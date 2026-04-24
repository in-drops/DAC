from config.chains import Chains
from models.token import Token, TokenTypes
from models.chain import Chain

from models.exceptions import TokenNameError
from utils.utils import to_checksum


class Tokens:

    NATIVE_TOKEN = Token(
        symbol='NATIVE',
        address='0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee',
        chain=Chains.ETHEREUM,
        type_token=TokenTypes.NATIVE,
        decimals=18
    )

    USDT_ETHEREUM = Token(
        symbol='USDT',
        address='0xdac17f958d2ee523a2206206994597c13d831ec7',
        chain=Chains.ETHEREUM,
        type_token=TokenTypes.STABLE,
        decimals=6
    )

    USDC_ETHEREUM = Token(
        symbol='USDC',
        address='0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',
        chain=Chains.ETHEREUM,
        type_token=TokenTypes.STABLE,
        decimals=6
    )

    USDT_BASE = Token(
        symbol='USDT',
        address='0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2',
        chain=Chains.BASE,
        type_token=TokenTypes.STABLE,
        decimals=6
    )

    USDC_BASE = Token(
        symbol='USDC',
        address='0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',
        chain=Chains.BASE,
        type_token=TokenTypes.STABLE,
        decimals=6
    )

    ARB_ARBITRUM_ONE = Token(
        symbol='ARB',
        address='0x912CE59144191C1204E64559FE8253a0e49E6548',
        chain=Chains.ARBITRUM_ONE,
        type_token=TokenTypes.ERC20,
        decimals=18
    )

    USDT_ARBITRUM_ONE = Token(
        symbol='USDT',
        address='0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9',
        chain=Chains.ARBITRUM_ONE,
        type_token=TokenTypes.STABLE,
        decimals=6
    )

    USDC_ARBITRUM_ONE = Token(
        symbol='USDC',
        address='0xaf88d065e77c8cC2239327C5EDb3A432268e5831',
        chain=Chains.ARBITRUM_ONE,
        type_token=TokenTypes.STABLE,
        decimals=6
    )

    OP_OP = Token(
        symbol='OP',
        address='0x4200000000000000000000000000000000000042',
        chain=Chains.OP,
        type_token=TokenTypes.ERC20,
        decimals=18
    )

    USDT_OP = Token(
        symbol='USDT',
        address='0x94b008aa00579c1307b0ef2c499ad98a8ce58e58',
        chain=Chains.OP,
        type_token=TokenTypes.STABLE,
        decimals=6
    )

    USDC_OP = Token(
        symbol='USDC',
        address='0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85',
        chain=Chains.OP,
        type_token=TokenTypes.STABLE,
        decimals=6
    )

    USDT_LINEA = Token(
        symbol='USDT',
        address='0xA219439258ca9da29E9Cc4cE5596924745e12B93',
        chain=Chains.LINEA,
        type_token=TokenTypes.STABLE,
        decimals=6
    )

    USDC_LINEA = Token(
        symbol='USDC',
        address='0x176211869cA2b568f2A7D4EE941E073a821EE1ff',
        chain=Chains.LINEA,
        type_token=TokenTypes.STABLE,
        decimals=6
    )


    USDT_POLYGON = Token(
        symbol='USDT',
        address='0xc2132d05d31c914a87c6611c10748aeb04b58e8f',
        chain=Chains.POLYGON,
        type_token=TokenTypes.STABLE,
        decimals=6
    )

    USDC_POLYGON = Token(
        symbol='USDC',
        address='0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359',
        chain=Chains.POLYGON,
        type_token=TokenTypes.STABLE,
        decimals=6
    )

    USDT_BSC = Token(
        symbol='USDT',
        address='0x55d398326f99059ff775485246999027b3197955',
        chain=Chains.BSC,
        type_token=TokenTypes.STABLE,
        decimals=6
    )

    USDC_BSC = Token(
        symbol='USDC',
        address='0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d',
        chain=Chains.BSC,
        type_token=TokenTypes.STABLE,
        decimals=6
    )




    # ── Nemesis Trade — Ethereum Sepolia ──────────────────────────────────────
    WETH_ETHEREUM_SEPOLIA = Token(
        symbol='WETH',
        address='0x7b79995e5f793A07Bc00c21412e50Ecae098E7f9',
        chain=Chains.ETHEREUM_SEPOLIA,
        type_token=TokenTypes.ERC20,
        decimals=18
    )

    USDC_ETHEREUM_SEPOLIA = Token(
        symbol='USDC',
        address='0x10279e6333f9D0ee103f4715b8aAeA75bE61464C',
        chain=Chains.ETHEREUM_SEPOLIA,
        type_token=TokenTypes.STABLE,
        decimals=6
    )

    DAI_ETHEREUM_SEPOLIA = Token(
        symbol='DAI',
        address='0xd67215fD6c0890493F34aF3c5E4231Ce98871fCb',
        chain=Chains.ETHEREUM_SEPOLIA,
        type_token=TokenTypes.STABLE,
        decimals=18
    )

    NEMESIS_ETHEREUM_SEPOLIA = Token(
        symbol='NEMESIS',
        address='0x47B7ed0e04edAb477c46543BDF766AcEA155Dd2F',
        chain=Chains.ETHEREUM_SEPOLIA,
        type_token=TokenTypes.ERC20,
        decimals=18
    )

    LINK_ETHEREUM_SEPOLIA = Token(
        symbol='LINK',
        address='0x779877A7B0D9E8603169DdbD7836e478b4624789',
        chain=Chains.ETHEREUM_SEPOLIA,
        type_token=TokenTypes.ERC20,
        decimals=18
    )

    UNI_ETHEREUM_SEPOLIA = Token(
        symbol='UNI',
        address='0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984',
        chain=Chains.ETHEREUM_SEPOLIA,
        type_token=TokenTypes.ERC20,
        decimals=18
    )




    @classmethod
    def get_token_by_address(cls, address: str) -> Token:
        address = to_checksum(address)
        for token in cls.__dict__.values():
            if isinstance(token, Token):
                if token.address == address:
                    return token
        raise TokenNameError(f'Token with address {address} not found')

    @classmethod
    def get_token_by_symbol(cls, symbol: str, chain: Chain) -> Token:

        symbol_and_chain = f'{symbol.upper()}_{chain.name.upper()}'
        return getattr(cls, symbol_and_chain)

    @classmethod
    def add_token(cls, token: Token):
        setattr(cls, token.symbol, token)
        return token

    @classmethod
    def get_tokens_by_chain(cls, chain: Chain) -> list[Token]:

        tokens = []
        for token in cls.__dict__.values():
            if isinstance(token, Token):
                if token.chain == chain:
                    if token.type_token == TokenTypes.NATIVE:
                        continue
                    tokens.append(token)
        return tokens

    @classmethod
    def get_tokens(cls) -> list[Token]:

        tokens = []
        for token in cls.__dict__.values():
            if isinstance(token, Token):
                if token.type_token == TokenTypes.NATIVE:
                    continue
                tokens.append(token)
        return tokens
