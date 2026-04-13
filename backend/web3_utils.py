import os
from web3 import Web3

RPC_URL = os.getenv("RPC_URL", "https://rpc-testnet.gokite.ai/")
USDT_ADDRESS = Web3.to_checksum_address(os.getenv("USDT_ADDRESS", "0x833589fCD6eDb6e08f4c7C32D4f71b54bdA02913"))

ERC20_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    }
]

w3 = Web3(Web3.HTTPProvider(RPC_URL))


def send_usdc(private_key, to, amount):
    account = w3.eth.account.from_key(private_key)
    contract = w3.eth.contract(address=USDT_ADDRESS, abi=ERC20_ABI)

    tx = contract.functions.transfer(
        Web3.to_checksum_address(to),
        int(amount * 1e6)
    ).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 100000,
        "gasPrice": w3.to_wei("2", "gwei")
    })

    signed = w3.eth.account.sign_transaction(tx, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)

    return tx_hash.hex()
