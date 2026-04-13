"""
Blockchain Payment Processing Service
Handles real USDT transfers on KITE AI blockchain
"""

import os
from web3 import Web3
from eth_account import Account
from dotenv import load_dotenv
import time

backend_dir = os.path.dirname(__file__)
root_env = os.path.join(backend_dir, os.pardir, ".env")
backend_env = os.path.join(backend_dir, ".env")
load_dotenv(root_env)
load_dotenv(backend_env, override=True)

KITE_RPC = os.getenv("KITE_RPC_URL", "https://rpc-testnet.gokite.ai/")
KITE_CHAIN_ID = int(os.getenv("KITE_CHAIN_ID", "2368"))
USDT_ADDRESS = os.getenv("USDT_ADDRESS", "0x0fF5393387ad2f9f691FD6Fd28e07E3969e27e63")
AUTO_BUY_CONTRACT = os.getenv("AUTO_BUY_CONTRACT_ADDRESS", "").strip()

if not USDT_ADDRESS:
    raise EnvironmentError(
        "KITE USDT token contract address not configured. "
        "Set USDT_ADDRESS in backend/.env or root .env"
    )

# Minimal testnet charges to preserve faucet tokens
MIN_USDT_CHARGE = 0.01  # Minimal charge per transaction (in USDT)
MIN_KITE_FOR_GAS = 0.001  # Minimal KITE needed for gas (in KITE)

# USDT ERC20 ABI
ERC20_ABI = [
    {
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
    {
        "inputs": [
            {"name": "_spender", "type": "address"},
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
    },
    {
        "inputs": [
            {"name": "_owner", "type": "address"}
        ],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
]

# AutoBuy Contract ABI
AUTO_BUY_ABI = [
    {
        "inputs": [
            {"name": "buyer", "type": "address"},
            {"name": "vendor", "type": "address"},
            {"name": "amount", "type": "uint256"}
        ],
        "name": "executePurchase",
        "outputs": [],
        "type": "function",
    },
]


class BlockchainPaymentProcessor:
    """Process real blockchain payments with USDT on KITE AI"""

    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(KITE_RPC))
        self.usdt_contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(USDT_ADDRESS),
            abi=ERC20_ABI
        )
        self.usdt_decimals = self._get_usdt_decimals()
        print(f"DEBUG: KITE USDT contract {USDT_ADDRESS} decimals={self.usdt_decimals}")

        if AUTO_BUY_CONTRACT:
            try:
                checksum_address = Web3.to_checksum_address(AUTO_BUY_CONTRACT)
                self.auto_buy_contract = self.w3.eth.contract(
                    address=checksum_address,
                    abi=AUTO_BUY_ABI
                )
            except Exception as e:
                print(
                    f"WARNING: AUTO_BUY_CONTRACT_ADDRESS is invalid; ignoring contract loading: {AUTO_BUY_CONTRACT}."
                )
                print(f"         Error: {e}")
                self.auto_buy_contract = None
        else:
            self.auto_buy_contract = None

    def _get_usdt_decimals(self) -> int:
        try:
            decimals = self.usdt_contract.functions.decimals().call()
            return int(decimals)
        except Exception as e:
            print(f"WARNING: Could not read USDT decimals from contract: {e}. Falling back to 6 decimals.")
            return 6

    def check_wallet_ready_for_payment(self, wallet_address: str) -> dict:
        """
        Quick check if wallet has BOTH tokens needed for payment
        STRICT: Returns False if either is missing
        """
        print(f"🔍 Checking wallet: {wallet_address}")
        try:
            wallet_checksum = Web3.to_checksum_address(wallet_address)
            print(f"✅ Checksum address: {wallet_checksum}")
            
            # Check KITE balance
            kite_balance_wei = self.w3.eth.get_balance(wallet_checksum)
            kite_balance = float(self.w3.from_wei(kite_balance_wei, "ether"))
            has_kite = kite_balance >= MIN_KITE_FOR_GAS
            print(f"💰 KITE balance: {kite_balance:.8f} (need {MIN_KITE_FOR_GAS:.8f}) - {'✅' if has_kite else '❌'}")
            
            # Check USDT balance
            usdt_balance_raw = self.usdt_contract.functions.balanceOf(wallet_checksum).call()
            usdt_balance = usdt_balance_raw / (10 ** self.usdt_decimals)
            has_usdt = usdt_balance >= MIN_USDT_CHARGE
            print(f"💵 USDT balance: {usdt_balance:.6f} (need {MIN_USDT_CHARGE:.6f}) - {'✅' if has_usdt else '❌'}")
            
            ready = has_kite and has_usdt
            print(f"🎯 Wallet ready: {ready}")
            
            return {
                "ready": ready,
                "kite": {
                    "balance": kite_balance,
                    "required": MIN_KITE_FOR_GAS,
                    "has_enough": has_kite,
                    "message": f"KITE: {kite_balance:.8f} (need {MIN_KITE_FOR_GAS:.8f})",
                },
                "usdt": {
                    "balance": usdt_balance,
                    "required": MIN_USDT_CHARGE,
                    "has_enough": has_usdt,
                    "message": f"USDT: {usdt_balance:.6f} (need {MIN_USDT_CHARGE:.6f})",
                },
                "summary": f"✅ Ready to pay" if ready else "❌ Missing tokens - get from KITE Faucet: https://faucet.gokite.ai",
            }
        except Exception as e:
            print(f"❌ Balance check failed for {wallet_address}: {str(e)}")
            # Always return required amounts even on error
            return {
                "ready": False,
                "error": str(e),
                "kite": {
                    "balance": 0,
                    "required": MIN_KITE_FOR_GAS,
                    "has_enough": False,
                    "message": f"Could not fetch KITE balance: {str(e)}",
                },
                "usdt": {
                    "balance": 0,
                    "required": MIN_USDT_CHARGE,
                    "has_enough": False,
                    "message": f"Could not fetch USDT balance: {str(e)}",
                },
                "summary": f"❌ Could not check wallet - ensure you're connected to KITE AI network: {str(e)}"
            }

    def validate_payment_params(self, from_address: str, to_address: str, amount_usd: float) -> dict:
        """
        Validate payment parameters before processing
        STRICT: Must have BOTH USDT and KITE tokens or payment fails
        """
        errors = []

        # Validate addresses
        if not Web3.is_address(from_address):
            errors.append("Invalid sender address")
        if not Web3.is_address(to_address):
            errors.append("Invalid recipient address")

        # Validate amount
        if amount_usd <= 0:
            errors.append("Amount must be greater than 0")
        if amount_usd > 1000000:
            errors.append("Amount exceeds maximum limit ($1M)")

        from_address_checksum = Web3.to_checksum_address(from_address)

        # CRITICAL: Check USDT balance - must have at least MIN_USDT_CHARGE
        try:
            usdt_balance_raw = self.usdt_contract.functions.balanceOf(from_address_checksum).call()
            usdt_balance = usdt_balance_raw / (10 ** self.usdt_decimals)

            if usdt_balance < MIN_USDT_CHARGE:
                errors.append(f"❌ INSUFFICIENT USDT: You have {usdt_balance:.6f} USDT, need minimum {MIN_USDT_CHARGE:.6f} USDT for testnet charges. Get USDT from KITE Faucet: https://faucet.gokite.ai")
        except Exception as e:
            errors.append(f"Could not check USDT balance: {str(e)}")

        # CRITICAL: Check KITE balance for gas - must have at least MIN_KITE_FOR_GAS
        try:
            kite_balance_wei = self.w3.eth.get_balance(from_address_checksum)
            kite_balance = self.w3.from_wei(kite_balance_wei, "ether")

            if float(kite_balance) < MIN_KITE_FOR_GAS:
                errors.append(f"❌ INSUFFICIENT KITE: You have {float(kite_balance):.8f} KITE, need minimum {MIN_KITE_FOR_GAS:.8f} KITE for gas fees. Get KITE from KITE Faucet: https://faucet.gokite.ai")
        except Exception as e:
            errors.append(f"Could not check KITE balance: {str(e)}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
        }

    def estimate_gas_cost(self) -> dict:
        """Estimate gas cost for a USDT transfer"""
        try:
            gas_price = self.w3.eth.gas_price
            gas_limit = 100000  # Typical for USDT transfer

            cost_wei = gas_price * gas_limit
            cost_kite = self.w3.from_wei(cost_wei, "ether")

            return {
                "gas_price_gwei": float(self.w3.from_wei(gas_price, "gwei")),
                "gas_limit": gas_limit,
                "estimated_cost_kite": float(cost_kite),
                "estimated_cost_usd": float(cost_kite) * 0.01,  # Approximate KITE price
            }
        except Exception as e:
            return {"error": str(e)}

    def prepare_usdt_transfer(self, from_address: str, to_address: str, amount_usd: float) -> dict:
        """
        Prepare USDT transfer transaction (for frontend signing)
        TESTNET: Charges minimal amount (0.01 USDT) to preserve faucet tokens
        
        Returns transaction object that frontend can sign with MetaMask
        Requires: User must have BOTH USDT and KITE tokens
        """
        try:
            from_addr = Web3.to_checksum_address(from_address)
            to_addr = Web3.to_checksum_address(to_address)

            # CRITICAL: Validate user has BOTH tokens before proceeding
            validation = self.validate_payment_params(from_addr, to_addr, amount_usd)
            if not validation["valid"]:
                return {
                    "success": False,
                    "errors": validation["errors"],
                    "note": "Payment blocked: Missing USDT or KITE tokens",
                }

            # Use minimal testnet charge (0.01 USDT) instead of full amount
            # This preserves faucet tokens for multiple transactions
            charge_usdt = MIN_USDT_CHARGE  # Fixed testnet charge
            amount_usdt_raw = int(charge_usdt * (10 ** self.usdt_decimals))

            # Build transaction
            tx = self.usdt_contract.functions.transfer(
                to_addr,
                amount_usdt_raw
            ).build_transaction({
                "from": from_addr,
                "nonce": self.w3.eth.get_transaction_count(from_addr),
                "gas": 100000,
                "gasPrice": self.w3.eth.gas_price,
                "chainId": 2368,
            })

            return {
                "success": True,
                "tx": tx,
                "tx_json": {
                    "to": tx["to"],
                    "from": tx["from"],
                    "value": tx["value"],
                    "gas": hex(tx["gas"]),
                    "gasPrice": hex(tx["gasPrice"]),
                    "data": tx["data"],
                    "nonce": hex(tx["nonce"]),
                    "chainId": hex(tx["chainId"]),
                },
                "details": {
                    "amount_requested_usd": amount_usd,
                    "actual_charge_usdt": charge_usdt,
                    "charge_reason": "Testnet minimal charge (0.01 USDT) to preserve faucet tokens",
                    "recipient": to_addr,
                    "blockchain": "KITE AI Testnet (2368)",
                    "settlement_network": "KITE",
                    "estimated_gas_cost_kite": float(self.w3.from_wei(tx["gas"] * tx["gasPrice"], "ether")),
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def send_usdt_transaction(self, signed_tx_data: dict) -> dict:
        """
        Send signed USDT transaction to blockchain
        Expects hex string of signed transaction from frontend
        """
        try:
            # Send transaction
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx_data)
            
            return {
                "success": True,
                "tx_hash": tx_hash.hex(),
                "status": "pending",
                "explorer_url": f"https://testnet.kitescan.ai/tx/{tx_hash.hex()}",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def wait_for_transaction(self, tx_hash: str, timeout: int = 180) -> dict:
        """
        Wait for transaction confirmation
        Returns transaction receipt when confirmed
        """
        try:
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)

            if receipt["status"] == 1:
                return {
                    "success": True,
                    "status": "confirmed",
                    "tx_hash": tx_hash,
                    "block_number": receipt["blockNumber"],
                    "gas_used": receipt["gasUsed"],
                    "transaction_fee_kite": float(self.w3.from_wei(
                        receipt["gasUsed"] * receipt["effectiveGasPrice"],
                        "ether"
                    )),
                    "explorer_url": f"https://testnet.kitescan.ai/tx/{tx_hash}",
                }
            else:
                return {
                    "success": False,
                    "status": "failed",
                    "tx_hash": tx_hash,
                    "message": "Transaction reverted",
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def get_transaction_status(self, tx_hash: str) -> dict:
        """Get current status of a transaction"""
        try:
            tx = self.w3.eth.get_transaction(tx_hash)
            
            try:
                receipt = self.w3.eth.get_transaction_receipt(tx_hash)
                status = "confirmed" if receipt["status"] == 1 else "failed"
                block = receipt["blockNumber"]
            except:
                status = "pending"
                block = None

            return {
                "tx_hash": tx_hash,
                "status": status,
                "from": tx["from"],
                "to": tx["to"],
                "value": str(tx["value"]),
                "block_number": block,
                "explorer_url": f"https://testnet.kitescan.ai/tx/{tx_hash}",
            }
        except Exception as e:
            return {
                "error": str(e),
            }

    def verify_signature(self, message: str, signature: str) -> str:
        """
        Verify Ethereum personal_sign signature and return recovered address
        """
        from eth_account import Account
        from eth_account.messages import encode_defunct
        
        # Ensure signature has 0x prefix
        if isinstance(signature, str) and not signature.startswith("0x"):
            signature = "0x" + signature
        
        # Encode message for personal_sign
        message_encoded = encode_defunct(text=message)
        
        # Recover address from signature
        recovered_address = Account.recover_message(message_encoded, signature=signature)
        
        return recovered_address


# Initialize processor
payment_processor = BlockchainPaymentProcessor()
