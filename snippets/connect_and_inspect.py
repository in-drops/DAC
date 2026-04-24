"""
Full flow: ADS #60 -> Rabby auth -> Connect WALLET Rabby -> universal_confirm -> Early Badge
Перехватывает запросы И ответы. Ctrl+C -> api_requests.json
Запуск: python snippets/connect_and_inspect.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import json

from config import config
from utils.utils import get_accounts, random_sleep
from utils.logging import init_logger
from core.browser.ads import Ads
from core.browser.rabby import Rabby
from core.excel import Excel
from loguru import logger

PROFILE_NUMBER = 60
SITE_URL = "https://inception.dachain.io/dashboard"
OUT_FILE = os.path.join(os.path.dirname(__file__), 'api_requests.json')

SKIP = ['.js', '.css', '.png', '.jpg', '.svg', '.ico', '.woff', '.ttf',
        'chrome-extension', 'google-analytics', 'datadog', 'sentry',
        'cloudflare', 'matomo', 'blob:', 'coinbase.com', 'fonts.g',
        'web3modal', 'walletconnect', 'pulse.wallet', 'hyperliquid']

captured_requests = {}   # url+method -> entry
captured_list = []


def log(text):
    sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()


def on_request(request):
    url = request.url
    if any(s in url for s in SKIP):
        return
    key = f"{request.method}:{url}"
    entry = {
        "method": request.method,
        "url": url,
        "post_data": request.post_data,
        "auth": request.headers.get("authorization", request.headers.get("Authorization", "")),
        "response_status": None,
        "response_body": None,
    }
    captured_requests[key] = entry
    captured_list.append(entry)
    line = f"[{request.method}] {url}"
    if request.post_data:
        line += f"\n  REQ: {request.post_data[:300]}"
    if entry["auth"]:
        line += f"\n  AUTH: {entry['auth'][:80]}"
    log(line)


def on_response(response):
    url = response.url
    if any(s in url for s in SKIP):
        return
    key = f"{response.request.method}:{url}"
    try:
        body = response.text()
    except Exception:
        body = ""
    entry = captured_requests.get(key)
    if entry:
        entry["response_status"] = response.status
        entry["response_body"] = body[:800]
    log(f"  <- {response.status} {url}\n  RESP: {body[:300]}")


def save():
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(captured_list, f, ensure_ascii=False, indent=2)
    logger.success(f"Сохранено {len(captured_list)} запросов -> {OUT_FILE}")


def main():
    init_logger()
    config.is_browser_run = True

    accounts = get_accounts()
    account = next((a for a in accounts if a.profile_number == PROFILE_NUMBER), None)
    if not account:
        logger.error(f"Профиль #{PROFILE_NUMBER} не найден!")
        return

    logger.info(f"Запуск профиля #{PROFILE_NUMBER} | {account.address}")
    ads = Ads(account)
    excel = Excel(account)
    rabby = Rabby(ads, account, excel)

    # Перехват на уровне контекста (все страницы)
    ads.context.on("request", on_request)
    ads.context.on("response", on_response)
    logger.info("Перехват запросов+ответов активен")

    # 1. Авторизация Rabby
    logger.info("Авторизация в Rabby...")
    rabby.auth_rabby()

    # 2. Открываем сайт
    logger.info(f"Открываю {SITE_URL}...")
    ads.open_url(SITE_URL, wait_until='domcontentloaded', timeout=60)
    random_sleep(3, 4)

    # 3. Connect
    page = ads.page
    connect_btn = page.get_by_role('button', name='Connect')
    if connect_btn.count():
        logger.info("Connect...")
        connect_btn.click()
        random_sleep(2, 3)

    # 4. WALLET
    wallet_btn = page.locator('button', has_text='WALLET')
    if wallet_btn.count():
        logger.info("WALLET...")
        wallet_btn.first.click()
        random_sleep(2, 3)

    # 5. Rabby Wallet
    for text in ['Rabby Wallet', 'Rabby']:
        el = page.locator(f'text={text}')
        if el.count():
            logger.info(f"Выбираю: {text}")
            el.first.click()
            random_sleep(2, 3)
            break

    # 6. universal_confirm — только 1 окно, с обработкой ошибки
    logger.info("universal_confirm...")
    try:
        rabby.universal_confirm(windows=1, buttons=1)
        random_sleep(2, 3)
    except Exception as e:
        logger.warning(f"universal_confirm ошибка: {e}")

    # 7. Второе окно Rabby (Sign), если появилось
    logger.info("Проверяю второй Rabby popup (Sign)...")
    try:
        rabby.universal_confirm(windows=1, buttons=1)
        random_sleep(2, 3)
    except Exception as e:
        logger.info(f"Второй popup не найден: {e}")

    logger.success("Подключено!")
    random_sleep(3, 4)
    logger.info(f"URL: {page.url}")

    # 8. Early Badge
    logger.info("Ищу Early Badge...")
    badge_selectors = [
        'text=Early Badge',
        'text=EARLY BADGE',
        'text=Early Access Badge',
        '[class*="badge"]',
        'button:has-text("Claim")',
        'button:has-text("CLAIM")',
    ]
    for sel in badge_selectors:
        try:
            el = page.locator(sel)
            if el.count():
                logger.info(f"Найден: {sel} — кликаю")
                el.first.click()
                random_sleep(2, 3)
                try:
                    rabby.universal_confirm(windows=1, buttons=1)
                except Exception:
                    pass
                random_sleep(2, 3)
                break
        except Exception:
            continue
    else:
        logger.info("Early Badge не найден или уже получен")

    logger.success("Готово! Перехват активен. Ctrl+C для сохранения.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

    save()


if __name__ == "__main__":
    main()
