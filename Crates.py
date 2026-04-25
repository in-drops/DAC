import random
import re
import time
from datetime import datetime, timedelta

import requests
from loguru import logger

from config.settings import config
from models.account import Account
from utils.inputs import (
    increase_counter_in_txt,
    input_pause, input_cycle_amount, input_cycle_pause, start_pause,
)
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

CRATE_COST_QE = 150
DAILY_LIMIT = 5

class SessionExpired(Exception):
    pass


AUTH_RETRIES = 3
AUTH_RETRY_PAUSE = (5, 10)
CRATE_OPEN_RETRIES = 3
CRATE_OPEN_RETRY_PAUSE = (5, 10)
CRATE_REVEAL_DELAY = (5, 8)
OPEN_PAUSE = (10, 20)  # пауза между ящиками одного аккаунта


class SimpleBot:
    """Обёртка для совместимости с трекинг-функциями utils/inputs.py."""
    def __init__(self, account: Account):
        self.account = account


def _sec_ch_ua(user_agent: str) -> str:
    """Формирует sec-ch-ua из строки User-Agent."""
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
        logger.error(f"{account.profile_number} Ошибка получения профиля: {e}")
        return None


def open_crate(
    session: requests.Session,
    account: Account,
    csrf_token: str,
) -> tuple[dict | None, dict | None]:
    """Открывает ящик. Возвращает (ответ_post, профиль_после_открытия).

    После POST ждём ~5-8 сек (анимация открытия), затем запрашиваем
    профиль для актуального баланса QE и полученных наград.
    """
    proxies = prepare_proxy_requests(account.proxy)

    for attempt in range(1, CRATE_OPEN_RETRIES + 1):
        try:
            resp = session.post(
                f"{API_BASE}/inception/crate/open/",
                json={},
                headers=_headers(account.user_agent, csrf_token),
                proxies=proxies,
                timeout=30,
            )
            if resp.status_code == 401:
                raise SessionExpired("сессия истекла (401)")

            resp.raise_for_status()
            open_result = resp.json()

            # ждём завершения анимации открытия (~5 сек на фронтенде)
            time.sleep(random.uniform(*CRATE_REVEAL_DELAY))

            profile_after = get_profile(session, account, csrf_token)
            return open_result, profile_after

        except SessionExpired:
            raise
        except Exception as e:
            logger.warning(
                f"{account.profile_number} ⚠️ Открытие ящика, попытка {attempt}/{CRATE_OPEN_RETRIES}: {e}"
            )
            if attempt < CRATE_OPEN_RETRIES:
                time.sleep(random.uniform(*CRATE_OPEN_RETRY_PAUSE))

    logger.error(f"{account.profile_number} Не удалось открыть ящик после {CRATE_OPEN_RETRIES} попыток")
    return None, None


def _format_reward(open_result: dict, qe_before: int, profile_after: dict | None) -> str:
    """Формирует строку лога с содержимым ящика.

    Реальная структура API-ответа:
      open_result['reward'] = {
        label, type, amount, multiplier, hours, dacc, tx_hash
      }
      open_result['new_total_qe'] — баланс после открытия
    """
    parts = []

    reward      = open_result.get("reward") or {}
    label       = reward.get("label", "")
    rtype       = reward.get("type", "")
    amount      = reward.get("amount", 0)
    multiplier  = reward.get("multiplier")
    hours       = reward.get("hours")
    dacc        = reward.get("dacc", 0)
    tx_hash     = reward.get("tx_hash", "")
    new_total   = open_result.get("new_total_qe", 0)

    if rtype == "qe":
        parts.append(f"награда: {label or f'{amount} QE'}")
    elif rtype == "multiplier":
        mult_str  = f"{multiplier}x" if multiplier else "?"
        hours_str = f" {hours}ч" if hours else ""
        parts.append(f"награда: Множитель {mult_str}{hours_str}")
    elif rtype == "dacc":
        dacc_str = f"{dacc} DACC" if dacc else "DACC"
        parts.append(f"награда: {dacc_str}")
        if tx_hash:
            parts.append(f"tx: {tx_hash[:20]}...")
    elif rtype == "jackpot":
        parts.append(f"награда: 🎰 JACKPOT {label or f'{amount} QE'}")
    elif label:
        parts.append(f"награда: {label}")
    elif rtype:
        parts.append(f"награда: {rtype} {amount}")
    else:
        parts.append(f"raw: {open_result}")

    balance = new_total or (profile_after.get("qe_balance") if profile_after else None)
    if balance:
        parts.append(f"баланс QE: {balance}")

    return " | ".join(parts) if parts else str(open_result)


def get_today_opens(account: Account) -> int:
    """Возвращает количество открытий ящиков сегодня.

    Использует crates_count.txt. Если дата в файле != сегодня — возвращает 0.
    """
    from pathlib import Path
    filepath = Path("config/data/crates_count.txt")
    today = datetime.now().strftime("%Y-%m-%d")

    if not filepath.exists():
        return 0

    with open(filepath, "r", encoding="utf-8") as f:
        for line in reversed(f.readlines()):
            parts = line.strip().split("\t")
            if len(parts) == 4 and str(parts[0]) == str(account.profile_number):
                saved_date = parts[2]
                if saved_date == today:
                    try:
                        return int(parts[3])
                    except ValueError:
                        return 0
                else:
                    return 0  # день сменился — счётчик сброшен
    return 0


def accounts_filter(accounts: list[Account]) -> list[Account]:
    filtered = []
    for account in accounts:
        opens_today = get_today_opens(account)
        if opens_today >= DAILY_LIMIT:
            logger.warning(
                f"{account.profile_number} ⚠️ Пропуск — дневной лимит достигнут ({opens_today}/{DAILY_LIMIT})"
            )
            continue
        filtered.append(account)
    return filtered


def worker(account: Account) -> None:
    account.user_agent = get_user_agent()

    session, csrf_token = auth(account)
    if not session:
        return

    profile = get_profile(session, account, csrf_token)
    if not profile:
        return

    qe_balance = profile.get("qe_balance", 0)
    logger.info(f"{account.profile_number} QE баланс: {qe_balance}")

    max_by_qe = int(qe_balance) // CRATE_COST_QE
    if max_by_qe == 0:
        logger.warning(
            f"{account.profile_number} ⚠️ Недостаточно QE (есть {qe_balance}, нужно {CRATE_COST_QE})"
        )
        return

    opens_today = get_today_opens(account)
    remaining_daily = DAILY_LIMIT - opens_today
    actual_count = min(max_by_qe, remaining_daily)

    if actual_count <= 0:
        logger.warning(f"{account.profile_number} ⚠️ Нет доступных слотов сегодня")
        return

    bot = SimpleBot(account)
    current_qe = qe_balance
    opened = 0
    reauth_attempts = 0

    i = 0
    while i < actual_count:
        try:
            open_result, profile_after = open_crate(session, account, csrf_token)
        except SessionExpired:
            if reauth_attempts >= AUTH_RETRIES:
                logger.error(f"{account.profile_number} Реавторизация исчерпана, останавливаем")
                break
            reauth_attempts += 1
            logger.warning(f"{account.profile_number} ⚠️ Сессия истекла — реавторизация {reauth_attempts}/{AUTH_RETRIES}")
            session, csrf_token = auth(account)
            if not session:
                break
            continue

        if open_result is None:
            break

        reauth_attempts = 0
        opened += 1
        increase_counter_in_txt(bot, "crates_count.txt")

        reward_info = _format_reward(open_result, current_qe, profile_after)
        logger.success(f"{account.profile_number} 🎯 Ящик {i + 1}/{actual_count}: {reward_info}")

        if profile_after:
            current_qe = profile_after.get("qe_balance", current_qe)

        i += 1
        if i < actual_count:
            random_sleep(*OPEN_PAUSE)

    if opened > 0:
        logger.success(
            f"{account.profile_number} 🔥 Открыто ящиков: {opened} | QE осталось: {current_qe}"
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

        active = accounts_filter(accounts)
        if not active:
            logger.warning(
                f"⚠️ Все аккаунты достигли дневного лимита ({DAILY_LIMIT} ящиков)"
            )
            if cycle < cycles - 1:
                random_sleep(cycle_pause)
            continue

        for i, account in enumerate(active):
            worker(account)

            if i < len(active) - 1:
                random_sleep(pause)

        if cycle < cycles - 1:
            logger.info("Пауза между циклами...")
            random_sleep(cycle_pause)

    logger.success("✅ Все циклы завершены!")


if __name__ == "__main__":
    main()
