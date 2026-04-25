import random
import re
import time
import urllib3

import requests
from loguru import logger
from web3 import Web3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config.chains import Chains
from config.settings import config
from core.onchain import Onchain
from models.account import Account
from models.amount import Amount
from utils.inputs import (
    cell_value_to_txt, get_value_from_txt,
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

BURN_CONTRACT = Web3.to_checksum_address("0x3691A78bE270dB1f3b1a86177A8f23F89A8Cef24")
BURN_ABI = [
    {"name": "burnForQE", "type": "function", "stateMutability": "payable", "inputs": [], "outputs": []}
]

MIN_DACC_BALANCE = 1.0   # минимальный баланс DACC для запуска
BURN_PCT_MIN = 0.10      # 10%
BURN_PCT_MAX = 0.25      # 25%

AUTH_RETRIES = 3
AUTH_RETRY_PAUSE = (5, 10)
BURN_TX_RETRIES = 3
BURN_TX_RETRY_PAUSE = (10, 20)
CONFIRM_RETRIES = 3
CONFIRM_RETRY_PAUSE = (5, 10)
TX_INDEX_DELAY = (15, 20)  # ждём индексации TX в API


class SimpleBot:
    """Обёртка для совместимости с трекинг-функциями utils/inputs.py."""
    def __init__(self, account: Account):
        self.account = account


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


def confirm_burn(
    session: requests.Session,
    account: Account,
    csrf_token: str,
    tx_hash: str,
) -> dict | None:
    proxies = prepare_proxy_requests(account.proxy)

    for attempt in range(1, CONFIRM_RETRIES + 1):
        try:
            resp = session.post(
                f"{API_BASE}/inception/exchange/confirm-burn/",
                json={"tx_hash": tx_hash},
                headers=_headers(account.user_agent, csrf_token),
                proxies=proxies,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(
                f"{account.profile_number} ⚠️ confirm-burn, попытка {attempt}/{CONFIRM_RETRIES}: {e}"
            )
            if attempt < CONFIRM_RETRIES:
                time.sleep(random.uniform(*CONFIRM_RETRY_PAUSE))

    logger.error(
        f"{account.profile_number} confirm-burn не удался после {CONFIRM_RETRIES} попыток"
    )
    return None


def accounts_filter(accounts: list[Account]) -> list[Account]:
    filtered = []
    for account in accounts:
        status = get_value_from_txt(account, "burn_status.txt")
        if status == "SUCCESS":
            logger.warning(f"{account.profile_number} ⚠️ Пропуск — burn уже выполнен")
            continue
        filtered.append(account)
    return filtered


def worker(account: Account) -> None:
    account.user_agent = get_user_agent()

    session, csrf_token = auth(account)
    if not session:
        return

    onchain = Onchain(account, Chains.DAC_TESTNET)
    # DAC testnet RPC SSL issues through proxy — disable verification
    onchain.w3 = Web3(Web3.HTTPProvider(
        Chains.DAC_TESTNET.rpc,
        request_kwargs={
            "headers": {"User-Agent": account.user_agent, "Content-Type": "application/json"},
            "proxies": prepare_proxy_requests(account.proxy),
            "verify": False,
        },
    ))
    balance = onchain.get_balance()

    if balance.ether < MIN_DACC_BALANCE:
        logger.warning(
            f"{account.profile_number} ⚠️ Баланс {balance.ether:.4f} DACC "
            f"— меньше минимума {MIN_DACC_BALANCE} DACC"
        )
        return

    pct = random.uniform(BURN_PCT_MIN, BURN_PCT_MAX)
    decimals = random.randint(1, 4)
    burn_ether = round(balance.ether * pct, decimals)
    burn_amount = Amount(round(burn_ether * 10**18), wei=True)

    logger.info(
        f"{account.profile_number} Баланс: {balance.ether:.{decimals}f} DACC | "
        f"Сжигаем: {burn_ether:.{decimals}f} DACC ({pct * 100:.1f}%)"
    )

    contract = onchain.w3.eth.contract(address=BURN_CONTRACT, abi=BURN_ABI)

    tx_hash = None
    for attempt in range(1, BURN_TX_RETRIES + 1):
        try:
            tx_params = onchain._prepare_tx(value=burn_amount)
            tx = contract.functions.burnForQE().build_transaction(tx_params)
            tx["gas"] = onchain.safe_estimate_gas(tx)
            tx_hash = onchain._sign_and_send(tx)
            logger.info(f"{account.profile_number} 🎯 TX подтверждён: {tx_hash}")
            break
        except Exception as e:
            logger.warning(
                f"{account.profile_number} ⚠️ TX, попытка {attempt}/{BURN_TX_RETRIES}: {e}"
            )
            if attempt < BURN_TX_RETRIES:
                time.sleep(random.uniform(*BURN_TX_RETRY_PAUSE))

    if not tx_hash:
        logger.error(f"{account.profile_number} TX не прошёл после {BURN_TX_RETRIES} попыток")
        return

    if not tx_hash.startswith("0x"):
        tx_hash = f"0x{tx_hash}"

    time.sleep(random.uniform(*TX_INDEX_DELAY))

    # TX занимает время — сессия может истечь, переавторизуемся перед confirm
    session, csrf_token = auth(account)
    if not session:
        logger.error(
            f"{account.profile_number} Реавторизация перед confirm-burn не удалась | TX: {tx_hash}"
        )
        bot = SimpleBot(account)
        cell_value_to_txt(bot, "SUCCESS", "burn_status.txt")
        return

    result = confirm_burn(session, account, csrf_token, tx_hash)

    bot = SimpleBot(account)
    cell_value_to_txt(bot, "SUCCESS", "burn_status.txt")

    if result:
        qe_credited = result.get("qe_credited", "?")
        logger.success(
            f"{account.profile_number} 🔥 Burn выполнен | "
            f"Сожжено: {burn_ether:.{decimals}f} DACC | QE начислено: {qe_credited}"
        )
    else:
        logger.warning(
            f"{account.profile_number} ⚠️ TX прошёл, confirm-burn не ответил | TX: {tx_hash}"
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
            logger.warning("⚠️ Все аккаунты уже сожгли DACC")
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
