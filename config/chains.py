from typing import Iterator

from models.chain import Chain
from models.exceptions import ChainNameError


class Chains:

    _chains = None

    ETHEREUM = Chain(
        name='ethereum',
        rpc='https://1rpc.io/eth',
        chain_id=1,
        metamask_name='Ethereum Mainnet',
        native_token='ETH',
        okx_name='ERC20'
    )

    LINEA = Chain(
        name='linea',
        rpc='https://1rpc.io/linea',
        chain_id=59144,
        metamask_name='Linea',
        native_token='ETH',
        okx_name='Linea'
    )

    ARBITRUM_ONE = Chain(
        name='arbitrum_one',
        rpc='https://1rpc.io/arb',
        chain_id=42161,
        metamask_name='Arbitrum One',
        native_token='ETH',
        okx_name='Arbitrum One'
    )



    BSC = Chain(
        name='bsc',
        # rpc='https://1rpc.io/bnb',
        rpc='https://56.rpc.thirdweb.com',
        chain_id=56,
        # metamask_name='BSC 1RPC',
        metamask_name='BSC TW',
        native_token='BNB',
        okx_name='BSC'
    )

    OP = Chain(
        name='op',
        rpc='https://1rpc.io/op',
        chain_id=10,
        native_token='ETH',
        metamask_name='Optimism Mainnet',
        okx_name='Optimism'
    )

    POLYGON = Chain(
        name='polygon',
        rpc='https://1rpc.io/matic',
        chain_id=137,
        native_token='POL',
        metamask_name='Polygon',
        okx_name='Polygon'
    )

    BASE = Chain(
        name='base',
        rpc='https://1rpc.io/base',
        chain_id=8453,
        native_token='ETH',
        metamask_name='Base',
        okx_name='Base'
    )

    GRAVITY = Chain(
        name='gravity',
        rpc='https://rpc.ankr.com/gravity',
        chain_id=1625,
        native_token='G',
        metamask_name='Gravity',
    )

    ETHEREUM_SEPOLIA = Chain(
        name='ethereum_sepolia',
        # rpc='https://1rpc.io/sepolia',
        # rpc='https://sepolia.drpc.org',
        rpc='https://ethereum-sepolia-rpc.publicnode.com',
        chain_id=11155111,
        native_token='sepETH',
        # metamask_name='Sepolia',
        # metamask_name='Sepolia DRPC',
        metamask_name='Sepolia PublicNode'
    )

    DAC_TESTNET = Chain(
        name='dac_testnet',
        rpc='https://rpctest.dachain.tech',
        chain_id=21894,
        native_token='DACC',
        metamask_name='DAC Testnet',
        is_eip1559=False,
    )




    def __iter__(self) -> Iterator[Chain]:

        return iter(self.get_chains_list())

    @classmethod
    def get_chain(cls, name: str) -> Chain:

        if not isinstance(name, str):
            raise TypeError(f'Ошибка поиска сети, для поиска нужно передать str, передано:  {type(name)}')

        name = name.upper()
        try:
            chain = getattr(cls, name)
            return chain
        except AttributeError:
            for chain in cls.__dict__.values():
                if isinstance(chain, Chain):
                    if chain.name.upper() == name:
                        return chain
            raise ChainNameError(f'Сеть {name} не найдена, добавьте ее в config/Chains, имена должны совпадать')


    @classmethod
    def get_chains_list(cls) -> list[Chain]:

        if not cls._chains:
            cls._chains = [chain for chain in cls.__dict__.values() if isinstance(chain, Chain)]

        return cls._chains


if __name__ == '__main__':
    pass
