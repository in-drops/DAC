"""
Перехватывает API-запросы inception.dachain.io на ВСЕХ страницах браузера.
Запуск: python snippets/inspect_dac_api.py
Выполни действия в браузере (Connect, Streaks, Badge), затем Ctrl+C.
Результаты: snippets/api_requests.json
"""
import time
import json
import sys
import os

# Путь к браузеру — скрипт подключается к уже запущенному ADS браузеру
CDP_ENDPOINT = None  # будет получен через ADS API

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests as req
from playwright.sync_api import sync_playwright

ADS_API = "http://local.adspower.net:50325/api/v1"
PROFILE_NUMBER = 60
SKIP = ['.js', '.css', '.png', '.jpg', '.svg', '.ico', '.woff', '.ttf',
        'chrome-extension', 'google', 'analytics', 'datadog', 'sentry']

captured = []
OUT_FILE = os.path.join(os.path.dirname(__file__), 'api_requests.json')


def get_cdp():
    resp = req.get(f"{ADS_API}/browser/active", params={"serial_number": PROFILE_NUMBER}, timeout=5)
    data = resp.json()
    if data.get("data", {}).get("status") == "Active":
        return data["data"]["ws"]["puppeteer"]
    resp = req.get(f"{ADS_API}/browser/start", params={"serial_number": PROFILE_NUMBER}, timeout=15)
    return resp.json()["data"]["ws"]["puppeteer"]


def on_request(request):
    url = request.url
    if any(s in url for s in SKIP):
        return
    entry = {
        "method": request.method,
        "url": url,
        "post_data": request.post_data,
        "auth": request.headers.get("authorization", request.headers.get("Authorization", "")),
    }
    captured.append(entry)
    line = f"[{request.method}] {url}"
    if request.post_data:
        line += f"\n  BODY: {request.post_data[:300]}"
    if entry["auth"]:
        line += f"\n  AUTH: {entry['auth'][:80]}"
    sys.stdout.buffer.write((line + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


def save():
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(captured, f, ensure_ascii=False, indent=2)
    sys.stdout.buffer.write(f"\nСохранено {len(captured)} запросов -> {OUT_FILE}\n".encode("utf-8"))
    sys.stdout.buffer.flush()


def main():
    cdp = get_cdp()
    sys.stdout.buffer.write(f"Подключаюсь к браузеру: {cdp}\n".encode("utf-8"))
    sys.stdout.buffer.flush()

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(cdp)
        context = browser.contexts[0]

        # Слушаем ВСЕ запросы на уровне контекста
        context.on("request", on_request)

        sys.stdout.buffer.write(b"Перехват активен. Выполняй действия в браузере. Ctrl+C для завершения.\n")
        sys.stdout.buffer.flush()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    save()


if __name__ == "__main__":
    main()
