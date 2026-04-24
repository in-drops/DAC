"""
Connect -> WALLET -> Rabby Wallet -> universal_confirm
Запуск: python snippets/click_connect.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config
from utils.utils import get_accounts, random_sleep
from utils.logging import init_logger
from core.browser.ads import Ads
from core.browser.rabby import Rabby
from core.excel import Excel
from loguru import logger

PROFILE_NUMBER = 60


def connect_wallet(ads: Ads, rabby: Rabby):
    page = ads.page

    # Клик Connect
    connect_btn = page.get_by_role('button', name='Connect')
    if connect_btn.count():
        logger.info("Нажимаю Connect...")
        connect_btn.click()
        random_sleep(2, 3)

    # Клик WALLET
    wallet_btn = page.locator('button', has_text='WALLET')
    if wallet_btn.count():
        logger.info("Выбираю WALLET...")
        wallet_btn.first.click()
        random_sleep(2, 3)

    # Клик Rabby
    for text in ['Rabby', 'rabby']:
        el = page.locator(f'text={text}')
        if el.count():
            logger.info("Выбираю Rabby Wallet...")
            el.first.click()
            random_sleep(2, 3)
            break

    # Подтверждаем через Rabby
    logger.info("Подтверждаю через Rabby universal_confirm...")
    rabby.universal_confirm(windows=1, buttons=1)
    logger.success("Кошелёк подключён!")


def main():
    init_logger()
    config.is_browser_run = True

    accounts = get_accounts()
    account = next((a for a in accounts if a.profile_number == PROFILE_NUMBER), None)
    if not account:
        logger.error(f"Профиль #{PROFILE_NUMBER} не найден!")
        return

    ads = Ads(account)
    excel = Excel(account)
    rabby = Rabby(ads, account, excel)

    connect_wallet(ads, rabby)

    random_sleep(2, 3)
    ads.open_url('https://inception.dachain.io/dashboard')
    logger.info(f"Страница: {ads.page.url}")

    ads.close_browser()


if __name__ == '__main__':
    main()
