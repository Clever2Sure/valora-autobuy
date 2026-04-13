"""
Blockchain Requirements & Wallet Setup Service
Ensures users have KITE AI blockchain configured and all required tokens
"""

import os
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()

# KITE AI Testnet Configuration
KITE_RPC = os.getenv("KITE_RPC_URL", "https://rpc-testnet.gokite.ai/")
KITE_CHAIN_ID = 2368
USDT_ADDRESS = os.getenv("USDT_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
MIN_KITE_FOR_GAS = 0.1  # Minimum KITE for gas fees
MIN_USDT_FOR_PURCHASE = 1.0  # Minimum USDT to make a purchase

# USDT Contract ABI (ERC20)
USDT_ABI = [
    {
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
        "constant": True,
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
        "constant": True,
    },
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
    {
        "inputs": [
            {"name": "_from", "type": "address"},
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transferFrom",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    }
]

# KITE AI Network Configuration for frontend
KITE_NETWORK_CONFIG = {
    "chainId": "0x940",  # 2368 in hex
    "chainName": "KITE AI Testnet",
    "nativeCurrency": {
        "name": "KITE",
        "symbol": "KITE",
        "decimals": 18,
    },
    "rpcUrls": [KITE_RPC],
    "blockExplorerUrls": ["https://testnet.kitescan.ai/"],
}

# USDT Token Configuration for frontend
USDT_TOKEN_CONFIG = {
    "address": USDT_ADDRESS,
    "symbol": "USDT",
    "decimals": 6,
    "image": "https://assets.coingecko.com/coins/images/325/large/Tether.png",
}


class WalletRequirements:
    """Check and manage wallet requirements for blockchain transactions"""

    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(KITE_RPC))
        self.usdt_contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(USDT_ADDRESS),
            abi=USDT_ABI
        )

    def is_connected(self) -> bool:
        """Check if RPC is connected"""
        try:
            return self.w3.is_connected()
        except Exception as e:
            print(f"❌ RPC Connection Error: {e}")
            return False

    def validate_address(self, address: str) -> bool:
        """Validate Ethereum address format"""
        try:
            return Web3.is_address(address)
        except Exception:
            return False

    def get_kite_balance(self, address: str) -> dict:
        """Get KITE balance (native gas token) for an address"""
        try:
            if not self.validate_address(address):
                return {"error": "Invalid address format", "balance": 0}

            address = Web3.to_checksum_address(address)
            balance_wei = self.w3.eth.get_balance(address)
            balance_kite = self.w3.from_wei(balance_wei, "ether")

            return {
                "balance": float(balance_kite),
                "balance_wei": str(balance_wei),
                "sufficient": float(balance_kite) >= MIN_KITE_FOR_GAS,
                "minimum_required": MIN_KITE_FOR_GAS,
                "needs": max(0, MIN_KITE_FOR_GAS - float(balance_kite)),
            }
        except Exception as e:
            return {"error": str(e), "balance": 0, "sufficient": False}

    def get_usdt_balance(self, address: str) -> dict:
        """Get USDT balance for an address"""
        try:
            if not self.validate_address(address):
                return {"error": "Invalid address format", "balance": 0}

            address = Web3.to_checksum_address(address)
            balance_raw = self.usdt_contract.functions.balanceOf(address).call()
            decimals = self.usdt_contract.functions.decimals().call()
            balance_usdt = balance_raw / (10 ** decimals)

            return {
                "balance": float(balance_usdt),
                "balance_raw": str(balance_raw),
                "decimals": decimals,
                "sufficient": float(balance_usdt) >= MIN_USDT_FOR_PURCHASE,
                "minimum_required": MIN_USDT_FOR_PURCHASE,
                "needs": max(0, MIN_USDT_FOR_PURCHASE - float(balance_usdt)),
            }
        except Exception as e:
            return {"error": str(e), "balance": 0, "sufficient": False}

    def check_wallet_requirements(self, address: str) -> dict:
        """
        Comprehensive wallet requirements check
        Returns status of network, KITE (gas), and USDT (payment)
        """
        kite_balance = self.get_kite_balance(address)
        usdt_balance = self.get_usdt_balance(address)

        return {
            "address": address,
            "network": {
                "name": "KITE AI Testnet",
                "chainId": KITE_CHAIN_ID,
                "config": KITE_NETWORK_CONFIG,
            },
            "kite": {
                "balance": kite_balance.get("balance", 0),
                "sufficient": kite_balance.get("sufficient", False),
                "needs": kite_balance.get("needs", 0),
                "minimum": MIN_KITE_FOR_GAS,
            },
            "usdt": {
                "balance": usdt_balance.get("balance", 0),
                "sufficient": usdt_balance.get("sufficient", False),
                "needs": usdt_balance.get("needs", 0),
                "minimum": MIN_USDT_FOR_PURCHASE,
                "config": USDT_TOKEN_CONFIG,
            },
            "ready_to_purchase": (
                kite_balance.get("sufficient", False) and
                usdt_balance.get("sufficient", False)
            ),
            "issues": self._get_issues(kite_balance, usdt_balance),
        }

    @staticmethod
    def _get_issues(kite_data: dict, usdt_data: dict) -> list:
        """Identify wallet issues"""
        issues = []

        if not kite_data.get("sufficient", False):
            issues.append({
                "type": "insufficient_kite",
                "severity": "critical",
                "message": f"❌ Insufficient KITE for gas fees. You have {kite_data.get('balance', 0):.8f} KITE, need minimum 0.001 KITE",
                "needs": kite_data.get("needs", 0),
                "faucet": "https://faucet.gokite.ai",
                "faucet_name": "KITE AI Faucet",
                "action": "Get KITE tokens from faucet for gas fees",
            })

        if not usdt_data.get("sufficient", False):
            issues.append({
                "type": "insufficient_usdt",
                "severity": "critical",
                "message": f"❌ Insufficient USDT for payment. You have {usdt_data.get('balance', 0):.6f} USDT, need minimum 0.01 USDT",
                "needs": usdt_data.get("needs", 0),
                "faucet": "https://faucet.gokite.ai",
                "faucet_name": "KITE AI Faucet",
                "action": "Get USDT tokens from faucet for service charges",
            })

        return issues

    def estimate_transaction_cost(self) -> dict:
        """Estimate gas costs for a typical USDT transfer"""
        try:
            # Estimate gas for USDT transfer
            gas_price = self.w3.eth.gas_price
            estimated_gas = 100000  # Standard estimate for USDT transfer

            total_wei = gas_price * estimated_gas
            total_kite = self.w3.from_wei(total_wei, "ether")

            return {
                "gas_limit": estimated_gas,
                "gas_price_gwei": self.w3.from_wei(gas_price, "gwei"),
                "estimated_cost_kite": float(total_kite),
                "estimated_cost_usd": float(total_kite) * 0.01,  # Approximate KITE price
            }
        except Exception as e:
            return {"error": str(e)}

    def get_faucet_info(self) -> dict:
        """Provide faucet information for getting test tokens"""
        return {
            "kite_faucet": {
                "name": "KITE AI Official Faucet",
                "url": "https://faucet.gokite.ai",
                "description": "Get test KITE for gas fees and USDT for payments",
                "amount": "KITE + USDT",
                "time_between_requests": "24 hours",
            },
            "usdt_faucet": {
                "name": "KITE AI Faucet (USDT via same faucet)",
                "url": "https://faucet.gokite.ai",
                "description": "Request both KITE (gas) and USDT (payment) tokens",
                "amount": "Configured amount",
            },
            "block_explorer": {
                "name": "Kitescan",
                "url": "https://testnet.kitescan.ai/",
                "description": "View transactions and verify settlements",
            },
        }



# Initialize service
wallet_service = WalletRequirements()
