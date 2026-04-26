from __future__ import annotations

import re
import random
import requests
from datetime import datetime
from pathlib import Path
from web3 import Web3
from loguru import logger

from config import config
from config.chains import Chains
from core.bot import Bot
from core.onchain import Onchain
from models.account import Account
from models.amount import Amount
from utils.inputs import (
    input_pause, input_cycle_amount, input_cycle_pause, start_pause,
    get_value_from_txt,
)
from utils.logging import init_logger
from utils.utils import (
    get_accounts, get_user_agent, prepare_proxy_requests, random_sleep,
    select_and_shuffle_profiles,
)

# ─── Константы ────────────────────────────────────────────────────────────────
BASE_URL    = 'https://inception.dachain.io'
MAX_RETRIES = 3
MINT_PAUSE  = (20, 50)   # пауза между минтами в рамках одного аккаунта (сек)
GAS_RESERVE = 0.15       # мин. резерв DACC на газ

NFT_CONTRACT = Web3.to_checksum_address('0xB36ab4c2Bd6aCfC36e9D6c53F39F4301901Bd647')
NFT_ABI = [
    {
        'name': 'claimRank',
        'type': 'function',
        'stateMutability': 'nonpayable',
        'inputs': [
            {'name': 'rankId',    'type': 'uint8'},
            {'name': 'signature', 'type': 'bytes'},
        ],
        'outputs': [],
    },
    {
        'name': 'hasMinted',
        'type': 'function',
        'stateMutability': 'view',
        'inputs': [
            {'name': '', 'type': 'address'},
            {'name': '', 'type': 'uint8'},
        ],
        'outputs': [{'name': '', 'type': 'bool'}],
    },
]

FILE_RANK_NFT_STATUS = 'rank_nft_status.txt'
FILE_RANK_NFT_MINTED = 'rank_nft_minted.txt'   # лог заминченных NFT (защита от повторов)
DATA_DIR = Path('config/data')

_ALREADY_MINTED = object()  # сентинел: API вернул 400 — NFT заминчен ранее
# ──────────────────────────────────────────────────────────────────────────────


class _AuthError(Exception):
    pass


# ─── UA-парсеры ───────────────────────────────────────────────────────────────

def _chrome_ver_from_ua(ua: str) -> str:
    m = re.search(r'Chrome/(\d+)', ua)
    return m.group(1) if m else '135'

def _platform_from_ua(ua: str) -> str:
    if 'Macintosh' in ua or 'Mac OS X' in ua:
        return '"macOS"'
    if 'Linux' in ua and 'Android' not in ua:
        return '"Linux"'
    return '"Windows"'

def _mobile_from_ua(ua: str) -> str:
    return '?1' if ('Android' in ua or 'Mobile' in ua) else '?0'


# ─── Session ──────────────────────────────────────────────────────────────────

class _Ctx:
    """Контекст сессии одного аккаунта с полными браузерными отпечатками."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.session: requests.Session = None
        self._base_headers: dict = {}
        self._page_headers: dict = {}
        self._csrf: str = ''

        account = bot.account
        # Прокси и заголовки строятся один раз — не меняются при reauth()
        self.proxies = prepare_proxy_requests(account.proxy)
        self._build_headers(account.user_agent)

        self.session = requests.Session()
        self._do_auth()

    def _build_headers(self, ua: str) -> None:
        """Строит оба набора заголовков из UA — вызывается один раз при старте."""
        chrome_ver = _chrome_ver_from_ua(ua)
        platform   = _platform_from_ua(ua)
        mobile     = _mobile_from_ua(ua)

        sec_ch_ua = (
            f'"Google Chrome";v="{chrome_ver}", '
            f'"Chromium";v="{chrome_ver}", '
            f'"Not?A_Brand";v="99"'
        )
        accept_lang = random.choice([
            'en-US,en;q=0.9',
            'en-US,en;q=0.9,uk;q=0.8',
            'en-GB,en;q=0.9,en-US;q=0.8',
            'en-US,en;q=0.8',
        ])
        dnt = '1' if random.random() < 0.4 else None

        # Fetch/API заголовки (Chrome fetch() из JS)
        self._base_headers = {
            'Accept-Encoding':    'gzip, deflate, br, zstd',
            'Accept-Language':    accept_lang,
            'Cache-Control':      'no-cache',
            'Origin':             BASE_URL,
            'Pragma':             'no-cache',
            'Priority':           'u=1, i',
            'sec-ch-ua':          sec_ch_ua,
            'sec-ch-ua-mobile':   mobile,
            'sec-ch-ua-platform': platform,
            'sec-fetch-dest':     'empty',
            'sec-fetch-mode':     'cors',
            'sec-fetch-site':     'same-origin',
            'User-Agent':         ua,
        }
        if dnt:
            self._base_headers['DNT'] = dnt

        # HTML-навигация (Chrome page load)
        self._page_headers = {
            'Accept': (
                'text/html,application/xhtml+xml,application/xml;q=0.9,'
                'image/avif,image/webp,image/apng,*/*;q=0.8,'
                'application/signed-exchange;v=b3;q=0.7'
            ),
            'Accept-Encoding':           'gzip, deflate, br, zstd',
            'Accept-Language':           accept_lang,
            'Cache-Control':             'max-age=0',
            'Priority':                  'u=0, i',
            'sec-ch-ua':                 sec_ch_ua,
            'sec-ch-ua-mobile':          mobile,
            'sec-ch-ua-platform':        platform,
            'sec-fetch-dest':            'document',
            'sec-fetch-mode':            'navigate',
            'sec-fetch-site':            'none',
            'sec-fetch-user':            '?1',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent':                ua,
        }
        if dnt:
            self._page_headers['DNT'] = dnt

    def _navigate(self, path: str, referer: str | None = None) -> None:
        headers = dict(self._page_headers)
        if referer:
            headers['Referer'] = BASE_URL + referer
            headers['sec-fetch-site'] = 'same-origin'
            headers['sec-fetch-user'] = '?1'
        try:
            self.session.get(BASE_URL + path, headers=headers,
                             proxies=self.proxies, timeout=30, allow_redirects=True)
        except Exception:
            pass

    def _do_auth(self) -> None:
        account = self.bot.account

        # 0. Главная страница (симуляция открытия браузером)
        self._navigate('/')
        random_sleep(1.5, 3.5)

        # 1. CSRF
        self.session.get(
            f'{BASE_URL}/api/auth/csrf/',
            headers={**self._base_headers, 'Accept': 'application/json, text/plain, */*',
                     'Referer': BASE_URL + '/'},
            proxies=self.proxies, timeout=30,
        )
        self._csrf = self.session.cookies.get('csrftoken', '')

        # 2. Авторизация — только адрес кошелька, без подписи
        random_sleep(1, 2)
        resp = self.session.post(
            f'{BASE_URL}/api/auth/wallet/',
            json={'wallet_address': account.address},
            headers={**self._base_headers,
                     'Accept': 'application/json, text/plain, */*',
                     'Content-Type': 'application/json',
                     'X-CSRFToken': self._csrf,
                     'Referer': BASE_URL + '/'},
            proxies=self.proxies, timeout=30,
        )
        if resp.status_code in (401, 403):
            raise Exception(f'{account.profile_number} Auth error {resp.status_code}: {resp.text[:100]}')

        data = resp.json()
        if not data.get('success'):
            raise Exception(f'{account.profile_number} Auth failed: {resp.text[:150]}')

        logger.info(f'{account.profile_number} Авторизован | QE: {data["user"].get("qe_balance", "?")}')

    def reauth(self) -> None:
        """Повторная авторизация — те же заголовки/прокси/UA, только новая сессия."""
        logger.warning(f'{self.bot.account.profile_number} Сессия истекла — переавторизуемся...')
        self.session = requests.Session()
        self._do_auth()

    def get(self, path: str, referer: str = '/dashboard') -> requests.Response:
        resp = self.session.get(
            f'{BASE_URL}{path}',
            headers={**self._base_headers, 'Accept': 'application/json, text/plain, */*',
                     'Referer': BASE_URL + referer},
            proxies=self.proxies, timeout=30,
        )
        if resp.status_code == 401:
            raise _AuthError(path)
        return resp

    def post(self, path: str, body: dict | None = None, referer: str = '/dashboard') -> requests.Response:
        random_sleep(1, 2)
        resp = self.session.post(
            f'{BASE_URL}{path}',
            json=body or {},
            headers={**self._base_headers,
                     'Accept': 'application/json, text/plain, */*',
                     'Content-Type': 'application/json',
                     'X-CSRFToken': self._csrf,
                     'Referer': BASE_URL + referer},
            proxies=self.proxies, timeout=30,
        )
        if resp.status_code == 401:
            raise _AuthError(path)
        return resp


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_rank_catalog(ctx: _Ctx) -> list[dict]:
    """Получает ранговые NFT из каталога: дашборд → badges (имитация навигации)."""
    ctx._navigate('/dashboard', referer='/')
    random_sleep(1.5, 3)
    try:
        ctx.get('/api/inception/profile/', referer='/dashboard')
    except Exception:
        pass
    random_sleep(1, 2)
    ctx._navigate('/badges', referer='/dashboard')
    random_sleep(1.5, 3)

    resp = ctx.get('/api/inception/badges/catalog/', referer='/badges')
    resp.raise_for_status()
    data = resp.json()
    items = data if isinstance(data, list) else data.get('badges', [])
    return [b for b in items if b.get('category') == 'rank']


def _get_claim_signature(ctx: _Ctx, rank_key: str) -> dict | object | None:
    """Запрашивает подпись для минта.
    Возвращает: dict — успех, _ALREADY_MINTED — 400 (заминчен вручную), None — 403 (не заработан).
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = ctx.post(
                '/api/inception/nft/claim-signature/',
                body={'rank_key': rank_key},
                referer='/badges',
            )
            if resp.status_code == 403:
                return None            # ранг не заработан
            if resp.status_code == 400:
                return _ALREADY_MINTED # заминчен ранее (вручную или другим способом)
            resp.raise_for_status()
            data = resp.json()
            if data.get('success'):
                return data
            return None
        except _AuthError:
            raise
        except Exception as e:
            if attempt < MAX_RETRIES:
                random_sleep(3, 7)
            else:
                logger.warning(f'{ctx.bot.account.profile_number} claim-signature [{rank_key}]: {e}')
    return None


def _is_minted_locally(account: Account, rank_key: str) -> bool:
    """Быстрая проверка по локальному файлу — без RPC. Первый слой защиты."""
    filepath = DATA_DIR / FILE_RANK_NFT_MINTED
    if not filepath.exists():
        return False
    profile_number = str(account.profile_number)
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) >= 4 and parts[0] == profile_number and parts[3] == rank_key:
                return True
    return False


def _save_minted_locally(account: Account, rank_key: str, rank_name: str, tx_hash: str) -> None:
    """Записывает заминченный NFT сразу после успешной транзакции."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    filepath = DATA_DIR / FILE_RANK_NFT_MINTED
    date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'{account.profile_number}\t{account.address}\t{date_str}\t{rank_key}\t{rank_name}\t{tx_hash}\n'
    with open(filepath, 'a', encoding='utf-8') as f:
        f.write(line)


def _has_minted_onchain(account: Account, rank_id: int) -> bool:
    """Вторичная проверка on-chain. При сбое RPC возвращает None (неизвестно)."""
    try:
        onchain = Onchain(account, Chains.DAC_TESTNET)
        contract = onchain.w3.eth.contract(address=NFT_CONTRACT, abi=NFT_ABI)
        return contract.functions.hasMinted(
            Web3.to_checksum_address(account.address), rank_id
        ).call()
    except Exception:
        return None  # RPC недоступен — не блокируем, локальный файл уже проверен


def _mint_onchain(account: Account, rank_id: int, signature_hex: str) -> str:
    """Отправляет on-chain транзакцию claimRank(rankId, signature)."""
    onchain = Onchain(account, Chains.DAC_TESTNET)
    contract = onchain.w3.eth.contract(address=NFT_CONTRACT, abi=NFT_ABI)

    sig_bytes = bytes.fromhex(signature_hex)

    tx_params = onchain._prepare_tx()
    tx_params = contract.functions.claimRank(rank_id, sig_bytes).build_transaction(tx_params)
    tx_params['gas'] = onchain.safe_estimate_gas(tx_params)

    return onchain._sign_and_send(tx_params)


def _check_gas(account: Account) -> bool:
    """Проверяет что на балансе достаточно DACC для оплаты газа."""
    try:
        onchain = Onchain(account, Chains.DAC_TESTNET)
        balance = onchain.get_balance()
        return balance.ether > GAS_RESERVE
    except Exception:
        return True  # при ошибке не блокируем


def _save_nft_status(bot: Bot, last_name: str, minted: int, total: int) -> None:
    """Сохраняет в rank_nft_status.txt: последний NFT + счётчик (X/Y)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    filepath = DATA_DIR / FILE_RANK_NFT_STATUS
    profile_number = str(bot.account.profile_number)
    wallet = bot.account.address
    date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    value = f'{last_name} ({minted}/{total})'

    new_line = f'{profile_number}\t{wallet}\t{date_str}\t{value}\n'
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


# ─── Core action ──────────────────────────────────────────────────────────────

def mint_rank_nft(bot: Bot, ctx: _Ctx) -> tuple[int, int, int, str]:
    """Возвращает (newly_minted, total_minted, total, last_name)."""
    account = bot.account

    rank_nfts = _get_rank_catalog(ctx)
    if not rank_nfts:
        logger.warning(f'{account.profile_number} ⚠️ Ранговые NFT не найдены в каталоге')
        return 0, 0, 0, '—'

    total = len(rank_nfts)
    newly_minted = 0
    total_minted = 0
    last_minted_name: str | None = None
    last_earned_name: str | None = None

    for i, nft in enumerate(rank_nfts):
        rank_key = nft.get('key', '')
        name = nft.get('name', rank_key)

        # 1. Получаем подпись API
        sig_data = _get_claim_signature(ctx, rank_key)

        if sig_data is None:
            continue  # 403 — ранг не заработан, пропускаем

        if sig_data is _ALREADY_MINTED:
            # 400 — заминчен вручную (например, через браузер)
            # Записываем в локальный файл если ещё нет, чтобы учесть в итоге
            if not _is_minted_locally(account, rank_key):
                _save_minted_locally(account, rank_key, name, 'external')
            total_minted += 1
            last_minted_name = name
            continue

        rank_id   = sig_data['rank_id']
        signature = sig_data['signature']
        last_earned_name = name

        # 2. Слой 1 — локальный файл (без RPC, мгновенно)
        if _is_minted_locally(account, rank_key):
            total_minted += 1
            last_minted_name = name
            continue

        # 3. Слой 2 — on-chain hasMinted (если RPC доступен)
        onchain_check = _has_minted_onchain(account, rank_id)
        if onchain_check is True:
            # Заминчено ранее вне скрипта — сохраняем локально чтобы не проверять RPC снова
            _save_minted_locally(account, rank_key, name, 'external')
            total_minted += 1
            last_minted_name = name
            continue
        # onchain_check is None → RPC упал, но локальный файл уже проверен → продолжаем

        # 4. Проверка газа
        if not _check_gas(account):
            logger.error(
                f'{account.profile_number} Недостаточно DACC для газа (резерв {GAS_RESERVE})'
            )
            break

        # 5. Минт on-chain
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                tx_hash = _mint_onchain(account, rank_id, signature)
                # Сразу пишем в локальный файл — защита от повторного минта
                _save_minted_locally(account, rank_key, name, tx_hash)
                newly_minted += 1
                total_minted += 1
                last_minted_name = name
                logger.success(
                    f'{account.profile_number} Заминчен {name} NFT | tx: {tx_hash} 🎯'
                )
                break
            except Exception as e:
                err = str(e)
                if 'already' in err.lower() or 'minted' in err.lower():
                    # Контракт говорит "уже есть" — пишем локально и двигаемся дальше
                    _save_minted_locally(account, rank_key, name, 'contract_reverted')
                    total_minted += 1
                    last_minted_name = name
                    break
                logger.error(
                    f'{account.profile_number} Попытка {attempt}/{MAX_RETRIES} [{name}]: {err}'
                )
                if attempt < MAX_RETRIES:
                    random_sleep(5, 10)

        # Пауза между минтами (кроме последнего)
        if i < len(rank_nfts) - 1 and newly_minted > 0:
            random_sleep(*MINT_PAUSE)

    final_name = last_minted_name or last_earned_name or '—'
    _save_nft_status(bot, final_name, total_minted, total)
    return newly_minted, total_minted, total, final_name


# ─── Worker ───────────────────────────────────────────────────────────────────

MAX_WORKER_ATTEMPTS = 3

def worker(account) -> None:
    account.user_agent = get_user_agent()
    result = None
    with Bot(account) as bot:
        for attempt in range(1, MAX_WORKER_ATTEMPTS + 1):
            try:
                ctx = _Ctx(bot)
                result = mint_rank_nft(bot, ctx)
                break
            except _AuthError:
                logger.warning(
                    f'{account.profile_number} Попытка {attempt}/{MAX_WORKER_ATTEMPTS}: '
                    f'сессия сброшена, переавторизуемся...'
                )
                if attempt < MAX_WORKER_ATTEMPTS:
                    random_sleep(5, 10)
            except Exception as e:
                logger.error(
                    f'{account.profile_number} Попытка {attempt}/{MAX_WORKER_ATTEMPTS} ошибка: {e}'
                )
                if attempt < MAX_WORKER_ATTEMPTS:
                    random_sleep(5, 10)
        else:
            logger.error(
                f'{account.profile_number} Аккаунт пропущен после {MAX_WORKER_ATTEMPTS} попыток'
            )

        if result:
            newly, total_minted, total, last_name = result
            if newly > 0:
                logger.success(
                    f'{account.profile_number} Заминчено {newly} NFT | '
                    f'всего {total_minted}/{total} | последний: {last_name} NFT 🔥'
                )
            else:
                logger.info(
                    f'{account.profile_number} Новых минтов нет | всего {total_minted}/{total}'
                )


# ─── Filter + Main ────────────────────────────────────────────────────────────

def accounts_filter(accounts: list) -> list:
    result = []
    for acc in accounts:
        status = get_value_from_txt(acc, FILE_RANK_NFT_STATUS)
        if status and '(' in status and '/' in status:
            try:
                counts = status.rsplit('(', 1)[1].rstrip(')')
                minted, total = map(int, counts.split('/'))
                if total > 0 and minted >= total:
                    logger.info(f'{acc.profile_number} Все ранговые NFT получены — пропускаем')
                    continue
            except (ValueError, IndexError):
                pass
        if not _check_gas(acc):
            logger.warning(f'{acc.profile_number} ⚠️ Недостаточно DACC для газа ({GAS_RESERVE} мин.) — пропускаем')
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
            logger.warning('Все аккаунты уже получили все ранговые NFT!')
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
