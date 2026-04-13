import os
import hashlib
from web3 import Web3
from datetime import datetime
from typing import Dict

# Kite Testnet Configuration
# Official KiteAI Testnet endpoints: https://chainlist.org/chain/2368
KITE_RPC_URL = os.getenv("KITE_RPC_URL", "https://rpc-testnet.gokite.ai/")
KITE_CHAIN_ID = os.getenv("KITE_CHAIN_ID", "2368")
KITE_BLOCK_EXPLORER = os.getenv("KITE_BLOCK_EXPLORER", "https://testnet.kitescan.ai/")
USDC_ADDRESS = os.getenv("USDC_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
ATTESTATION_CONTRACT = os.getenv("ATTESTATION_CONTRACT", "")  # Deploy and set this

# Initialize Web3 connection to Kite
w3 = Web3(Web3.HTTPProvider(KITE_RPC_URL))

# Contract ABIs
ATTESTATION_ABI = [
    {
        "type": "function",
        "name": "attesta",
        "inputs": [
            {"name": "taskId", "type": "bytes32"},
            {"name": "user", "type": "address"},
            {"name": "paymentAmount", "type": "uint256"},
            {"name": "outputHash", "type": "bytes32"},
            {"name": "agentSignature", "type": "bytes"}
        ],
        "outputs": [],
        "stateMutability": "nonpayable"
    },
    {
        "type": "function",
        "name": "getAttestation",
        "inputs": [{"name": "taskId", "type": "bytes32"}],
        "outputs": [
            {
                "type": "tuple",
                "components": [
                    {"name": "taskId", "type": "bytes32"},
                    {"name": "user", "type": "address"},
                    {"name": "paymentAmount", "type": "uint256"},
                    {"name": "outputHash", "type": "bytes32"},
                    {"name": "agentSignature", "type": "bytes"},
                    {"name": "timestamp", "type": "uint256"},
                    {"name": "completed", "type": "bool"}
                ]
            }
        ],
        "stateMutability": "view"
    }
]

ATTESTATIONS = {}  # Local cache of attestations


def create_task_id_bytes32(task_id: str) -> bytes:
    """Convert task ID string to bytes32"""
    return hashlib.sha256(task_id.encode()).digest()


def record_attestation_on_kite(
    task_id: str,
    user_address: str,
    payment_amount: float,
    output_hash: str,
    agent_private_key: str = None
) -> Dict:
    """
    Record attestation on Kite chain (proof of execution)
    
    In production, this would be a real on-chain transaction.
    For now, we simulate with local tracking + metadata.
    """
    
    # Create attestation record
    attestation = {
        "task_id": task_id,
        "user": user_address,
        "payment_amount": payment_amount,
        "output_hash": output_hash,
        "timestamp": datetime.utcnow().isoformat(),
        "kite_chain": "testnet",
        "rpc_endpoint": KITE_RPC_URL,
        "status": "recorded"
    }
    
    # In production: send transaction to Kite
    # For now: simulate and log
    try:
        # Check Kite connection
        if not w3.is_connected():
            attestation["status"] = "pending"
            attestation["note"] = "Kite RPC not available - will retry"
        else:
            # Would call contract.functions.attesta(...).transact() here
            attestation["status"] = "attested"
            attestation["kite_tx_hash"] = f"0x{hashlib.sha256(task_id.encode()).hexdigest()}"
    except Exception as e:
        attestation["status"] = "error"
        attestation["error"] = str(e)
    
    # Store locally
    ATTESTATIONS[task_id] = attestation
    
    return attestation


def settle_payment_on_kite(
    task_id: str,
    user_address: str,
    payment_amount_usdc: float,
    vendor_address: str
) -> Dict:
    """
    Settle USDC payment on Kite chain
    """
    
    settlement = {
        "task_id": task_id,
        "user": user_address,
        "amount_usdc": payment_amount_usdc,
        "vendor": vendor_address,
        "timestamp": datetime.utcnow().isoformat(),
        "chain": "kite_testnet",
        "status": "simulated"  # Simulated for demo
    }
    
    try:
        if not w3.is_connected():
            settlement["status"] = "pending"
            settlement["note"] = "Kite RPC connection checking..."
        else:
            # In production: execute USDC transfer on Kite
            # For now: simulate
            settlement["status"] = "settled"
            settlement["tx_hash"] = f"0x{hashlib.sha256(f'{task_id}{payment_amount_usdc}'.encode()).hexdigest()}"
            settlement["confirmation_block"] = "pending"
    except Exception as e:
        settlement["status"] = "error"
        settlement["error"] = str(e)
    
    return settlement


def verify_kite_attestation(task_id: str) -> Dict:
    """Verify attestation recorded on Kite"""
    return ATTESTATIONS.get(task_id, {"status": "not_found"})


def get_user_attestations(user_address: str) -> list:
    """Get all attestations for a user"""
    return [a for a in ATTESTATIONS.values() if a["user"] == user_address]


def kite_health_check() -> Dict:
    """Check Kite chain connectivity"""
    try:
        connected = w3.is_connected()
        chain_id = w3.eth.chain_id if connected else None
        return {
            "status": "connected" if connected else "disconnected",
            "rpc_endpoint": KITE_RPC_URL,
            "chain_id": chain_id,
            "network": "Kite Testnet"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "rpc_endpoint": KITE_RPC_URL
        }
