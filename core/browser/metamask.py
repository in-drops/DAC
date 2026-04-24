import re
import time

from loguru import logger
from playwright.sync_api import Locator
import pyperclip
from core.browser.ads import Ads
from core.excel import Excel
from config import config
from models.account import Account
from models.chain import Chain
from utils.utils import random_sleep, generate_password, write_text_to_file

class Metamask:
    """
    Класс для работы с metamask v.13.00.0
    """

    def __init__(self, ads: Ads, account: Account, excel: Excel) -> None:
        self._url = config.metamask_url
        self.ads = ads
        self.password = account.password
        self.seed = account.seed
        self.excel = excel

    def open_metamask(self):

        self.ads.open_url(self._url)
        random_sleep(5, 10)

    def create_wallet(self) -> tuple[str, str, str]:

        self.open_metamask()
        try:
            self.ads.page.get_by_test_id('onboarding-get-started-button').wait_for(state='visible')
        except:
            raise Exception(f"{self.ads.profile_number} Ошибка создания кошелька MetaMask! Удалите расширение в профиле ADS и перезапустите софт...")

        self.ads.page.locator('.dropdown').click()
        random_sleep(1, 3)
        self.ads.page.locator('.dropdown__select').select_option(value=["en"])
        random_sleep(1, 3)
        self.ads.page.locator('.dropdown__select').click()
        random_sleep(1, 3)
        self.ads.page.get_by_test_id('onboarding-get-started-button').click()
        random_sleep(3, 5)
        if self.ads.page.get_by_role('dialog').get_by_test_id('terms-of-use-checkbox').is_visible():
            self.ads.page.get_by_role('dialog').get_by_test_id('terms-of-use-checkbox').click()
            random_sleep(1, 3)
            for _ in range(20):
                self.ads.page.get_by_test_id('terms-of-use-scroll-button').click()
                time.sleep(0.3)
                if self.ads.page.get_by_role('dialog').get_by_role('button', name='Agree').is_enabled():
                    random_sleep(1, 3)
                    self.ads.page.get_by_role('dialog').get_by_role('button', name='Agree').click()
                    break
                time.sleep(0.5)
            random_sleep(1, 3)

        self.ads.page.get_by_test_id('onboarding-create-wallet').click()
        random_sleep(1, 3)
        if self.ads.page.get_by_test_id('onboarding-create-with-srp-button').count():
            self.ads.page.get_by_test_id('onboarding-create-with-srp-button').click()

        random_sleep(3, 5)
        if not self.password:
            self.password = generate_password()
        self.ads.page.get_by_test_id('create-password-new-input').fill(self.password)
        random_sleep(1, 3)
        self.ads.page.get_by_test_id('create-password-confirm-input').fill(self.password)
        random_sleep(1, 3)
        self.ads.page.get_by_test_id('create-password-terms').click()
        random_sleep(1, 3)
        self.ads.page.get_by_test_id('create-password-submit').click()
        random_sleep(1, 3)
        self.ads.page.get_by_test_id('secure-wallet-recommended').click()
        random_sleep(1, 3)
        self.ads.page.get_by_test_id('recovery-phrase-reveal').click()

        seed = []
        for i in range(12):
            test_id = f"recovery-phrase-chip-{i}"
            raw_text = self.ads.page.get_by_test_id(test_id).inner_text()
            word = raw_text.strip().split()[-1]
            seed.append(word)

        self.ads.page.get_by_test_id('recovery-phrase-continue').click()
        random_sleep(1, 3)

        for i in range(12):
            button = self.ads.page.get_by_test_id(f'recovery-phrase-quiz-unanswered-{i}')
            if button.count():
                # Кнопка есть → это пустое поле → кликаем
                button.click()
                random_sleep(0.2, 0.4)
        random_sleep(1, 3)
        self.ads.page.get_by_test_id('recovery-phrase-confirm').click()
        random_sleep(3, 5)
        self.ads.page.get_by_test_id('confirm-srp-modal-button').click()
        random_sleep(1, 3)

        if self.ads.page.get_by_test_id('metametrics-data-collection-checkbox').is_visible():
            self.ads.page.get_by_test_id('metametrics-data-collection-checkbox').click()
            random_sleep(1, 3)
            self.ads.page.get_by_role('button', name='I agree').click()

        random_sleep(3, 5)
        self.ads.click_if_exists(method='test_id', value='onboarding-complete-done')
        random_sleep(5, 7)
        self.ads.click_if_exists(method='test_id', value='pin-extension-done')
        random_sleep(3, 5)

        if self.ads.page.get_by_role('dialog').filter(has_text='Solana').count():
            self.ads.page.get_by_role('dialog').get_by_test_id('not-now-button').click()
            random_sleep(1, 3)

        self.ads.click_if_exists(self.ads.page.get_by_role('button', name='Got it'))
        random_sleep(1, 3)

        address = self.get_address()
        seed_str = " ".join(seed)
        self.excel.set_cell('Address', address)
        self.excel.set_cell('Seed', seed_str)
        self.excel.set_cell('Password', self.password)

        return address, seed_str, self.password

    def import_wallet(self) -> tuple[str, str, str]:

        self.open_metamask()

        seed_list = self.seed.split(" ")
        if not self.password:
            self.password = generate_password()
        try:
            self.ads.page.get_by_test_id('onboarding-get-started-button').wait_for(state='visible', timeout=10000)
            self.ads.page.locator('.dropdown').click()
            random_sleep(1, 3)
            self.ads.page.locator('.dropdown__select').select_option(value=["en"])
            random_sleep(1, 3)
            self.ads.page.locator('.dropdown__select').click()
            random_sleep(1, 3)
            self.ads.page.get_by_test_id('onboarding-get-started-button').click()
            random_sleep(3, 5)
            if self.ads.page.get_by_role('dialog').get_by_test_id('terms-of-use-checkbox').is_visible():
                self.ads.page.get_by_role('dialog').get_by_test_id('terms-of-use-checkbox').click()
                random_sleep(1, 3)
                for _ in range(20):
                    self.ads.page.get_by_test_id('terms-of-use-scroll-button').click()
                    time.sleep(0.3)
                    if self.ads.page.get_by_role('dialog').get_by_role('button', name='Agree').is_enabled():
                        random_sleep(1, 3)
                        self.ads.page.get_by_role('dialog').get_by_role('button', name='Agree').click()
                        break
                    time.sleep(0.5)
                random_sleep(1, 3)

            self.ads.page.get_by_test_id('onboarding-import-wallet').click()
            random_sleep(1, 3)
            if self.ads.page.get_by_test_id('onboarding-import-with-srp-button').count():
                self.ads.page.get_by_test_id('onboarding-import-with-srp-button').click()
            input_area = self.ads.page.get_by_test_id('srp-input-import__srp-note')
            input_area.click()
            input_area.type(seed_list[0] + " ", delay=50)
            random_sleep(0.5, 1)
            # Вводим оставшиеся 11 слов с пробелами
            for i in range(1, 12):
                input_field = self.ads.page.get_by_test_id(f"import-srp__srp-word-{i}")
                input_field.wait_for(state="visible", timeout=5000)
                input_field.type(seed_list[i] + " ", delay=50)  # вместо .fill
                random_sleep(0.2, 0.5)
            self.ads.page.get_by_test_id('import-srp-confirm').click()
            random_sleep(3, 5)
            self.ads.page.get_by_test_id('create-password-new-input').fill(self.password)
            random_sleep(1, 3)
            self.ads.page.get_by_test_id('create-password-confirm-input').fill(self.password)
            random_sleep(1, 3)

            self.ads.page.get_by_test_id('create-password-terms').click()
            random_sleep(1, 3)
            self.ads.page.get_by_test_id('create-password-submit').click()
            random_sleep(3, 5)

            if self.ads.page.get_by_test_id('metametrics-data-collection-checkbox').is_visible():
                self.ads.page.get_by_test_id('metametrics-data-collection-checkbox').click()
                random_sleep(1, 3)
                self.ads.page.get_by_role('button', name='I agree').click()
                random_sleep(3, 5)

            self.ads.click_if_exists(method='test_id', value='onboarding-complete-done')
            random_sleep(5, 7)
            self.ads.click_if_exists(method='test_id', value='pin-extension-done')
            random_sleep(3, 5)

        except:
            logger.warning(f"{self.ads.profile_number}: В Metamask уже имеется счет! Делаем сброс и импортируем новый.")
            self.ads.page.get_by_text('Forgot password?').click()
            random_sleep(3, 5)
            self.ads.page.get_by_test_id('reset-password-modal-button').click()
            random_sleep(3, 5)
            for i, word in enumerate(seed_list):
                self.ads.page.get_by_test_id(f"import-srp__srp-word-{i}").fill(word)
            self.ads.page.get_by_test_id('create-vault-password').fill(self.password)
            random_sleep(1, 3)
            self.ads.page.get_by_test_id('create-vault-confirm-password').fill(self.password)
            random_sleep(1, 3)
            self.ads.page.get_by_test_id('create-new-vault-submit-button').click()
            random_sleep(5, 7)

        if self.ads.page.get_by_role('dialog').filter(has_text='Solana').count():
            self.ads.page.get_by_role('dialog').get_by_test_id('not-now-button').click()
            random_sleep(1, 3)
        self.ads.click_if_exists(self.ads.page.get_by_role('button', name='Got it'))
        address = self.get_address()
        self.excel.set_cell('Address', address)
        self.excel.set_cell('Password', self.password)
        seed_str = " ".join(seed_list)
        return address, seed_str, self.password

    def get_address(self) -> str:

        self.ads.page.get_by_test_id('account-options-menu-button').click()
        random_sleep(1, 3)
        self.ads.page.get_by_test_id('account-list-menu-details').click()
        random_sleep(3, 5)
        self.ads.page.get_by_test_id('account-details-row-address').click()
        random_sleep(3, 5)
        address = self.ads.page.locator('.qr-code__address-segments').inner_text().replace('\n', '')
        return address

    def auth_metamask_evm(self) -> None:

        self.open_metamask()
        if not self.password:
            raise Exception(f"{self.ads.profile_number}: Не указан пароль для авторизации в Metamask!")

        try:
            self.ads.page.get_by_test_id('unlock-password').wait_for(timeout=10000, state='visible')
            self.ads.page.get_by_test_id('unlock-password').fill(self.password)
            random_sleep(3, 5)
            self.ads.page.get_by_test_id('unlock-submit').click()
            random_sleep(5, 7)
            if self.ads.page.get_by_role('dialog').filter(has_text='Solana').count():
                self.ads.page.get_by_role('dialog').get_by_test_id('not-now-button').click()
                random_sleep(1, 3)
        except:
            pass


        if self.ads.page.get_by_role('dialog').get_by_role('button', name='Remind me later').count():
            self.ads.page.get_by_role('dialog').get_by_role('button', name='Remind me later').click()
            random_sleep(1, 3)

        try:
            if self.ads.page.get_by_test_id('account-menu-icon').filter(has_not_text='Solana').count():
                logger.info(f"{self.ads.profile_number}: Успешная авторизация в Metamask Wallet EVM!")

            else:
                self.ads.page.get_by_test_id('account-menu-icon').click()
                random_sleep(1, 3)
                self.ads.page.get_by_test_id('account-item').filter(has_not_text='Solana').nth(0).click()
                random_sleep(1, 3)
                if self.ads.page.get_by_test_id('account-menu-icon').filter(has_not_text='Solana').count():
                    logger.info(f"{self.ads.profile_number}: Успешная авторизация в Metamask Wallet EVM!")
                    random_sleep(1, 3)

        except Exception:
            logger.error(f"{self.ads.profile_number}: Ошибка авторизации в Metamask Wallet EVM!")
            raise Exception

    def auth_metamask_solana(self) -> None:

        self.open_metamask()
        if not self.password:
            raise Exception(f"{self.ads.profile_number}: Не указан пароль для авторизации в Metamask!")

        try:
            self.ads.page.get_by_test_id('unlock-password').wait_for(timeout=10000, state='visible')
            self.ads.page.get_by_test_id('unlock-password').fill(self.password)
            random_sleep(3, 5)
            self.ads.page.get_by_test_id('unlock-submit').click()
            random_sleep(5, 7)
            if self.ads.page.get_by_role('dialog').filter(has_text='Solana').count():
                self.ads.page.get_by_role('dialog').get_by_test_id('not-now-button').click()
                random_sleep(1, 3)
        except:
            pass

        if self.ads.page.get_by_role('dialog').get_by_role('button', name='Remind me later').count():
            self.ads.page.get_by_role('dialog').get_by_role('button', name='Remind me later').click()
            random_sleep(1, 3)

        try:
            if self.ads.page.get_by_test_id('account-menu-icon').filter(has_text='Solana').count():
                logger.info(f"{self.ads.profile_number}: Успешная авторизация в Metamask Wallet Solana!")

            else:
                self.ads.page.get_by_test_id('account-menu-icon').click()
                random_sleep(1, 3)
                self.ads.page.get_by_test_id('account-item').filter(has_text='Solana').nth(0).click()
                random_sleep(1, 3)
                if self.ads.page.get_by_test_id('account-menu-icon').filter(has_text='Solana').count():
                    logger.info(f"{self.ads.profile_number}: Успешная авторизация в Metamask Wallet Solana!")
                    random_sleep(1, 3)

        except Exception:
            logger.error(f"{self.ads.profile_number}: Ошибка авторизации в Metamask Wallet Solana!")
            raise Exception

    def select_chain(self, chain: Chain) -> None:

        self.open_metamask()
        try:
            self.ads.page.get_by_test_id('account-options-menu-button').wait_for(timeout=30000, state='visible')
            random_sleep(1, 2)
            self.ads.page.get_by_test_id('account-options-menu-button').click()
            random_sleep(1, 2)
            self.ads.page.get_by_test_id('global-menu-networks').click()
            random_sleep(1, 2)

        except Exception:
            logger.error(f"{self.ads.profile_number}: Ошибка при открытии списка сетей в Metamask Wallet!")
            raise Exception

        try:
            enabled_networks = self.ads.page.locator('div[data-rbd-droppable-id="characters"]')
            if enabled_networks.get_by_text(chain.metamask_name, exact=True).count():
                logger.info(f'Сеть {chain.metamask_name} присутствует в списке сетей Metamask Wallet!')
                self.ads.page.locator('header').locator('//span[contains(@style, "close")]').click()
                random_sleep(1, 2)

            else:
                self.set_chain(chain)

        except Exception:
            logger.error(
                f"{self.ads.profile_number}: Ошибка при добавлении сети {chain.metamask_name} в Metamask Wallet!")

    def set_chain(self, chain: Chain) -> None:

        try:
            self.ads.page.reload()
            self.ads.page.get_by_test_id('account-options-menu-button').wait_for(timeout=30000, state='visible')
            random_sleep(1, 2)
            self.ads.page.get_by_test_id('account-options-menu-button').click()
            random_sleep(1, 2)
            self.ads.page.get_by_test_id('global-menu-networks').click()
            random_sleep(1, 2)
            self.ads.page.get_by_role('button', name='Add a custom network').click()

            # заполняем первую часть полей
            self._set_chain_data(chain)

            # проверяем, есть ли ошибка с chain_id
            if self.ads.page.get_by_test_id('network-form-chain-id-error').count():
                raise Exception(
                    f'Error: {self.ads.profile_number} Metamask не принимает RPC {chain.rpc}, попробуйте другой')

            # заполняем chain_id и проверяем, есть ли уже сеть с таким id
            self.ads.page.get_by_test_id('network-form-chain-id').fill(str(chain.chain_id))

            # есть ли уже сеть с таким id
            if self.ads.page.get_by_test_id('network-form-chain-id-error').count():
                self.ads.page.get_by_test_id('network-form-chain-id-error').get_by_role('button').click()
                self._set_chain_data(chain)

            # заполняем оставшиеся поля
            self.ads.page.get_by_test_id('network-form-ticker-input').fill(chain.native_token)
            self.ads.page.locator('section').locator('div.networks-tab__network-form__footer').get_by_role(
                'button').click()
            for _ in range(30):
                if self.ads.page.get_by_text('was successfully').count():
                    logger.info(f'Сеть {chain.metamask_name} успешно добавлена в Metamask Wallet!')
                    break
                time.sleep(0.5)
        except Exception:
            logger.error(f'Не удалось добавить сеть {chain.metamask_name} в Metamask Wallet!')
            raise Exception

    def _set_chain_data(self, chain: Chain) -> None:

        self.ads.page.get_by_test_id('network-form-network-name').fill(chain.metamask_name)
        self.ads.page.get_by_test_id('test-add-rpc-drop-down').click()
        time.sleep(0.5)

        while self.ads.page.get_by_role('tooltip').get_by_label('Delete').is_visible():
            self.ads.page.get_by_role('tooltip').get_by_label('Delete').nth(0).click()
            random_sleep(3, 5)

        self.ads.page.locator('section').get_by_role('button', name='Add RPC URL').filter(
            has_not=self.ads.page.locator('span')
        ).click()

        self.ads.page.get_by_test_id('rpc-url-input-test').fill(chain.rpc)
        self.ads.page.locator('section').get_by_role('button', name='Add URL').click()


    # def wait_for_wallet_page(self, timeout=10):
    #     """
    #     Ждет появления окна кошелька и возвращает его страницу.
    #     """
    #
    #     for _ in range(int(timeout * 2)):  # проверка каждые 0.5 сек
    #         for page in self.ads.context.pages:
    #             title = ""
    #             try:
    #                 title = page.title() or ""
    #             except:
    #                 pass
    #
    #             if "MetaMask" in title:
    #                 # logger.success("Окно Metamask Wallet найдено! ✅")
    #                 return page
    #
    #         time.sleep(0.5)
    #
    #     return None

    # def universal_confirm(self, windows: int = 1, buttons: int = 1) -> None:
    #     '''Подтверждение транзакций в кошельке'''
    #
    #     for _ in range(windows):
    #         time.sleep(5)
    #
    #         wallet_page = self.wait_for_wallet_page()
    #
    #         if wallet_page:
    #             # logger.success("Окно Metamask Wallet найдено! ✅")
    #             pass
    #         else:
    #             logger.error("Не удалось найти окно Metamask Wallet! ")
    #             return
    #         buttons_name = [
    #             'confirm-btn',
    #             'confirm-sign-message-confirm-snap-footer-button',
    #             'confirm-footer-button',
    #             'smart-transaction-status-page-footer-close-button',
    #             'page-container-footer-next',
    #             'confirmation-submit-button'
    #
    #         ]
    #
    #         clicked = False
    #         for __ in range(buttons):
    #             for button in buttons_name:
    #                 if wallet_page.get_by_test_id(button).count():
    #                     time.sleep(0.5)
    #                     wallet_page.get_by_test_id(button).click()
    #                     logger.info('Успешно подтверждено в Metamask Wallet!')
    #                     clicked = True
    #                     break
    #
    #                 if wallet_page.locator('button', has_text='Review alert').count():
    #                     wallet_page.get_by_test_id('confirm-footer-cancel-button').click()
    #                     time.sleep(0.5)
    #                     logger.error(
    #                         f'{self.ads.profile_number} Ошибка "Review Alert" в Metamask! Возможно не хватает средств для оплаты транзакции...')
    #                     clicked = True
    #                     break
    #             time.sleep(1)
    #
    #         if not clicked:
    #             logger.error(
    #                 f'{self.ads.profile_number} Не найдена ни одна кнопка подтверждения в Metamask!'
    #             )
    #
    #         random_sleep(1)
    #
    #         wallet_page.close()



    def universal_confirm(self, windows: int = 1, buttons: int = 1) -> None:

        for _ in range(windows):
            random_sleep(5, 10)
            mm_page = self.ads.context.new_page()
            mm_page.goto(self._url)
            buttons_name = [
                'confirm-btn',
                'confirm-sign-message-confirm-snap-footer-button',
                'confirm-footer-button',
                'smart-transaction-status-page-footer-close-button',
                'page-container-footer-next',
                'confirmation-submit-button'

            ]

            if mm_page.get_by_text("Review Permissions").count():
                mm_page.get_by_test_id('page-container-footer-next').click()
                time.sleep(1)
                mm_page.close()
                random_sleep(5, 10)
                mm_page = self.ads.context.new_page()
                mm_page.goto(self._url)

            for __ in range(buttons):
                for button in buttons_name:
                    if mm_page.get_by_test_id(button).count():
                        mm_page.get_by_test_id(button).click()
                        logger.info(f'{self.ads.profile_number} Успешно подтверждено в Metamask!')
                        break
                    else:
                        if mm_page.locator('button', has_text='Review alert').count():
                            mm_page.get_by_test_id('confirm-footer-cancel-button').click()
                            logger.error(f'{self.ads.profile_number} Ошибка "Review Alert" в Metamask! Возможно не хватает средств для оплаты транзакции...')

            mm_page.close()


    # def universal_confirm(self, windows: int = 1, buttons: int = 1) -> None:
    #
    #     for _ in range(windows):
    #         random_sleep(5, 10)
    #         mm_page = self.ads.context.new_page()
    #         mm_page.goto(self._url)
    #
    #         buttons_name = [
    #             'confirm-btn',
    #             'confirm-sign-message-confirm-snap-footer-button',
    #             'confirm-footer-button',
    #             'smart-transaction-status-page-footer-close-button',
    #             'page-container-footer-next',
    #             'confirmation-submit-button'
    #
    #         ]
    #
    #         for __ in range(buttons):
    #             confirmed = False
    #
    #             for button in buttons_name:
    #                 try:
    #                     mm_page.get_by_test_id(button).wait_for(timeout=5000)
    #                     mm_page.get_by_test_id(button).click()
    #                     logger.info(f'{self.ads.profile_number} Успешно подтверждено в Metamask!')
    #                     confirmed = True
    #                     break
    #                 except:
    #                     continue
    #
    #             if confirmed:
    #                 continue  # переходим к следующей кнопке
    #
    #             # Если не подтвердилось, ищем Review alert
    #             if mm_page.locator('button', has_text='Review alert').count():
    #                 logger.warning(
    #                     f'{self.ads.profile_number} Обнаружен "Review Alert" в Metamask! Ждём возможную загрузку кнопки...')
    #
    #                 for attempt in range(3):
    #                     random_sleep(5, 7)
    #                     for button in buttons_name:
    #                         try:
    #                             mm_page.get_by_test_id(button).wait_for(timeout=2000)
    #                             mm_page.get_by_test_id(button).click()
    #                             logger.info(f'{self.ads.profile_number} Успешно подтверждено в Metamask!!')
    #                             confirmed = True
    #                             break
    #                         except:
    #                             continue
    #                     if confirmed:
    #                         break  # выходим из троекратной попытки
    #
    #                 if not confirmed:
    #                     # Три попытки прошли, кнопка так и не появилась — жмём cancel
    #                     try:
    #                         mm_page.get_by_test_id('confirm-footer-cancel-button').click()
    #                         logger.error(
    #                             f'{self.ads.profile_number} Отмена транзакции: "Review Alert" не прошёл, подтверждение не появилось.')
    #                     except:
    #                         logger.error(
    #                             f'{self.ads.profile_number} Не удалось нажать "Cancel" в Metamask - кнопка не найдена.')
    #
    #         mm_page.close()

