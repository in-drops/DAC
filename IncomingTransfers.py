from __future__ import annotations
import math
import random
import time
import urllib3

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

# ============================================================
INCOMING_COUNT = (1, 2)    # сколько входящих переводов получает аккаунт
AMOUNT_MIN     = 0.0001    # мин. сумма перевода, DACC
AMOUNT_MAX     = 0.01      # макс. сумма перевода, DACC
MIN_SENDER_BALANCE = 0.05  # мин. баланс отправителя

TX_RETRIES       = 3
TX_RETRY_PAUSE   = (10, 20)

FILE_INCOMING = 'incoming_status.txt'
# ============================================================


class SimpleBot:
    def __init__(self, account: Account):
        self.account = account


def human_round(amount: float) -> float:
    if amount == 0:
        return 0.0
    magnitude = math.floor(math.log10(abs(amount)))
    sig_digits = random.randint(2, 4)
    decimal_places = max(0, min(sig_digits - magnitude - 1, 8))
    return round(amount, decimal_places)


def _make_onchain(account: Account) -> Onchain:
    onchain = Onchain(account, Chains.DAC_TESTNET)
    onchain.w3 = Web3(Web3.HTTPProvider(
        Chains.DAC_TESTNET.rpc,
        request_kwargs={
            "headers": {"User-Agent": account.user_agent, "Content-Type": "application/json"},
            "proxies": prepare_proxy_requests(account.proxy),
            "verify": False,
        },
    ))
    return onchain


def send_from(sender: Account, recipient_address: str) -> bool:
    sender.user_agent = get_user_agent()
    onchain = _make_onchain(sender)

    balance = onchain.get_balance()
    if balance.ether < MIN_SENDER_BALANCE:
        logger.warning(
            f"Отправитель #{sender.profile_number} ⚠️ Баланс {balance.ether:.4f} DACC "
            f"— меньше минимума {MIN_SENDER_BALANCE} DACC, пропуск"
        )
        return False

    amount_val = human_round(random.uniform(AMOUNT_MIN, AMOUNT_MAX))
    amount = Amount(round(amount_val * 10**18), wei=True)

    for attempt in range(1, TX_RETRIES + 1):
        try:
            tx_hash = onchain.send_token(
                to_address=Web3.to_checksum_address(recipient_address),
                amount=amount,
                token=None,
            )
            logger.info(
                f"#{sender.profile_number} → {recipient_address[:10]}... | "
                f"{amount_val} DACC | TX: {tx_hash[:16]}..."
            )
            return True
        except Exception as e:
            logger.warning(
                f"Отправитель #{sender.profile_number} ⚠️ TX, попытка {attempt}/{TX_RETRIES}: {e}"
            )
            if attempt < TX_RETRIES:
                time.sleep(random.uniform(*TX_RETRY_PAUSE))

    logger.error(f"Отправитель #{sender.profile_number} TX не прошёл после {TX_RETRIES} попыток")
    return False


def accounts_filter(accounts: list[Account]) -> list[Account]:
    filtered = []
    for account in accounts:
        status = get_value_from_txt(account, FILE_INCOMING)
        if status == "SUCCESS":
            logger.warning(f"{account.profile_number} ⚠️ Пропуск — входящие переводы уже выполнены")
            continue
        filtered.append(account)
    return filtered


def worker(account: Account, all_accounts: list[Account]) -> None:
    possible_senders = [a for a in all_accounts if a.address != account.address]
    if not possible_senders:
        logger.error(f"{account.profile_number} Нет доступных отправителей в списке")
        return

    count = random.randint(*INCOMING_COUNT)
    senders = random.sample(possible_senders, min(count, len(possible_senders)))

    received = 0
    for i, sender in enumerate(senders):
        if send_from(sender, account.address):
            received += 1
        if i < len(senders) - 1:
            random_sleep((5, 15))

    bot = SimpleBot(account)
    cell_value_to_txt(bot, "SUCCESS", FILE_INCOMING)

    if received > 0:
        logger.success(f"{account.profile_number} ✅ Получено {received}/{len(senders)} переводов")
    else:
        logger.warning(f"{account.profile_number} ⚠️ Ни один перевод не прошёл")


def main():
    init_logger()
    config.is_browser_run = False

    accounts = get_accounts()
    all_accounts = list(accounts)
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
            logger.warning("⚠️ Все аккаунты уже получили входящие переводы")
            if cycle < cycles - 1:
                random_sleep(cycle_pause)
            continue

        for i, account in enumerate(active):
            worker(account, all_accounts)

            if i < len(active) - 1:
                random_sleep(pause)

        if cycle < cycles - 1:
            logger.info("Пауза между циклами...")
            random_sleep(cycle_pause)

    logger.success("✅ Все циклы завершены!")


if __name__ == "__main__":
    main()
