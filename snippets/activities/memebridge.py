from loguru import logger
from core import bot
from core.bot import Bot
from models.amount import Amount
from config import Chains, Tokens
from config import Contracts
from core.onchain import Onchain
from models.chain import Chain
import requests
from utils.utils import to_checksum
import random

def get_gas_data(*chains: Chain):
    target_chains_id = [str(chain.chain_id) for chain in chains]
    url = 'https://gas.memebridge.app/api/v1/chainInfo'
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    meme_chains_id = ''
    manager = None
    meme_chains = data['data']['to']
    random.shuffle(meme_chains)

    for meme_chain in meme_chains:
        if meme_chain['chainID'] in target_chains_id:
            if manager is None:
                manager = meme_chain['manager']
            if manager != meme_chain['manager']:
                raise ValueError('Manager address is different')
            meme_chains_id += hex(meme_chain['id'])[2:]

    if len(meme_chains_id) / 2 != len(chains):
        raise ValueError('Chains count is different')

    input_data = '0x1' + hex(len(chains))[2:] + meme_chains_id
    return manager, input_data

def get_eth_price():
    url = 'https://gas.memebridge.app/api/v1/tokenPrice'
    response = requests.get(url)
    response.raise_for_status()
    return float(response.json()['data']['tokenPrice']['ETH'])

def send_gas(bot: Bot, amount_usdt: Amount, *chains: Chain, onchain: Onchain | None = None):
    """
    :param amount: Количество токенов в USDT
    """
    if onchain is None:
        onchain = bot.onchain

    total_amount_in_usdt = amount_usdt * len(chains)
    eth_price = get_eth_price()
    amount_eth = Amount(total_amount_in_usdt.ether / eth_price)

    manager, input_data = get_gas_data(*chains)

    rounded_fee = '000100000000'
    rounded_amount = int(str(amount_eth.wei)[:-len(rounded_fee)] + rounded_fee)
    rounded_amount = Amount(rounded_amount, wei=True)


    tx_params = onchain._prepare_tx(
        to_address=manager,
        value=rounded_amount
    )

    tx_params['data'] = input_data

    tx_params = onchain._estimate_gas(tx_params)
    tx_hash = onchain._sign_and_send(tx_params)
    logger.info(f"Транзакция отправлена! Tx hash: {tx_hash}")
    return tx_hash