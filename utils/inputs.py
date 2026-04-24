from __future__ import annotations
import re
import random
from typing import Optional, Tuple
from config import Chains, Tokens
from core.bot import Bot
from core.excel import Excel
from core.onchain import Onchain
from models.account import Account
from models.amount import Amount
from models.chain import Chain
from models.token import Token
from loguru import logger



def input_pause() -> float:
    while True:
        pause_input = input('\nВведите паузу между профилями в минутах (например: 5, 10, 3) и нажмите ENTER: ')
        pause_cleaned = re.sub(r'\D', '', pause_input)
        try:
            pause_minutes = float(pause_cleaned)
            pause_seconds = pause_minutes * 60
            print(f"Пауза между профилями: {int(pause_minutes)} минут.\n")
            return pause_seconds
        except ValueError:
            print("Некорректный ввод! Попробуйте снова.")


def input_cycle_amount() -> int:

    while True:
        amount_input = input('Введите количество циклов (например: 1, 5, 10) и нажмите ENTER: ')
        amount_cleaned = re.sub(r'\D', '', amount_input)
        try:
            cycle_amount = int(amount_cleaned)
            print(f"Введено количество циклов: {int(amount_input)}!\n")
            return cycle_amount
        except ValueError:
            print("Некорректный ввод! Попробуйте снова.")

def input_cycle_pause() -> float:
    while True:
        pause_input = input('Введите паузу между циклами в минутах (например: 5, 10, 120) и нажмите ENTER: ')
        pause_cleaned = re.sub(r'\D', '', pause_input)
        try:
            pause_minutes = float(pause_cleaned)
            pause_seconds = pause_minutes * 60
            print(f"Пауза между циклами: {int(pause_minutes)} минут.\n")
            return pause_seconds
        except ValueError:
            print("Некорректный ввод! Попробуйте снова.")

def input_okx_chain() -> Chain:

    chains = Chains.get_chains_list()
    filtered_chains = [chain for chain in chains if getattr(chain, 'okx_name', None)]
    message_chains_list = '\n'.join([f'{index} - {chain.name.upper()}' for index, chain in enumerate(filtered_chains, start=1)])
    while True:
        try:
            chain_select_index = int(input(f'\nВыбор сети для переводов с биржей OKX:\n{message_chains_list}\nВведите номер сети и нажмите ENTER: '))
            chain = filtered_chains[chain_select_index - 1]
            print(f'Выбрана сеть {chain.name.upper()}!')
            return chain
        except (ValueError, IndexError):
            print("Некорректный ввод! Попробуйте снова.")

def input_token_address() -> str:

    while True:
        token_address = input('\nВведите адрес контракта токена: ')
        token_address = re.sub(r'^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$', '', token_address)
        if len(token_address) == 42:
            return token_address
        else:
            print("Некорректный ввод! Попробуйте снова.")

def input_amount_type() -> Tuple[str, Optional[float]]:

    input_amount_type_message = (
        f"Выбор суммы вывода с каждого кошелька:\n"
        f"1 - все токены\n"
        f"2 - 50%\n"
        f"3 - 25%\n"
        f"4 - указать сумму вручную"
    )
    while True:
        amount_type = input(f'{input_amount_type_message}\nВведите номер выбора и нажмите ENTER: ')
        amount_type = re.sub(r'\D', '', amount_type)
        if amount_type in ['1', '2', '3']:
            return amount_type, None
        if amount_type == '4':
            amount_input = input_withdraw_amount()
            return amount_type, amount_input
        print("Некорректный ввод! Введите 1, 2, 3 или 4.\n")

def get_withdraw_amount(balance, amount_type, amount_input) -> Amount | float | int:

    if amount_type == '1':
        return balance
    elif amount_type == '2':
        return balance / 2
    elif amount_type == '3':
        return balance / 4
    elif amount_type == '4' and amount_input:
        return amount_input

def input_withdraw_amount() -> float | int:

    while True:
        amount_input = input(
            'Введите сумму для каждого кошелька (например: 3, 7.5, 0.001) и нажмите ENTER: ')
        amount_input = re.sub(r'[^0-9,.]', '', amount_input).replace(',', '.')
        try:
            return float(amount_input)
        except ValueError:
            print("Некорректный ввод! Попробуйте снова.")


def input_deposit_amount() -> float:

    while True:
        amount_input = input(
            'Введите сумму хранения для каждого кошелька (например: 3, 7.5, 0.001) и нажмите ENTER: ')
        amount_input = re.sub(r'[^0-9,.]', '', amount_input).replace(',', '.')
        try:
            amount_input = float(amount_input)
            return amount_input
        except ValueError:
            print("Некорректный ввод! Попробуйте снова.")


def input_checker_chain() -> Chain:

    chains = Chains.get_chains_list()
    message_chains_list = '\n'.join([f'{index} - {chain.name.upper()}' for index, chain in enumerate(chains, start=1)])
    while True:
        try:
            chain_select_index = input(
                f'\nВыбор сети для проверки баланса:\n{message_chains_list}\nВведите номер и нажмите ENTER: ')
            chain_select_index = re.sub(r'\D', '', chain_select_index)
            chain_select_index = int(chain_select_index)
            chain = chains[chain_select_index - 1]
            print(f'Выбрана сеть {chain.name.upper()}!')
            return chain
        except (ValueError, IndexError):
            print("Некорректный ввод! Попробуйте снова.")

def input_token_index(chain) -> Token:

    tokens = Tokens.get_tokens_by_chain(chain)
    message_tokens_list = '\n'.join(
        [f'{index} - {token.symbol}' for index, token in enumerate(tokens, start=1)])
    while True:
        try:
            token_select_index = input(
                f'\nВыбор токена из списка:\n{message_tokens_list}\nВведите номер токена и нажмите ENTER: ')
            token_select_index = re.sub(r'\D', '', token_select_index)
            token_select_index = int(token_select_index)
            token = tokens[token_select_index - 1]
            print(f'Выбран токен {token.symbol}!\n')
            return token
        except (ValueError, IndexError):
            print("Некорректный ввод! Попробуйте снова.")

def input_token_type(chain) -> Tuple[str, Optional[str]]:

    tokens = Tokens.get_tokens_by_chain(chain)
    symbols = ', '.join(token.symbol for token in tokens)
    token_type_message = (
        f"\nВыбор типа токенов:\n"
        f"1 - {chain.native_token} (нативный токен)\n"
        f"2 - токены из списка: {symbols}\n"
        f"3 - токена нет в списке (поиск по адресу контракта)"
    )
    while True:
        token_type = input(f'{token_type_message}\nВведите номер выбора и нажмите ENTER: ')
        token_type = re.sub(r'\D', '', token_type)

        if token_type in ['1', '2']:
            return token_type, None

        if token_type == '3':
            token_address = input_token_address()
            return token_type, token_address

        print("Некорректный ввод! Введите 1, 2 или 3.")

def input_token_type_and_token_list(chain) -> Tuple[str, Optional[Token | str]]:

    tokens = Tokens.get_tokens_by_chain(chain)
    symbols = ', '.join(token.symbol for token in tokens)
    token_type_message = (
        f"\nВыбор типа токенов:\n"
        f"1 - {chain.native_token} (нативный токен)\n"
        f"2 - токен из списка: {symbols}\n"
        f"3 - токена нет в списке (поиск по адресу контракта)"
    )
    while True:
        token_type = input(f'{token_type_message}\nВведите номер выбора и нажмите ENTER: ')
        token_type = re.sub(r'\D', '', token_type)

        if token_type == '1':
            print(f'Выбран нативный токен {chain.native_token}!\n')
            return token_type, None

        if token_type == '2':
            token = input_token_index(chain)
            return token_type, token

        if token_type == '3':
            token_address = input_token_address()
            return token_type, token_address

        print("Некорректный ввод! Введите 1, 2 или 3.")

def okx_activity():

    action_type_message = (
        f"Выбор действия для работы с биржей OKX:\n"
        f"1 - пополняем токенами кошельки с биржи OKX\n"
        f"2 - выводим токены с кошельков на биржу OKX\n"
    )
    while True:
        action_type = input(f'{action_type_message}Введите номер выбора и нажмите ENTER: ')
        action_type = re.sub(r'\D', '', action_type)
        if action_type == '1':
            return
        if action_type == '2':
            return

        print("Некорректный ввод! Введите 1 или 2\n")

def start_pause() -> int:

    start_pause_message = (
        f"Выберите время для запуска софта:\n"
        f"1 - запустить софт сразу\n"
        f"2 - запустить софт через определённое время\n"
    )
    while True:
        action_type = input(f'{start_pause_message}Введите номер выбора и нажмите ENTER: ')
        action_type = re.sub(r'\D', '', action_type)

        if action_type == '1':
            return 0

        if action_type == '2':
            while True:
                start_pause_input = input('\nВведите время задержки в минутах и нажмите ENTER: ')
                start_pause_input = re.sub(r'[^0-9,.]', '', start_pause_input).replace(',', '.')

                try:
                    delay_minutes = float(start_pause_input)
                    delay_seconds = int(delay_minutes * 60)
                    print(f'Запуск софта произойдёт через {int(start_pause_input)} минут...')
                    return delay_seconds

                except ValueError:
                    print("Некорректный ввод! Попробуйте снова.")

        print("Некорректный ввод! Введите 1 или 2\n")

import os
from datetime import datetime
from pathlib import Path

# Гарантируем, что папка существует
DATA_DIR = Path("config/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)


# def cell_date_to_txt(bot: Bot, filename: str) -> None:
#     filepath = DATA_DIR / filename
#     profile_number = bot.account.profile_number
#     wallet_address = bot.account.address
#     date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#     with open(filepath, "a", encoding="utf-8") as f:
#         f.write(f"{profile_number}\t{wallet_address}\t{date_str}\n")


def cell_date_to_txt(bot: Bot, filename: str) -> None:
    filepath = DATA_DIR / filename
    profile_number = str(bot.account.profile_number)
    wallet_address = bot.account.address
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = []
    updated = False

    # Прочитать все строки и обновить нужную
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 3 and parts[0] == profile_number:
                    lines.append(f"{profile_number}\t{wallet_address}\t{date_str}\n")
                    updated = True
                else:
                    lines.append(line)

    # Если профиль не найден — добавим новую строку
    if not updated:
        lines.append(f"{profile_number}\t{wallet_address}\t{date_str}\n")

    # Перезаписать файл
    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(lines)



def get_date_from_txt(account: Account, filename: str) -> datetime:
    filepath = DATA_DIR / filename
    profile_number = account.profile_number
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in reversed(f.readlines()):
                parts = line.strip().split("\t")
                if len(parts) >= 3 and str(profile_number) == parts[0]:
                    try:
                        return datetime.strptime(parts[2], "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        break  # если формат даты сломан — вернём старую ниже
    except FileNotFoundError:
        pass

    # если ничего не нашли — вернём старую дату
    return datetime.now().replace(year=2000)



def cell_value_to_txt(bot, value: int | float | str, filename: str) -> None:
    filepath = DATA_DIR / filename
    profile_number = bot.account.profile_number
    wallet_address = bot.account.address
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    updated = False
    new_lines = []

    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\t")
                if parts[0] == str(profile_number):
                    # Заменяем дату и значение
                    new_line = f"{parts[0]}\t{parts[1]}\t{date_str}\t{value}\n"
                    new_lines.append(new_line)
                    updated = True
                else:
                    new_lines.append(line)

    if not updated:
        # Добавляем новую строку, если профиль ещё не был записан
        new_line = f"{profile_number}\t{wallet_address}\t{date_str}\t{value}\n"
        new_lines.append(new_line)

    # Перезаписываем файл
    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

def get_value_from_txt(account: Account, filename: str) -> int | float | str | None:
    filepath = DATA_DIR / filename
    profile_number = account.profile_number

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in reversed(f.readlines()):
                parts = line.strip().split("\t")
                if len(parts) == 4 and str(profile_number) == parts[0]:
                    value = parts[3]
                    # Попробуем распарсить как int
                    if value.isdigit() or (value.startswith('-') and value[1:].isdigit()):
                        return int(value)
                    # Попробуем как float
                    try:
                        return float(value)
                    except ValueError:
                        pass
                    # Вернём как строку
                    return value
    except FileNotFoundError:
        return None

def increase_counter_in_txt(bot: Bot, filename: str, number: int = 1) -> int:
    filepath = DATA_DIR / filename
    profile_number = bot.account.profile_number
    wallet_address = bot.account.address
    date_str = datetime.now().strftime("%Y-%m-%d")
    updated = False
    result = 0
    lines = []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        pass

    for i, line in enumerate(lines):
        parts = line.strip().split("\t")
        if len(parts) == 4 and parts[0] == str(profile_number):
            try:
                current = int(parts[3])
            except ValueError:
                raise ValueError(f"Некорректное значение счётчика у профиля {profile_number}: {parts[3]}")
            result = current + number
            lines[i] = f"{profile_number}\t{wallet_address}\t{date_str}\t{result}\n"
            updated = True
            break

    if not updated:
        result = number
        lines.append(f"{profile_number}\t{wallet_address}\t{date_str}\t{result}\n")

    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(lines)

    return result

def get_counter_from_txt(bot: Bot, filename: str) -> int:
    filepath = DATA_DIR / filename
    profile_number = str(bot.account.profile_number)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in reversed(f.readlines()):
                parts = line.strip().split("\t")
                # Проверяем формат (4 части: профиль, адрес, дата, значение)
                if len(parts) == 4 and parts[0] == profile_number:
                    val_str = parts[3]
                    if val_str.isdigit():
                        return int(val_str)
                    else:
                        raise TypeError(f"Значение в файле для профиля {profile_number} не является целым числом: {val_str}")
        return 0
    except FileNotFoundError:
        return 0

def payment_chain(bot: Bot, amount: Amount):
    excel_report = Excel(bot.account, file='accounts.xlsx')
    # account_chain = excel_report.get_cell('Payment Chain').strip().upper()
    account_chain = excel_report.get_cell('Payment Chain')
    if account_chain is None:
        logger.error('Платёжная сеть не указана в таблице accounts.xlsx!')
        return None
    account_chain = re.sub(r'[^A-Z]', '', excel_report.get_cell('Payment Chain').upper())
    arb_chain = Chains.ARBITRUM_ONE
    arb_instance = Onchain(bot.account, arb_chain)
    arb_balance = arb_instance.get_balance().ether
    op_chain = Chains.OP
    op_instance = Onchain(bot.account, op_chain)
    op_balance = op_instance.get_balance().ether
    base_chain = Chains.BASE
    base_instance = Onchain(bot.account, base_chain)
    base_balance = base_instance.get_balance().ether

    if account_chain == 'ARB':
        if arb_balance >= amount * 1.1:
            logger.warning(f'Для оплаты выбрана платёжная сеть профиля по умолчанию {arb_chain.name.upper()}!')
            chain = arb_chain
            return chain

        else:
            if arb_balance <= amount * 1.1:
                logger.warning(
                    f'Баланс в платёжной сети профиля по умолчанию {arb_chain.name.upper()} недостаточный: {arb_balance:.5f}! Проверяем сети {op_chain.name.upper()} и {base_chain.name.upper()}...')
                if op_balance >= amount * 1.1:
                    logger.success(f'Платёжной сетью выбрана {op_chain.name.upper()}! Баланс сети: {op_balance:.5f}')
                    chain = op_chain
                    return chain
                elif base_balance >= amount * 1.1:
                    logger.success(
                        f'Платёжной сетью выбрана {base_chain.name.upper()}! Баланс сети: {base_balance:.5f}')
                    chain = base_chain
                    return chain
                else:
                    logger.error(
                        f'Балансы сетей {op_chain.name.upper()} и {base_chain.name.upper()} недостаточные для совершения транзакции! Сделайте пополнение...')
                    return

    if account_chain == 'OP':
        if op_balance >= amount * 1.1:
            logger.warning(f'Для оплаты выбрана платёжная сеть профиля по умолчанию {op_chain.name.upper()}!')
            chain = op_chain
            return chain
        else:
            if op_balance <= amount * 1.1:
                logger.warning(
                    f'Баланс в платёжной сети профиля по умолчанию {op_chain.name.upper()} недостаточный: {op_balance:.5f}! Проверяем сети {arb_chain.name.upper()} и {base_chain.name.upper()}...')
                if arb_balance >= amount * 1.1:
                    logger.success(f'Платёжной сетью выбрана {arb_chain.name.upper()}! Баланс сети: {arb_balance:.5f}')
                    chain = arb_chain
                    return chain
                elif base_balance >= amount * 1.1:
                    logger.success(
                        f'Платёжной сетью выбрана {base_chain.name.upper()}! Баланс сети: {base_balance:.5f}')
                    chain = base_chain
                    return chain
                else:
                    logger.error(
                        f'Балансы сетей {arb_chain.name.upper()} и {base_chain.name.upper()} недостаточные для совершения транзакции! Сделайте пополнение...')
                    return

    if account_chain == 'BASE':
        if base_balance >= amount * 1.1:
            logger.warning(f'Для оплаты выбрана платёжная сеть профиля по умолчанию {base_chain.name.upper()}!')
            chain = base_chain
            return chain
        else:
            if base_balance <= amount * 1.1:
                logger.warning(
                    f'Баланс в платёжной сети профиля по умолчанию {base_chain.name.upper()} недостаточный: {base_balance:.5f}! Проверяем сети {arb_chain.name.upper()} и {op_chain.name.upper()}...')
                if arb_balance >= amount * 1.1:
                    logger.success(f'Платёжной сетью выбрана {arb_chain.name.upper()}! Баланс сети: {arb_balance:.5f}')
                    chain = arb_chain
                    return chain
                elif op_balance >= amount * 1.1:
                    logger.success(
                        f'Платёжной сетью выбрана {op_chain.name.upper()}! Баланс сети: {op_balance:.5f}')
                    chain = op_chain
                    return chain
                else:
                    logger.error(
                        f'Балансы сетей {arb_chain.name.upper()} и {op_chain.name.upper()} недостаточные для совершения транзакции! Сделайте пополнение...')
                    return