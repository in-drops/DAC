from pprint import pprint
from loguru import logger
import random
from core.bot import Bot
from models.amount import Amount
from config import Chains
from config import Contracts
from core.onchain import Onchain
from models.chain import Chain
import requests
import time


def get_request_id(bot: Bot, amount: Amount, to_token_contract: str, from_chain: Chain, to_chain: Chain) -> str:

    url = 'https://api.relay.link/quote'
    body = {
        'user': bot.account.address,
        'originChainId': from_chain.chain_id,
        'destinationChainId': to_chain.chain_id,
        'originCurrency': '0x0000000000000000000000000000000000000000',
        'destinationCurrency': to_token_contract,
        'recipient': bot.account.address,
        'tradeType': 'EXPECTED_OUTPUT',
        'amount': amount.wei,
        'referrer': 'relay.link/swap',
        'useDepositAddress': False,
        'useExternalLiquidity': False
    }

    response = requests.post(url, json=body, timeout=(5, 10))
    response.raise_for_status()
    response = response.json()
    return response['steps'][0]['requestId']


# def relay(bot: Bot, to_chain: Chain, amount: Amount, to_token_contract: str | None = None, onchain: Onchain | None = None):
#
#     if onchain is None:
#         onchain = bot.onchain
#
#     if to_token_contract is None:
#         to_token_contract = '0x0000000000000000000000000000000000000000'
#
#     from_chain = onchain.chain
#     relay_contract = Contracts.get_contract_by_name('relay', from_chain)
#     request_id = get_request_id(bot, amount, to_token_contract, from_chain, to_chain)
#     tx_params = onchain._prepare_tx(value=amount, to_address=relay_contract.address)
#     tx_params['data'] = request_id
#     tx_params = onchain._estimate_gas(tx_params)
#     tx_hash = onchain._sign_and_send(tx_params)
#     message = f'Cумма: {amount.ether:.5f} {from_chain.native_token} | В сеть: {to_chain.name.upper()} | Tx hash: {tx_hash}'
#     logger.info(f'Транзакция отправлена! {message}')




def relay(bot: Bot, to_chain: Chain, amount: Amount, to_token_contract: str | None = None, onchain: Onchain | None = None):
    if onchain is None:
        onchain = bot.onchain

    if to_token_contract is None:
        to_token_contract = '0x0000000000000000000000000000000000000000'

    from_chain = onchain.chain
    relay_contract = Contracts.get_contract_by_name('relay', from_chain)

    # Повторные попытки получения request_id
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            request_id = get_request_id(bot, amount, to_token_contract, from_chain, to_chain)
            break
        except Exception as e:
            logger.warning(f"[{attempt}/{max_retries}] Ошибка получения ответа от Relay Mainnet API: {e}")
            if attempt == max_retries:
                logger.error(f"Не удалось получить ответ от Relay Mainnet API после {attempt} попыток!")
                return
            time.sleep(5)

    # Подготовка и отправка транзакции
    tx_params = onchain._prepare_tx(value=amount, to_address=relay_contract.address)
    tx_params['data'] = request_id
    tx_params = onchain._estimate_gas(tx_params)
    tx_hash = onchain._sign_and_send(tx_params)

    message = f'Сумма: {amount.ether:.5f} {from_chain.native_token} | В сеть: {to_chain.name.upper()} | Tx hash: {tx_hash}'
    logger.success(f'Транзакция отправлена! {message}')


def get_request_id_testnet(bot: Bot, amount: Amount, to_token_contract: str, from_chain: Chain, to_chain: Chain) -> str:

    url = 'https://api.testnets.relay.link/quote'
    body = {
        'user': bot.account.address,
        'originChainId': from_chain.chain_id,
        'destinationChainId': to_chain.chain_id,
        'originCurrency': '0x0000000000000000000000000000000000000000',
        'destinationCurrency': to_token_contract,
        'recipient': bot.account.address,
        'tradeType': 'EXPECTED_OUTPUT',
        'amount': amount.wei,
        'referrer': 'relay.link/swap',
        'useDepositAddress': False,
        'useExternalLiquidity': False
    }

    response = requests.post(url, json=body)
    response.raise_for_status()
    response = response.json()
    return response['steps'][0]['requestId']

def relay_testnet(bot: Bot, to_chain: Chain, amount: Amount, to_token_contract: str | None = None, onchain: Onchain | None = None):

    if onchain is None:
        onchain = bot.onchain

    if to_token_contract is None:
        to_token_contract = '0x0000000000000000000000000000000000000000'

    from_chain = onchain.chain
    relay_contract = Contracts.get_contract_by_name('relay', from_chain)
    request_id = get_request_id_testnet(bot, amount, to_token_contract, from_chain, to_chain)
    tx_params = onchain._prepare_tx(value=amount, to_address=relay_contract.address)
    tx_params['data'] = request_id
    tx_params = onchain._estimate_gas(tx_params)
    tx_hash = onchain._sign_and_send(tx_params)
    message = f'Cумма: {amount.ether:.5f} {from_chain.native_token} | В сеть: {to_chain.name.upper()} | Tx hash: {tx_hash}'
    logger.info(f'Транзакция отправлена! {message}')







