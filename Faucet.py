from __future__ import annotations

import requests
from datetime import datetime, timedelta
from pathlib import Path
from loguru import logger

from config import config
from core.bot import Bot
from utils.inputs import (
    input_pause, input_cycle_amount, input_cycle_pause, start_pause,
    cell_date_to_txt, cell_value_to_txt,
    get_date_from_txt, get_value_from_txt,
)
from utils.logging import init_logger
from utils.utils import (
    get_accounts, get_user_agent, prepare_proxy_requests, random_sleep,
    select_and_shuffle_profiles,
)

# ─── Константы ────────────────────────────────────────────────────────────────
BASE_URL              = 'https://inception.dachain.io'
FAUCET_COOLDOWN = timedelta(hours=8, minutes=5)
MAX_RETRIES           = 3

FILE_FAUCET_DATE  = 'faucet_date.txt'
FILE_EARLY_BADGE  = 'early_badge_status.txt'
FILE_SCOUTING     = 'scouting_status.txt'    # exp_leaderboard — Scouting (25 QE, одноразово)
FILE_EXPLORER     = 'explorer_status.txt'    # exp_explorer    — Block Sleuth (50 QE, одноразово)
FILE_STATS        = 'stats.txt'
# ──────────────────────────────────────────────────────────────────────────────


class _AuthError(Exception):
    """Сессия истекла — нужна переавторизация."""


# ─── Session ──────────────────────────────────────────────────────────────────

class _Ctx:
    """Контекст сессии одного аккаунта (session + headers + proxies)."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.session: requests.Session = None
        self.get_h: dict = {}
        self.post_h: dict = {}
        self.proxies: dict = {}
        self._auth()

    def _auth(self) -> None:
        import random as _rnd
        account = self.bot.account
        self.proxies = prepare_proxy_requests(account.proxy)

        # Вытаскиваем версию Chrome из UA для sec-ch-ua
        ua = account.user_agent
        chrome_ver = '135'
        import re as _re
        m = _re.search(r'Chrome/(\d+)', ua)
        if m:
            chrome_ver = m.group(1)

        # Вариация Accept-Language на каждую сессию
        langs = [
            'en-US,en;q=0.9',
            'en-US,en;q=0.9,uk;q=0.8',
            'en-GB,en;q=0.9,en-US;q=0.8',
            'en-US,en;q=0.8',
        ]
        accept_lang = _rnd.choice(langs)

        self._base_headers = {
            'User-Agent':         ua,
            'Accept-Language':    accept_lang,
            'Accept-Encoding':    'gzip, deflate, br, zstd',
            'sec-ch-ua':          f'"Google Chrome";v="{chrome_ver}", "Chromium";v="{chrome_ver}", "Not?A_Brand";v="99"',
            'sec-ch-ua-mobile':   '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest':     'empty',
            'sec-fetch-mode':     'cors',
            'sec-fetch-site':     'same-origin',
            'Origin':             BASE_URL,
        }

        self.session = requests.Session()

        # 1. CSRF cookie — с Referer главной страницы
        self.session.get(
            f'{BASE_URL}/api/auth/csrf/',
            headers={**self._base_headers, 'Accept': 'application/json, text/plain, */*',
                     'Referer': BASE_URL + '/'},
            proxies=self.proxies,
            timeout=30,
        )
        csrf = self.session.cookies.get('csrftoken', '')
        self._csrf = csrf

        # 2. Авторизация (без подписи — только адрес кошелька)
        random_sleep(1, 2)
        resp = self.session.post(
            f'{BASE_URL}/api/auth/wallet/',
            json={'wallet_address': account.address},
            headers={**self._base_headers,
                     'Accept': 'application/json, text/plain, */*',
                     'Content-Type': 'application/json',
                     'X-CSRFToken': csrf,
                     'Referer': BASE_URL + '/'},
            proxies=self.proxies,
            timeout=30,
        )
        if resp.status_code in (401, 403):
            raise Exception(f'{account.profile_number} Auth error {resp.status_code}: {resp.text[:100]}')

        data = resp.json()
        if not data.get('success'):
            raise Exception(f'{account.profile_number} Auth failed: {resp.text[:150]}')

        logger.info(f'{account.profile_number} Авторизован | QE: {data["user"].get("qe_balance", "?")}')

    def reauth(self) -> None:
        logger.warning(f'{self.bot.account.profile_number} Сессия истекла — переавторизуемся...')
        self._auth()

    def get(self, path: str, referer: str = '/dashboard') -> requests.Response:
        headers = {
            **self._base_headers,
            'Accept':   'application/json, text/plain, */*',
            'Referer':  BASE_URL + referer,
        }
        resp = self.session.get(
            f'{BASE_URL}{path}',
            headers=headers,
            proxies=self.proxies,
            timeout=30,
        )
        if resp.status_code == 401:
            raise _AuthError(path)
        return resp

    def post(self, path: str, body: dict | None = None, referer: str = '/dashboard') -> requests.Response:
        random_sleep(1, 2)
        headers = {
            **self._base_headers,
            'Accept':         'application/json, text/plain, */*',
            'Content-Type':   'application/json',
            'X-CSRFToken':    self._csrf,
            'Referer':        BASE_URL + referer,
        }
        resp = self.session.post(
            f'{BASE_URL}{path}',
            json=body or {},
            headers=headers,
            proxies=self.proxies,
            timeout=30,
        )
        if resp.status_code == 401:
            raise _AuthError(path)
        return resp


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _write_faucet_date(bot, dt: datetime) -> None:
    """Записывает произвольную дату в faucet_date.txt (для синхронизации с API кулдауном)."""
    from pathlib import Path
    filepath = Path('config/data') / FILE_FAUCET_DATE
    profile_number = str(bot.account.profile_number)
    date_str = dt.strftime('%Y-%m-%d %H:%M:%S')
    lines = []
    updated = False
    if filepath.exists():
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip().split('\t')[0] == profile_number:
                    lines.append(f'{profile_number}\t{bot.account.address}\t{date_str}\n')
                    updated = True
                else:
                    lines.append(line)
    if not updated:
        lines.append(f'{profile_number}\t{bot.account.address}\t{date_str}\n')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(lines)


def _get_profile(ctx: _Ctx) -> dict:
    resp = ctx.get('/api/inception/profile/')
    resp.raise_for_status()
    return resp.json()


def update_stats_txt(bot: Bot, profile: dict) -> None:
    """Обновляет строку аккаунта в stats.txt.

    Формат: profile  wallet  date  rank  badges  qe  dacc  streak
    """
    DATA_DIR = Path('config/data')
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    filepath = DATA_DIR / FILE_STATS

    profile_number = str(bot.account.profile_number)
    date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    rank   = profile.get('user_rank', '?')
    badges = len(profile.get('badges', []))
    qe     = profile.get('qe_balance', 0)
    dacc   = profile.get('dacc_balance', '0')
    streak = profile.get('streak_days', 0)

    new_line = (
        f'{profile_number}\t{bot.account.address}\t{date_str}\t'
        f'Rank: {rank}\tBadges: {badges}\tQE: {qe}\tDACC: {dacc}\tStreak: {streak}\n'
    )

    lines = []
    updated = False
    if filepath.exists():
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip().split('\t')[0] == profile_number:
                    lines.append(new_line)
                    updated = True
                else:
                    lines.append(line)
    if not updated:
        lines.append(new_line)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    logger.info(
        f'{bot.account.profile_number} Статистика: '
        f'ранг #{rank} | бейджей {badges} | QE {qe} | DACC {dacc} | стрик {streak}д'
    )


# ─── Actions ──────────────────────────────────────────────────────────────────

def claim_early_badge(bot: Bot, ctx: _Ctx) -> None:
    if get_value_from_txt(bot.account, FILE_EARLY_BADGE) == 'SUCCESS':
        logger.debug(f'{bot.account.profile_number} Early Badge уже получен ранее')
        return

    profile = _get_profile(ctx)
    badge_keys = {b.get('badge__key') for b in profile.get('badges', [])}
    if 'sys_early_badge' in badge_keys:
        cell_value_to_txt(bot, 'SUCCESS', FILE_EARLY_BADGE)
        return

    resp = ctx.post('/api/inception/claim-badge/', {'key': 'sys_early_badge'})
    data = resp.json()

    if data.get('success'):
        cell_value_to_txt(bot, 'SUCCESS', FILE_EARLY_BADGE)
        logger.success(f'{bot.account.profile_number} Early Badge получен! QE: +{data.get("qe_awarded", 0)} 🎯')
    else:
        err = str(data.get('error', data))
        if 'already' in err.lower() or 'claimed' in err.lower():
            cell_value_to_txt(bot, 'SUCCESS', FILE_EARLY_BADGE)
        else:
            logger.warning(f'{bot.account.profile_number} Early Badge: {err}')


def claim_scouting(bot: Bot, ctx: _Ctx) -> None:
    """Scouting badge — посещение лидерборда (25 QE, одноразово)."""
    if get_value_from_txt(bot.account, FILE_SCOUTING) == 'SUCCESS':
        return

    resp = ctx.post('/api/inception/visit/leaderboard/', referer='/leaderboard')
    data = resp.json()
    if data.get('success'):
        cell_value_to_txt(bot, 'SUCCESS', FILE_SCOUTING)
        if data.get('awarded'):
            logger.success(f'{bot.account.profile_number} Scouting badge получен! 🎯')
    else:
        logger.warning(f'{bot.account.profile_number} Scouting: {data}')


def claim_explorer(bot: Bot, ctx: _Ctx) -> None:
    """Block Sleuth badge — посещение explorer (50 QE, одноразово)."""
    if get_value_from_txt(bot.account, FILE_EXPLORER) == 'SUCCESS':
        return

    resp = ctx.post('/api/inception/visit/explorer/', referer='/explorer')
    data = resp.json()
    if data.get('success'):
        cell_value_to_txt(bot, 'SUCCESS', FILE_EXPLORER)
        if data.get('awarded'):
            logger.success(f'{bot.account.profile_number} Block Sleuth badge получен! 🎯')
    else:
        logger.warning(f'{bot.account.profile_number} Block Sleuth: {data}')


def claim_faucet(bot: Bot, ctx: _Ctx) -> bool:
    last = get_date_from_txt(bot.account, FILE_FAUCET_DATE)
    if last and datetime.now() - last < FAUCET_COOLDOWN:
        remaining = FAUCET_COOLDOWN - (datetime.now() - last)
        hours = int(remaining.total_seconds() // 3600)
        mins  = int((remaining.total_seconds() % 3600) // 60)
        logger.info(f'{bot.account.profile_number} Фосет кулдаун: ещё {hours}ч {mins}м')
        return False

    # Проверяем кулдаун только если seconds_left > 0 (реальный кулдаун)
    profile = _get_profile(ctx)
    secs = profile.get('faucet_seconds_left', 0)
    if not profile.get('faucet_available') and secs > 0:
        logger.info(
            f'{bot.account.profile_number} Фосет кулдаун: '
            f'ещё {secs // 3600}ч {(secs % 3600) // 60}м'
        )
        # Синхронизируем локальный файл с реальным кулдауном платформы
        corrected = datetime.now() - FAUCET_COOLDOWN + timedelta(seconds=secs)
        _write_faucet_date(bot, corrected)
        return False

    # Имитируем посещение страницы фосета перед клеймом
    try:
        ctx.get('/api/inception/visit/faucet/', referer='/faucet')
    except Exception:
        pass
    random_sleep(1, 2)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = ctx.post('/api/inception/faucet/', referer='/faucet')
            data = resp.json()

            if 'error' in data:
                code, err = data.get('code', ''), data.get('error', '')
                if code == 'social_required':
                    logger.warning(f'{bot.account.profile_number} ⚠️ Фосет требует X или Discord')
                    return False
                elif code == 'dispense_pending':
                    cell_date_to_txt(bot, FILE_FAUCET_DATE)
                    logger.success(f'{bot.account.profile_number} Фосет принят, транзакция отправляется 🎯')
                    return True
                else:
                    logger.error(f'{bot.account.profile_number} Фосет ошибка [{code}]: {err}')
                    if attempt < MAX_RETRIES:
                        random_sleep(3, 7)
                    continue

            if data.get('success') or 'amount' in data:
                cell_date_to_txt(bot, FILE_FAUCET_DATE)
                logger.success(f'{bot.account.profile_number} Фосет получен 🎯')
                return True

            logger.error(f'{bot.account.profile_number} Неожиданный ответ: {data}')
            return False

        except _AuthError:
            raise
        except Exception as e:
            logger.error(f'{bot.account.profile_number} Попытка {attempt}/{MAX_RETRIES}: {e}')
            if attempt < MAX_RETRIES:
                random_sleep(3, 7)

    return False


# ─── Worker ───────────────────────────────────────────────────────────────────

def worker(account) -> None:
    account.user_agent = get_user_agent()
    with Bot(account) as bot:
        ctx = _Ctx(bot)

        # До 2 попыток: при сбросе сессии — переавторизуемся и повторяем
        for attempt in range(2):
            try:
                claim_early_badge(bot, ctx)
                claim_scouting(bot, ctx)
                claim_explorer(bot, ctx)
                claim_faucet(bot, ctx)
                profile = _get_profile(ctx)
                update_stats_txt(bot, profile)
                break
            except _AuthError:
                if attempt == 0:
                    ctx.reauth()
                else:
                    logger.error(f'{account.profile_number} Не удалось переавторизоваться')


# ─── Filter + Main ────────────────────────────────────────────────────────────

def accounts_filter(accounts):
    result = []
    for acc in accounts:
        last = get_date_from_txt(acc, FILE_FAUCET_DATE)
        if last and datetime.now() - last < FAUCET_COOLDOWN:
            logger.info(f'{acc.profile_number} Фосет на кулдауне...')
            continue
        result.append(acc)
    return result


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
            logger.warning('Все аккаунты уже получили фосет — кулдаун не истёк!')
            if cycle < cycle_amount - 1:
                random_sleep(cycle_pause)
            continue

        logger.info(f'Активных аккаунтов: {len(active)}')

        for account in active:
            worker(account)
            random_sleep(pause)

        logger.success(f'Цикл {cycle + 1}/{cycle_amount} завершён ✅')
        if cycle < cycle_amount - 1:
            random_sleep(cycle_pause)



if __name__ == '__main__':
    main()
