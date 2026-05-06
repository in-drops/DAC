from __future__ import annotations
import math
import random
import secrets
from eth_utils import to_checksum_address
from loguru import logger
from config import config, Chains
from core.bot import Bot
from core.onchain import Onchain
from models.amount import Amount
from utils.logging import init_logger
from utils.utils import get_accounts, random_sleep, select_and_shuffle_profiles, get_user_agent
from utils.inputs import (
    input_pause, input_cycle_amount, input_cycle_pause, start_pause,
    increase_counter_in_txt, cell_date_to_txt, get_value_from_txt
)

# ============================================================
TRANSFER_COUNT_MIN    = 2
TRANSFER_COUNT_MAX    = 5
TRANSFER_FILTER_LIMIT = 50
AMOUNT_MIN            = 0.0001   # минимум: одна десятитысячная DACC
AMOUNT_MAX            = 0.1      # максимум: одна десятая DACC
GAS_RESERVE           = 0.15     # резерв на газ в DACC
MAX_ERRORS            = 5

FILE_TRANSFERS_COUNT = 'transfers_count.txt'
FILE_TRANSFERS_DATE  = 'transfers_date.txt'
# ============================================================


def human_round(amount: float) -> float:
    if amount == 0:
        return 0.0
    magnitude = math.floor(math.log10(abs(amount)))
    sig_digits = random.randint(2, 4)
    decimal_places = sig_digits - magnitude - 1
    decimal_places = max(0, min(decimal_places, 8))
    return round(amount, decimal_places)


def generate_random_evm_address() -> str:
    return to_checksum_address('0x' + secrets.token_bytes(20).hex())


def calculate_transfer_amounts(balance: float, count: int) -> list[float]:
    available = max(balance - GAS_RESERVE, 0.0)
    if available <= 0:
        return []
    amounts = []
    for _ in range(count):
        raw = random.uniform(AMOUNT_MIN, AMOUNT_MAX)
        val = human_round(raw)
        if val <= 0 or sum(amounts) + val > available:
            break
        amounts.append(val)
    return amounts


def accounts_filter(accounts):
    result = []
    for acc in accounts:
        count = get_value_from_txt(acc, FILE_TRANSFERS_COUNT) or 0
        if count >= TRANSFER_FILTER_LIMIT:
            logger.info(f'{acc.profile_number} Лимит трансферов ({count}/{TRANSFER_FILTER_LIMIT}), пропускаем')
            continue
        result.append(acc)
    return result


NETWORK_ERR_MARKERS = (
    'SSLEOFError', 'SSLError', 'ProxyError', 'Max retries',
    'Remote end closed', 'ConnectionError', 'Read timed out'
)


def is_network_error(e: Exception) -> bool:
    return any(s in str(e) for s in NETWORK_ERR_MARKERS)


def safe_get_balance(account, chain, attempts: int = 4):
    """Получить баланс с retry на сетевых ошибках. Пересоздаёт Onchain каждую попытку."""
    last_err = None
    for n in range(1, attempts + 1):
        try:
            onchain = Onchain(account, chain)
            return onchain.get_balance(), onchain
        except Exception as e:
            last_err = e
            if not is_network_error(e):
                raise
            if n < attempts:
                random_sleep(20, 40)
    raise last_err


def worker(account) -> None:
    account.user_agent = get_user_agent()

    with Bot(account, chain=Chains.DAC_TESTNET) as bot:
        try:
            balance, onchain = safe_get_balance(bot.account, bot.chain)
        except Exception as e:
            logger.error(f'{account.profile_number} Не удалось получить баланс после ретраев: {e}')
            return
        symbol  = bot.chain.native_token

        logger.info(
            f'{account.profile_number} Баланс: {balance.ether:.6f} {symbol} | '
            f'Газовый резерв: {GAS_RESERVE} {symbol}'
        )

        if balance.ether <= GAS_RESERVE:
            logger.warning(f'⚠️ {account.profile_number} Баланс ниже газового резерва, пропускаем')
            return

        count   = random.randint(TRANSFER_COUNT_MIN, TRANSFER_COUNT_MAX)
        amounts = calculate_transfer_amounts(balance.ether, count)

        if not amounts:
            logger.warning(f'⚠️ {account.profile_number} Недостаточно баланса для трансферов: {balance.ether:.6f} {symbol}')
            return

        logger.info(f'{account.profile_number} Запланировано {len(amounts)} трансферов: {amounts}')

        errors = 0
        done   = 0
        for i, amount_val in enumerate(amounts):
            try:
                recipient = generate_random_evm_address()
                amount    = Amount(amount_val, decimals=18)
                tx_hash   = onchain.send_token(to_address=recipient, amount=amount, token=None)

                logger.success(
                    f'{account.profile_number} Трансфер {i + 1}/{len(amounts)}: '
                    f'{amount_val} {symbol} → {recipient[:10]}... | tx: {tx_hash} 🎯'
                )
                increase_counter_in_txt(bot, FILE_TRANSFERS_COUNT)
                cell_date_to_txt(bot, FILE_TRANSFERS_DATE)
                done += 1

            except Exception as e:
                errors += 1
                logger.error(f'{account.profile_number} Ошибка трансфера {i + 1}/{len(amounts)}: {e}')
                if errors >= MAX_ERRORS:
                    logger.warning(f'⚠️ {account.profile_number} Достигнут лимит ошибок ({MAX_ERRORS}), пропускаем аккаунт')
                    break
                # При сетевых ошибках RPC даём ноде время восстановиться и пересоздаём соединение
                if is_network_error(e):
                    random_sleep(30, 60)
                    onchain = Onchain(bot.account, bot.chain)
                continue

            if i < len(amounts) - 1:
                random_sleep(30, 60)

        logger.success(
            f'{account.profile_number} Выполнено {done}/{len(amounts)} трансферов. '
            f'Данные в {FILE_TRANSFERS_COUNT} 🔥'
        )


def main():
    init_logger()
    accounts     = get_accounts()
    accounts     = select_and_shuffle_profiles(accounts)
    pause        = input_pause()
    cycle_amount = input_cycle_amount()
    cycle_pause  = input_cycle_pause()
    delay        = start_pause()

    if delay:
        random_sleep(delay)

    for cycle in range(cycle_amount):
        active = accounts_filter(accounts)
        if not active:
            logger.warning('⚠️ Все аккаунты достигли лимита трансферов!')
            break
        for account in active:
            worker(account)
            random_sleep(pause)
        logger.success(f'Цикл {cycle + 1}/{cycle_amount} завершён ✅')
        if cycle < cycle_amount - 1:
            random_sleep(cycle_pause)


if __name__ == '__main__':
    main()
