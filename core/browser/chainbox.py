import time
from typing import Optional

from loguru import logger
from playwright.sync_api import Page

from core.browser.ads import Ads
from models.account import Account
from utils.utils import random_sleep, generate_password


class Chainbox:
    """
    Класс для работы с Chainbox Wallet
    Extension ID: fafipkjpodjefcmagnidcibkhlgajann

    Флоу import_wallet():
      #/start           → кнопка (link) "Import wallet"
      #/init/import_phrase → textarea placeholder='Please input' → кнопка "Next"
      #/init/import_phrase → 2x input[type=password] → кнопка "Encrypted Storage"
      → редирект на #/unlock (кошелёк создан)

    Флоу auth_wallet():
      #/unlock → input[type=password] placeholder='Please enter your password'
               → кнопка "Unlock"
      → редирект на #/ (главный экран)
    """

    EXTENSION_ID = 'fafipkjpodjefcmagnidcibkhlgajann'

    def __init__(self, ads: Ads, account: Account) -> None:
        self._url = f'chrome-extension://{self.EXTENSION_ID}/popup.html'
        self.ads = ads
        self.password = account.password
        self.seed = account.seed

    def _goto_extension(self, url: str) -> None:
        """Навигация к chrome-extension URL через CDP (игнорирует ошибку None-response)"""
        try:
            if self.ads.page.is_closed():
                self.ads.page = self.ads.context.new_page()
            self.ads.page.goto(url, wait_until='domcontentloaded')
        except AttributeError:
            # Playwright CDP-баг: chrome-extension goto возвращает None вместо Response
            pass
        except Exception as e:
            if 'closed' in str(e).lower() or 'target' in str(e).lower():
                self.ads.page = self.ads.context.new_page()
                try:
                    self.ads.page.goto(url, wait_until='domcontentloaded')
                except AttributeError:
                    pass
            else:
                raise e

    def open_wallet(self) -> None:
        """Открытие страницы кошелька"""
        self._goto_extension(self._url)
        random_sleep(2, 3)

    def import_wallet(self) -> None:
        """Импорт кошелька по сид-фразе (12 слов одной строкой)"""

        url_start = f'chrome-extension://{self.EXTENSION_ID}/popup.html#/start'
        self._goto_extension(url_start)

        if not self.password:
            self.password = generate_password()

        random_sleep(3, 5)

        # Если страница закрылась после навигации — переоткрываем
        if self.ads.page.is_closed():
            self._goto_extension(url_start)
            random_sleep(3, 5)

        try:
            # Шаг 1: стартовый экран #/start
            # "Import wallet" — это <a>, а не <button>
            import_link = self.ads.page.get_by_role('link', name='Import wallet')
            import_link.wait_for(state='visible', timeout=15000)
            random_sleep(1, 2)
            import_link.click()
            random_sleep(2, 3)

            # Шаг 2: экран ввода seed-фразы #/init/import_phrase
            # поле — <textarea placeholder="Please input">
            seed_input = self.ads.page.locator('textarea[placeholder="Please input"]')
            seed_input.wait_for(state='visible', timeout=10000)
            random_sleep(0.5, 1)
            seed_input.click()
            random_sleep(0.5, 1)
            seed_input.fill(self.seed)
            random_sleep(1, 2)

            # Кнопка перехода к паролю
            self.ads.page.get_by_role('button', name='Next').click()
            random_sleep(2, 4)

            # Шаг 3: экран установки пароля (тот же URL, другой контент)
            # Два поля: Password и Confirm Password
            pw_inputs = self.ads.page.locator('input[type="password"]')
            pw_inputs.nth(0).wait_for(state='visible', timeout=10000)
            random_sleep(0.5, 1)
            pw_inputs.nth(0).fill(self.password)
            random_sleep(0.5, 1)
            pw_inputs.nth(1).fill(self.password)
            random_sleep(1, 2)

            # Кнопка подтверждения (создаёт кошелёк)
            self.ads.page.get_by_role('button', name='Encrypted Storage').click()
            random_sleep(5, 8)

            logger.success(f'{self.ads.profile_number}: Кошелёк Chainbox успешно импортирован! 🎯')

        except Exception as e:
            raise Exception(f'{self.ads.profile_number}: Ошибка импорта Chainbox: {e}')

    def remove_extension(self) -> None:
        """Удаление расширения через chrome://extensions (shadow DOM)"""
        try:
            self.ads.page.goto('chrome://extensions', wait_until='domcontentloaded')
            random_sleep(2, 3)

            removed = self.ads.page.evaluate(f"""
                () => {{
                    const manager = document.querySelector('extensions-manager');
                    if (!manager?.shadowRoot) return false;
                    const itemList = manager.shadowRoot.querySelector('extensions-item-list');
                    if (!itemList?.shadowRoot) return false;
                    const items = itemList.shadowRoot.querySelectorAll('extensions-item');
                    for (const item of items) {{
                        if (item.id === '{self.EXTENSION_ID}') {{
                            const removeBtn = item.shadowRoot?.querySelector('#removeButton');
                            if (removeBtn) {{ removeBtn.click(); return true; }}
                        }}
                    }}
                    return false;
                }}
            """)

            random_sleep(1, 2)

            # Подтверждение диалога удаления если появился
            confirm_btn = self.ads.page.get_by_role('button', name='Remove')
            if confirm_btn.is_visible():
                confirm_btn.click()
                random_sleep(1, 2)

            if removed:
                logger.success(f'{self.ads.profile_number}: Расширение Chainbox удалено! 🎯')
            else:
                logger.warning(f'⚠️ {self.ads.profile_number}: Расширение не найдено в профиле ADS')

        except Exception as e:
            logger.error(f'{self.ads.profile_number}: Ошибка удаления расширения: {e}')

    def reset_extension_storage(self) -> None:
        """Сброс хранилища расширения через service worker — возвращает к экрану #/start"""
        try:
            # Ищем service worker Chainbox
            worker = None
            for sw in self.ads.context.service_workers:
                if self.EXTENSION_ID in sw.url:
                    worker = sw
                    break

            if worker:
                # Очищаем chrome.storage + IndexedDB через service worker (общий origin расширения)
                worker.evaluate("""
                    async () => {
                        await chrome.storage.local.clear();
                        await chrome.storage.session.clear();
                        const dbs = await indexedDB.databases();
                        await Promise.all(dbs.map(db => new Promise((res, rej) => {
                            const req = indexedDB.deleteDatabase(db.name);
                            req.onsuccess = res;
                            req.onerror = rej;
                        })));
                    }
                """)
                random_sleep(1, 2)
                logger.info(f'{self.ads.profile_number}: chrome.storage + IndexedDB Chainbox сброшены через SW')
            else:
                logger.warning(f'⚠️ {self.ads.profile_number}: Service worker Chainbox не найден, пробуем UI-сброс')
                # Fallback: ищем уже открытую вкладку расширения (не создаём новую)
                ext_page = next((p for p in self.ads.context.pages if self.EXTENSION_ID in p.url), None)
                if ext_page:
                    ext_page.evaluate("""
                        async () => {
                            const dbs = await indexedDB.databases();
                            for (const db of dbs) indexedDB.deleteDatabase(db.name);
                            localStorage.clear();
                            sessionStorage.clear();
                        }
                    """)
                    random_sleep(1, 2)

            # Открываем Chainbox в текущей ads.page — должен показать #/start
            self._goto_extension(self._url)
            random_sleep(2, 3)

            # Если страница закрылась (window.close) — открываем заново
            try:
                current_url = self.ads.page.url
            except Exception:
                self.ads.page = self.ads.context.new_page()
                self._goto_extension(self._url)
                random_sleep(2, 3)

            logger.info(f'{self.ads.profile_number}: Chainbox сброшен, URL: {self.ads.page.url}')
        except Exception as e:
            raise Exception(f'{self.ads.profile_number}: Ошибка сброса Chainbox: {e}')

    def auth_wallet(self) -> None:
        """Авторизация (разблокировка) кошелька"""
        self.open_wallet()

        if not self.password:
            raise Exception(f'{self.ads.profile_number}: Не указан пароль для Chainbox!')

        try:
            # Экран #/unlock: input[type=password] placeholder='Please enter your password'
            password_input = self.ads.page.locator('input[type="password"]')
            if password_input.is_visible():
                password_input.fill(self.password)
                random_sleep(0.5, 1)
                self.ads.page.get_by_role('button', name='Unlock').click()
                random_sleep(2, 3)
                logger.info(f'{self.ads.profile_number}: Успешная авторизация в Chainbox!')
            else:
                logger.info(f'{self.ads.profile_number}: Chainbox уже разблокирован!')

        except Exception as e:
            logger.error(f'{self.ads.profile_number}: Ошибка авторизации Chainbox: {e}')

    def wait_for_popup(self, url_contains: str = None, timeout: int = 15,
                       seen_urls: set = None) -> Optional[Page]:
        """
        Ожидает popup-страницу Chainbox с хэш-роутом действия.
        Chainbox НЕ использует notification URL — открывает popup.html с хэшами:
          #/connection/wallet, #/switch_ethereum_chain, #/message/sign,
          #/sign/..., #/transaction/..., #/approval/...

        seen_urls — множество уже обработанных URL (не page ID!), т.к. Chainbox может
        менять хэш одного и того же окна (напр. /switch_ethereum_chain → /message/sign).
        """
        popup_hashes = ['/connection/', '/message/', '/sign/', '/transaction/', '/approval/',
                        '/switch_ethereum_chain', '/add_ethereum_chain']

        for _ in range(timeout):
            for page in self.ads.context.pages:
                try:
                    url = page.url
                except Exception:
                    continue
                if seen_urls and url in seen_urls:
                    continue
                if 'chrome-extension://' not in url or self.EXTENSION_ID not in url:
                    continue
                if url_contains:
                    if url_contains.lower() in url.lower():
                        return page
                else:
                    for pattern in popup_hashes:
                        if pattern in url:
                            return page
            time.sleep(1)
        return None

    def universal_confirm(self, windows: int = 1) -> None:
        """
        Подтверждение popup-запросов Chainbox.
        Обрабатывает: connection, chain switch, sign message, transaction, approval.

        Кнопки по типу popup (из тестирования task.simplechain.com):
          #/connection/wallet       → Connect
          #/switch_ethereum_chain   → Agree
          #/add_ethereum_chain      → Agree
          #/message/sign            → Confirm  (Signature Request — sign in)
          #/sign/...                → Sign, Confirm
          #/transaction/...         → Confirm, Approve
          #/approval/...            → Approve, Confirm
        """
        btn_map = {
            '/connection/': ['Connect', 'Allow', 'Confirm'],
            '/switch_ethereum_chain': ['Agree', 'Allow', 'Confirm'],
            '/add_ethereum_chain': ['Agree', 'Allow', 'Confirm'],
            '/message/': ['Confirm', 'Sign', 'OK'],
            '/sign/': ['Sign', 'Confirm', 'OK'],
            '/transaction/': ['Confirm', 'Approve', 'OK'],
            '/approval/': ['Approve', 'Confirm', 'Allow'],
        }
        default_candidates = ['Connect', 'Agree', 'Confirm', 'Sign', 'Approve', 'Allow', 'OK']

        seen_urls: set = set()

        for i in range(windows):
            if i > 0:
                random_sleep(1, 2)

            popup_page = self.wait_for_popup(timeout=60, seen_urls=seen_urls)
            if not popup_page:
                logger.warning(f'{self.ads.profile_number}: Chainbox popup #{i + 1} не найден')
                return

            url = popup_page.url
            seen_urls.add(url)
            logger.info(f'{self.ads.profile_number}: Chainbox popup #{i + 1}: {url}')

            # Определяем нужные кнопки по URL
            candidates = default_candidates
            for pattern, btns in btn_map.items():
                if pattern in url:
                    candidates = btns
                    break

            clicked = False
            for btn_name in candidates:
                try:
                    btn = popup_page.get_by_role('button', name=btn_name)
                    if btn.count() > 0 and btn.first.is_visible():
                        # Ждём пока кнопка станет enabled (до 30 сек)
                        for __ in range(30):
                            if btn.first.is_enabled():
                                break
                            time.sleep(1)
                        btn.first.click()
                        random_sleep(2, 3)
                        clicked = True
                        logger.success(f'{self.ads.profile_number}: Chainbox подтверждено: "{btn_name}"')
                        break
                except Exception:
                    pass

            if not clicked:
                logger.warning(f'{self.ads.profile_number}: Chainbox popup автоподтверждён или кнопка исчезла. URL: {url}')
