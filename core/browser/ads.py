from __future__ import annotations
import json
import math
import random
from typing import Optional, Literal, List
import requests
from config.settings import config
from models.account import Account
from utils.utils import random_sleep, get_response
from playwright.sync_api import sync_playwright, Browser, Page, Locator, Playwright, Frame
from loguru import logger


class Ads:
    # _local_api_url = 'http://127.0.0.1:50325/api/v1/'
    _local_api_url = 'http://local.adspower.net:50325/api/v1/'

    def __init__(self, account: Account):
        self.profile_number = account.profile_number
        self.proxy = account.proxy
        self._profile_id = None  # id профиля в ADS, реализован геттер profile_id
        self._user_agent = None  # user_agent браузера, реализован геттер user_agent

        # if config.set_proxy:
        #     self.proxy = account.proxy
        #     self._set_proxy()

        if not config.is_browser_run:
            return

        self.pw: Optional[Playwright] = None
        self._browser = self._start_browser()
        self.context = self._browser.contexts[0]
        self.page = self.context.new_page()
        self._prepare_browser()

        if config.is_mobile_proxy:
            get_response(config.link_change_ip, attempts=1, return_except=False)

        # if config.check_proxy:
        #     self._check_proxy()

    @property
    def profile_id(self) -> str:
        if not self._profile_id:
            self._profile_id = self._get_profile_id()
        return self._profile_id

    @property
    def user_agent(self) -> str:

        if not self._user_agent:
            self._user_agent = self.page.evaluate('navigator.userAgent')
        return self._user_agent

    def _open_browser(self) -> str:

        params = dict(serial_number=self.profile_number)
        url = self._local_api_url + 'browser/start'
        random_sleep(1, 2)
        try:
            data = get_response(url, params)
            return data['data']['ws']['puppeteer']
        except Exception as e:
            logger.error(f'{self.profile_number} Ошибка при открытии браузера: {e}')
            raise e

    def _check_browser_status(self) -> Optional[str]:

        params = dict(serial_number=self.profile_number)
        url = self._local_api_url + 'browser/active'
        random_sleep(1, 2)
        try:
            data = get_response(url, params)
            if data['data']['status'] == 'Active':
                logger.info(f'{self.profile_number} Браузер уже активен!')
                return data['data']['ws']['puppeteer']
            return None
        except Exception as e:
            logger.error(f'{self.profile_number} Ошибка при проверке статуса браузера (запущен ли ADS?: {e} ')
            raise e

    def _start_browser(self) -> Browser:

        for attempt in range(3):
            try:
                # Проверяем статус браузера и запускаем его, если не активен
                if not (endpoint := self._check_browser_status()):
                    logger.info(f'{self.profile_number} Запускаем браузер!')
                    random_sleep(3, 4)
                    endpoint = self._open_browser()

                # подключаемся к браузеру
                random_sleep(4, 5)
                self.pw = sync_playwright().start()
                slow_mo = random.randint(*config.speed)
                browser = self.pw.chromium.connect_over_cdp(endpoint, slow_mo=slow_mo)
                if browser.is_connected():
                    return browser
                logger.error(f'{self.profile_number} Error не удалось запустить браузер!')

            except Exception as e:
                logger.error(f'{self.profile_number} Error не удалось запустить браузер {e}')
                self.pw.stop() if self.pw else None
                # Если ECONNREFUSED — браузер завис в ADS, перезапускаем
                if 'ECONNREFUSED' in str(e) or 'connect' in str(e).lower():
                    logger.info(f'{self.profile_number} Браузер недоступен, останавливаем и перезапускаем...')
                    try:
                        requests.get(
                            self._local_api_url + 'browser/stop',
                            params={'serial_number': self.profile_number},
                            timeout=5
                        )
                    except Exception:
                        pass
                    random_sleep(5, 8)
                else:
                    random_sleep(5, 10)

        raise Exception(f'Error не удалось запустить браузер')

    def _prepare_browser(self) -> None:

        try:
            for page in self.context.pages:
                if 'offscreen' in page.url:
                    continue
                if page.url != self.page.url:
                    page.close()

        except Exception as e:
            logger.error(f'{self.profile_number} Ошибка при закрытии страниц: {e}')
            raise e

    def close_browser(self) -> None:

        if not config.is_browser_run:
            return

        if self._browser.is_connected():
            self._browser.close()

        self.pw.stop() if self.pw else None
        params = dict(serial_number=self.profile_number)
        url = self._local_api_url + 'browser/stop'
        random_sleep(1, 2)
        try:
            get_response(url, params)
        except Exception as e:
            logger.error(f'{self.profile_number} Ошибка при остановке браузера: {e}')
            raise e

    def catch_page(self, url_contains: str | list[str] = None, timeout: int = 10) -> \
            Optional[Page]:

        if isinstance(url_contains, str):
            url_contains = [url_contains]

        for attempt in range(timeout):
            for page in self.context.pages:
                for url in url_contains:
                    if url in page.url:
                        return page
                    if attempt and attempt % 3 == 0:
                        self.pages_context_reload()
                    random_sleep(1, 2)

        logger.warning(f'{self.profile_number} Ошибка страница не найдена: {url_contains}')
        return None

    def pages_context_reload(self) -> None:

        new_page = self.context.new_page()
        random_sleep(1, 2)
        new_page.close()

    def _set_proxy(self) -> None:

        try:
            ip, port, login, password = self.proxy.split(":")

            profile_id = self._get_profile_id()

            proxy_config = {
                "proxy_type": "http",
                "proxy_host": ip,
                "proxy_port": port,
                "proxy_user": login,
                "proxy_password": password,
                "proxy_soft": "other"
            }

            data = {
                "user_id": profile_id,
                "user_proxy_config": proxy_config
            }
            url = self._local_api_url + "user/update"
            response = requests.post(url, json=data, headers={"Content-Type": "application/json"})
            response.raise_for_status()
            logger.success(f"{self.profile_number}: Proxy успешно добавлен! IP: {ip}")
            random_sleep(2)

        except Exception as e:
            logger.error(f"{self.profile_number}: Ошибка установки Proxy: Проверьте корректность данных в 'accounts.xlsx'.")
            raise e

    def _get_profile_id(self) -> str:

        url = self._local_api_url + 'user/list'
        params = {'serial_number': self.profile_number}

        random_sleep(1, 2)
        try:
            data = get_response(url, params)
            return data['data']['list'][0]['user_id']
        except Exception as e:
            logger.error(f'{self.profile_number} Ошибка при получении id профиля: {e}')
            raise e

    def _check_proxy(self) -> None:

        try:
            ip, port, login, password = self.proxy.split(":")
            current_ip = self._get_ip()
            logger.success(f"{self.profile_number}: Текущий ip: {current_ip}")
            if current_ip != ip:
                raise Exception("Proxy не работает!")

        except Exception as e:
            if "'NoneType' object has no attribute 'split'" in str(e):
                logger.error(f"{self.profile_number}: Ошибка проверки Proxy: Проверьте корректность данных в 'accounts.xlsx'.")
                raise e

    def _get_ip(self) -> str:

        try:
            ip = self.page.evaluate('''
                        async () => {
                            const response = await fetch('https://api.ipify.org');
                            const data = await response.text();
                            return data;
                        }
                    ''')
        except Exception:
            logger.error(f'{self.profile_number} Ошибка при получении ip')
            self.page.goto('https://api.ipify.org/?format=json')
            random_sleep(1, 2)
            ip_text = self.page.locator('//pre').inner_text()  # парсим json и возвращаем ip
            ip = json.loads(ip_text)['ip']  # парсим json и возвращаем ip

        return ip

    def open_url(
            self,
            url: str,
            wait_until: Optional[
                Literal['commit', 'domcontentloaded', 'load', 'networkidle']
            ] = 'load',
            locator: Optional[Locator] = None,
            timeout: int = 30,
            attempts: int = 1,
            referer: Optional[str] = None,
    ) -> None:

        # Переводим время ожидания в миллисекунды, если передали секунды
        if timeout < 1000:
            timeout = timeout * 1000

        # Проверяем, если передана ссылка на расширение chrome
        if not url.startswith('chrome-extension'):
            # Проверяем и добавляем https:// если необходимо
            if not (url.startswith('http://') or url.startswith('https://')):
                url = f'https://{url}'

        # Проверяем, если одна из версий URL уже открыта
        if self.page.url != url:
            for attempt in range(attempts):
                try:
                    self.page.goto(url, wait_until=wait_until, timeout=timeout, referer=referer)
                    break
                except Exception as e:
                    if attempt == attempts - 1:
                        raise e
                    logger.error(f'{self.profile_number} Ошибка при открытии страницы {url}: {e}')
                    random_sleep(1, 2)

        # Если передан xpath, ждем элемент на странице заданное время
        if locator:
            locator.wait_for(state='visible', timeout=timeout)

    def click_if_exists(
            self,
            locator: Optional[Locator] = None,
            *,
            method: Optional[Literal['test_id', 'role', 'text']] = None,
            value: Optional[str] = None
    ) -> None:

        if not locator:
            match method:
                case 'test_id':
                    locator = self.page.get_by_test_id(value)
                case 'role':
                    role, name = value.split(':', 1)
                    locator = self.page.get_by_role(role, name=name)
                case 'text':
                    locator = self.page.get_by_text(value)
        random_sleep(2, 3)
        if locator.count():
            locator.click()

    def click_and_catch_page(self, locator: Locator, timeout: int = 30) -> Page:

        with self.context.expect_page(timeout=timeout * 1000) as page_catcher:
            locator.click()
        return page_catcher.value

    def get_text_with_clipboard(self, locator: Locator) -> str:

        import pyperclip

        old_clipboard = pyperclip.paste()
        # кликаем по элементу, чтобы скопировать текст в буфер обмена
        locator.click()
        # получаем текст из буфера обмена
        new_clipboard = pyperclip.paste()

        # восстанавливаем старое значение
        pyperclip.copy(old_clipboard)

        return new_clipboard

    def keyboard_emulation(self, locator: Locator, text: str, mistake: bool = False) -> None:

        for symbol in text:
            if mistake and random.randint(0, 10) > 8:
                random_symbol = random.choice('abcdefghijklmnopqrstuvwxyz')
                locator.press_sequentially(random_symbol)
                random_sleep(0.01, 0.1)
                locator.press('Backspace')
            locator.press_sequentially(symbol)
            random_sleep(0.01, 0.1)

    def dump_frame_tree(self, page: Optional[Page] = None) -> None:

        if not page:
            page = self.page
        self._dump_frame_tree(page.main_frame)

    def _dump_frame_tree(self, frame: Frame, indent: str = "") -> None:

        print(indent + frame.name + '@' + frame.url)
        for child in frame.child_frames:
            self._dump_frame_tree(child, indent + '    ')

    def get_browser_offsets(self):

        self.page.bring_to_front()

        browser_offsets = self.page.evaluate(
            """() => ({
                x: window.screenX,
                y: window.screenY
            })"""
        )

        header_height = self.page.evaluate(
            """() => window.outerHeight - window.innerHeight"""
        )

        viewport_offsets = {
            'x': browser_offsets['x'],
            'y': browser_offsets['y'] + header_height
        }

        return viewport_offsets

    def random_click(
            self,
            locator: Locator,
            manual_radius: float = None,
            modifiers: Optional[List[Literal["Alt", "Control", "Meta", "Shift"]]] = None
    ) -> None:

        box = locator.bounding_box()
        if box is None:
            raise Exception('Bounding box не найден!')
        width, height = box['width'], box['height']
        cx, cy = width / 2, height / 2
        radius = manual_radius if manual_radius is not None else min(width, height) / 2
        angle = random.uniform(0, 2 * math.pi)
        r = radius * math.sqrt(random.uniform(0, 1))
        rand_x = cx + r * math.cos(angle)
        rand_y = cy + r * math.sin(angle)
        locator.click(position={'x': rand_x, 'y': rand_y}, modifiers=modifiers)

    def wait_locator_state(
            self,
            locator: Locator | str,
            attempts: int = 30,
            negative: bool = False,
            equals: int | str | float | None = None,
            attribute: str | None = None
    ) -> bool:

        # Преобразуем строку в локатор, если необходимо
        locator = self.page.get_by_text(locator) if isinstance(locator, str) else locator

        for _ in range(attempts):
            random_sleep()
            try:
                # Проверяем наличие элемента
                element_present = locator.count() > 0

                # Если ожидаем исчезновение элемента
                if negative and element_present:
                    continue  # Элемент присутствует, ждём его исчезновения

                # Если ожидаем появление элемента
                if not negative and not element_present:
                    continue  # Элемент отсутствует, ждём его появления

                # Если указан параметр equals, проверяем значение
                if equals is not None:
                    if attribute:
                        # Сравниваем значение атрибута
                        element_value = locator.get_attribute(attribute)
                        if element_value is None or str(element_value).strip().lower() != str(
                                equals).strip().lower():
                            continue  # Значение атрибута не совпадает
                    else:
                        # Сравниваем текст элемента
                        element_text = locator.text_content()
                        if element_text is None or str(element_text).strip().lower() != str(
                                equals).strip().lower():
                            continue  # Текст не совпадает

                # Все условия выполнены
                return True

            except Exception as error:
                logger.error(f'{self.profile_number} Ошибка при проверке элемента: {error}')

        return False


    def soft_cookie_cleaner(self):
        """Чистит куки/хранилища только для текущего сайта, не затрагивая остальные сайты в браузере."""

        # Запоминаем текущий домен
        url = self.page.url
        domain = url.split("/")[2] if "://" in url else url

        # Получаем все куки в контексте
        all_cookies = self.context.cookies()

        # Оставляем только куки не относящиеся к текущему домену
        keep_cookies = [cookie for cookie in all_cookies if domain not in cookie.get("domain", "")]

        # Чистим все куки/хранилища только на текущем сайте
        self.page.context.clear_cookies()
        self.page.evaluate("localStorage.clear();")
        self.page.evaluate("sessionStorage.clear();")
        self.page.evaluate("""
            indexedDB.databases().then(dbs => {
                dbs.forEach(db => indexedDB.deleteDatabase(db.name));
            });
        """)

        # Возвращаем остальные куки (чтобы другие сайты не пострадали)
        if keep_cookies:
            self.context.add_cookies(keep_cookies)

        self.page.reload()
        random_sleep(5, 7)



    def hard_cookie_cleaner(self):
        """Полностью чистит все куки/хранилища во всём контексте (опасно для Gmail и других сайтов)."""
        self.context.clear_cookies()
        self.page.evaluate("localStorage.clear();")
        self.page.evaluate("sessionStorage.clear();")
        self.page.evaluate("""
            indexedDB.databases().then(dbs => {
                dbs.forEach(db => indexedDB.deleteDatabase(db.name));
            });
        """)
        self.page.reload()
        random_sleep(5, 7)