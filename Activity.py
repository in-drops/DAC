import random
import re
import time

import requests
from loguru import logger

from config.settings import config
from models.account import Account
from utils.inputs import input_pause, input_cycle_amount, input_cycle_pause, start_pause
from utils.logging import init_logger
from utils.utils import (
    get_accounts, select_and_shuffle_profiles,
    prepare_proxy_requests, random_sleep, get_user_agent,
)

BASE_URL = "https://inception.dachain.io"
API_BASE = "https://inception.dachain.io/api"

REFERRER_PAGES = [
    f"{BASE_URL}/dashboard",
    f"{BASE_URL}/badge",
    f"{BASE_URL}/my-activity",
    f"{BASE_URL}/leaderboard",
    f"{BASE_URL}/faucet",
    f"{BASE_URL}/qe-pool",
]

# Badge categories shown on each activity tab
SOCIAL_CATEGORIES = {"social", "referral", "exploration", "weekly"}
ONCHAIN_CATEGORIES = {"onboarding", "faucet", "hold", "transaction", "onchain", "streak"}

# Badges not yet active — excluded from "to do" list
COMING_SOON_KEYS = {
    "soc_share_weekly", "soc_quote_weekly", "soc_screenshot",
    "soc_reply", "soc_tag_friend", "soc_retweet_launch",
    "wk_claim_7", "wk_5_tx", "wk_share_x",
    "oc_bridge_tokens", "oc_multi_sig",
}

AUTH_RETRIES = 3
AUTH_RETRY_PAUSE = (5, 10)


def _sec_ch_ua(user_agent: str) -> str:
    m = re.search(r"Chrome/(\d+)", user_agent)
    v = m.group(1) if m else "135"
    return f'"Chromium";v="{v}", "Not-A.Brand";v="24", "Google Chrome";v="{v}"'


def _headers(user_agent: str, csrf_token: str = "") -> dict:
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Content-Type": "application/json",
        "Origin": BASE_URL,
        "Referer": random.choice(REFERRER_PAGES),
        "sec-ch-ua": _sec_ch_ua(user_agent),
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "Connection": "keep-alive",
    }
    if csrf_token:
        headers["X-CSRFToken"] = csrf_token
    return headers


def auth(account: Account) -> tuple[requests.Session | None, str]:
    proxies = prepare_proxy_requests(account.proxy)

    for attempt in range(1, AUTH_RETRIES + 1):
        session = requests.Session()
        try:
            resp = session.get(
                f"{API_BASE}/auth/csrf/",
                headers=_headers(account.user_agent),
                proxies=proxies,
                timeout=30,
            )
            resp.raise_for_status()
            csrf_token = session.cookies.get("csrftoken", "")

            resp = session.post(
                f"{API_BASE}/auth/wallet/",
                json={"wallet_address": account.address},
                headers=_headers(account.user_agent, csrf_token),
                proxies=proxies,
                timeout=30,
            )
            resp.raise_for_status()

            if "sessionid" not in session.cookies:
                raise ConnectionError("sessionid отсутствует в cookies")

            return session, csrf_token

        except Exception as e:
            logger.warning(
                f"{account.profile_number} ⚠️ Авторизация, попытка {attempt}/{AUTH_RETRIES}: {e}"
            )
            if attempt < AUTH_RETRIES:
                time.sleep(random.uniform(*AUTH_RETRY_PAUSE))

    logger.error(f"{account.profile_number} Авторизация не удалась после {AUTH_RETRIES} попыток")
    return None, ""


def get_badge_catalog(session: requests.Session, account: Account, csrf_token: str) -> dict[str, dict]:
    """Возвращает {badge_key: {name, category}} для всех бейджей."""
    proxies = prepare_proxy_requests(account.proxy)
    try:
        resp = session.get(
            f"{API_BASE}/inception/badges/catalog/",
            headers=_headers(account.user_agent, csrf_token),
            proxies=proxies,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            b["key"]: {"name": b["name"], "category": b["category"]}
            for b in data.get("badges", [])
        }
    except Exception as e:
        logger.error(f"{account.profile_number} Ошибка загрузки каталога бейджей: {e}")
        return {}


def get_profile(session: requests.Session, account: Account, csrf_token: str) -> dict | None:
    proxies = prepare_proxy_requests(account.proxy)
    try:
        resp = session.get(
            f"{API_BASE}/inception/profile/",
            headers=_headers(account.user_agent, csrf_token),
            proxies=proxies,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"{account.profile_number} Ошибка загрузки профиля: {e}")
        return None


def analyze_activity(
    profile: dict,
    catalog: dict[str, dict],
) -> dict:
    """Вычисляет статистику выполненных/невыполненных задач."""
    earned_keys = {b["badge__key"] for b in profile.get("badges", [])}

    social_done, social_todo = [], []
    onchain_done, onchain_todo = [], []

    for key, info in catalog.items():
        category = info["category"]
        name = info["name"]
        is_coming_soon = key in COMING_SOON_KEYS

        if category in SOCIAL_CATEGORIES and not is_coming_soon:
            if key in earned_keys:
                social_done.append(name)
            else:
                social_todo.append(name)

        elif category in ONCHAIN_CATEGORIES and not is_coming_soon:
            if key in earned_keys:
                onchain_done.append(name)
            else:
                onchain_todo.append(name)

    return {
        "social_done": social_done,
        "social_todo": social_todo,
        "onchain_done": onchain_done,
        "onchain_todo": onchain_todo,
        "events": len(profile.get("badges", [])),
        "qe": profile.get("qe_balance", 0),
    }


def worker(account: Account) -> None:
    account.user_agent = get_user_agent()

    session, csrf_token = auth(account)
    if not session:
        return

    catalog = get_badge_catalog(session, account, csrf_token)
    if not catalog:
        return

    profile = get_profile(session, account, csrf_token)
    if not profile:
        return

    stats = analyze_activity(profile, catalog)

    s_done = len(stats["social_done"])
    s_todo = len(stats["social_todo"])
    o_done = len(stats["onchain_done"])
    o_todo = len(stats["onchain_todo"])

    if stats["social_todo"]:
        logger.warning(
            f"{account.profile_number} 💬 Social: выполнено {s_done} / не выполнено {s_todo} "
            f"— {', '.join(stats['social_todo'])}"
        )
    else:
        logger.info(f"{account.profile_number} 💬 Social: все задания выполнены ({s_done})")

    if stats["onchain_todo"]:
        logger.warning(
            f"{account.profile_number} ⛓ OnChain: выполнено {o_done} / не выполнено {o_todo} "
            f"— {', '.join(stats['onchain_todo'])}"
        )
    else:
        logger.info(f"{account.profile_number} ⛓ OnChain: все задания выполнены ({o_done})")

    logger.success(
        f"{account.profile_number} 🔥 Events: {stats['events']} | QE: {stats['qe']}"
    )


def main():
    init_logger()
    config.is_browser_run = False

    accounts = get_accounts()
    accounts = select_and_shuffle_profiles(accounts)

    pause = input_pause()
    cycles = input_cycle_amount()
    cycle_pause = input_cycle_pause()
    delay = start_pause()

    if delay:
        logger.info(f"Задержка старта: {delay // 60} мин...")
        time.sleep(delay)

    for cycle in range(cycles):
        logger.info(f"Цикл {cycle + 1}/{cycles}")

        for i, account in enumerate(accounts):
            worker(account)

            if i < len(accounts) - 1:
                random_sleep(pause)

        if cycle < cycles - 1:
            logger.info("Пауза между циклами...")
            random_sleep(cycle_pause)

    logger.success("✅ Все циклы завершены!")


if __name__ == "__main__":
    main()
