from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import json
import time
import hashlib
from dotenv import load_dotenv

# Load environment variables from root .env and backend/.env
backend_dir = os.path.dirname(__file__)
root_env = os.path.join(backend_dir, os.pardir, ".env")
backend_env = os.path.join(backend_dir, ".env")
load_dotenv(root_env)
load_dotenv(backend_env, override=True)

# Valora treasury recipient for service charge payments
VALORA_TREASURY_ADDRESS = os.getenv("VALORA_TREASURY_ADDRESS")

pending_links_file = os.path.join(backend_dir, "pending_purchase_links.json")


def load_pending_purchase_links():
    if os.path.exists(pending_links_file):
        try:
            with open(pending_links_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"WARNING: Failed to load pending purchase links: {e}")
            return {}
    return {}


def save_pending_purchase_links():
    try:
        with open(pending_links_file, "w", encoding="utf-8") as f:
            json.dump(pending_purchase_links, f)
    except Exception as e:
        print(f"WARNING: Failed to save pending purchase links: {e}")

pending_purchase_links = load_pending_purchase_links()

# Existing imports
from .agent import decide_purchase
from .constraints import validate
from .web3_utils import send_usdc, w3
from .kite import settle_usdc, get_settlements
from .subscriptions import (
    create_subscription, get_subscription, cancel_subscription,
    pause_subscription, resume_subscription, get_due_subscriptions,
    update_subscription_charge
)
from .users import register_user, authenticate_user, get_user_by_token

# New imports
from .kite_settlement import (
    record_attestation_on_kite, settle_payment_on_kite,
    verify_kite_attestation, get_user_attestations, kite_health_check
)
from .blockchain_payment import (
    payment_processor, MIN_USDT_CHARGE,
    USDT_ADDRESS, KITE_CHAIN_ID, KITE_RPC
)
from web3 import Web3

if not VALORA_TREASURY_ADDRESS:
    raise RuntimeError(
        "VALORA_TREASURY_ADDRESS is required. Set it in root .env or the environment before starting the backend."
    )

if not Web3.is_address(VALORA_TREASURY_ADDRESS):
    raise RuntimeError(
        f"VALORA_TREASURY_ADDRESS is invalid: {VALORA_TREASURY_ADDRESS}. "
        "Use a full checksum KITE wallet address like 0xDd1B81c0e23afb7a0307F5c03ad4b6a0b40787f1."
    )

app = FastAPI(title="AutoBuy Agent")

# Store pending product URLs until payment completes
pending_purchase_links = {}
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8001")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize agents


def get_current_user(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    token = authorization.replace("Bearer ", "")
    user = get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


# ============ AUTH ENDPOINTS ============

@app.post("/register")
async def register(request: dict):
    username = request.get("username")
    password = request.get("password")
    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")
    user = register_user(username, password)
    if not user:
        raise HTTPException(status_code=409, detail="user already exists")
    token = authenticate_user(username, password)
    return {"status": "registered", "token": token}


@app.post("/login")
async def login(request: dict):
    username = request.get("username")
    password = request.get("password")
    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")
    token = authenticate_user(username, password)
    if not token:
        raise HTTPException(status_code=401, detail="invalid credentials")
    return {"status": "authenticated", "token": token}


@app.get("/me")
async def me(user=Depends(get_current_user)):
    return {"username": user["username"], "id": user["id"]}


# ============ KITE CHAIN ENDPOINTS ============

@app.get("/kite/health")
async def kite_health():
    """Check Kite chain connectivity"""
    return kite_health_check()


@app.get("/kite/usdt-debug")
async def kite_usdt_debug():
    """Debug endpoint for configured KITE USDT contract and detected decimals"""
    try:
        usdt_address_checksum = Web3.to_checksum_address(USDT_ADDRESS)
        contract_code = payment_processor.w3.eth.get_code(usdt_address_checksum).hex()
        code_size = len(contract_code) - 2
        contract_deployed = code_size > 0
    except Exception as e:
        contract_code = None
        code_size = 0
        contract_deployed = False
        code_error = str(e)
    else:
        code_error = None

    return {
        "connected": payment_processor.w3.is_connected(),
        "usdt_address": USDT_ADDRESS,
        "usdt_address_checksum": usdt_address_checksum if contract_deployed or code_error is None else None,
        "usdt_decimals": payment_processor.usdt_decimals,
        "contract_code_size": code_size,
        "contract_deployed": contract_deployed,
        "contract_code_error": code_error,
        "treasury_address": VALORA_TREASURY_ADDRESS,
        "chain_id": KITE_CHAIN_ID,
        "rpc_url": KITE_RPC,
        "note": "USDT_ADDRESS is the USDT contract. VALORA_TREASURY_ADDRESS must be the full KITE wallet address that receives service fees."
    }


@app.get("/kite/attestations/{user_id}")
async def get_kite_attestations(user_id: str, user=Depends(get_current_user)):
    """Get user's attestations on Kite"""
    if user_id != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    attestations = get_user_attestations(user_id)
    return {
        "user": user_id,
        "attestation_count": len(attestations),
        "attestations": attestations
    }


@app.get("/kite/settlements")
async def get_kite_settlements(user=Depends(get_current_user)):
    """Get list of all simulated Kite settlements"""
    data = get_settlements()
    # optionally filter by user metadata
    own = [s for s in data if s.get("metadata", {}).get("user") == user["username"]]
    return {
        "user": user["username"],
        "settlement_count": len(own),
        "settlements": own
    }


# ============ ORIGINAL COMMERCE ENDPOINTS ============

@app.post("/buy")
async def buy(request: dict, user=Depends(get_current_user)):
    """Enhanced purchase with online product search capability"""
    search_online = request.get("search_online", False)

    decision = decide_purchase(request)
    if decision["status"] != "approved":
        return decision

    product = decision["product"]

    # Enforce budget caps and explicit range constraints (defensive guard)
    budget = float(request.get("budget", 0))

    from .agent import parse_price_range
    min_price, max_price, _ = parse_price_range(request.get("query", ""), budget)
    max_price = min(max_price, budget)

    if product["price"] > budget or product["price"] > max_price:
        return {"status": "rejected", "reason": "over_budget"}

    valid, reason = validate(product, budget)
    if not valid:
        return {"status": "rejected", "reason": reason}

    # Recipient destination for purchase - ALWAYS Valora treasury for service fees
    recipient_address = VALORA_TREASURY_ADDRESS
    if not recipient_address:
        raise ValueError("VALORA_TREASURY_ADDRESS not configured")

    # Create product preview (without direct URL to prevent bypassing payment)
    product_preview = {
        "name": product["name"],
        "price": product["price"],
        "rating": product.get("rating"),
        "source": product.get("source"),
        "currency": product.get("currency", "USD")
        # Note: URL is intentionally excluded to enforce payment flow
    }

    # Preserve the real product URL for the later payment confirmation step
    if product.get("url"):
        purchase_token = hashlib.sha256(
            (product["url"] + product["name"] + str(time.time())).encode()
        ).hexdigest()
        pending_purchase_links[purchase_token] = {
            "url": product["url"],
            "product": product,
            "created_at": time.time(),
            "expires_at": time.time() + 60 * 60  # expire protected link after 1 hour
        }
        save_pending_purchase_links()
        product_preview["purchase_token"] = purchase_token

    # Enhanced response with search metadata
    payment_info = {
        "status": "payment_required",
        "product": product_preview,  # Preview without URL
        "amount": product["price"],
        "currency": "USDT",
        "source": decision.get("source", "local_catalog"),
        "x402": True,
        "message": "Pay commission to access direct purchase link and complete transaction on Kite"
    }

    # Include search results if from online search (also without URLs)
    if "search_results" in decision:
        preview_results = []
        for result in decision["search_results"]:
            preview_results.append({
                "name": result["name"],
                "price": result["price"],
                "rating": result.get("rating"),
                "source": result.get("source"),
                "currency": result.get("currency", "USD")
                # URL excluded
            })
        payment_info["search_results"] = preview_results

    return JSONResponse(status_code=402, content=payment_info)


@app.get("/redeem/{product_token}")
async def redeem_product_link(product_token: str):
    """Redirect the secured product token to the real merchant URL."""
    token_info = pending_purchase_links.get(product_token)
    if not token_info:
        raise HTTPException(status_code=404, detail="Protected purchase link not found or expired")

    expires_at = token_info.get("expires_at")
    if expires_at and time.time() > expires_at:
        pending_purchase_links.pop(product_token, None)
        save_pending_purchase_links()
        raise HTTPException(status_code=404, detail="Protected purchase link has expired")

    target_url = token_info.get("url")
    if not target_url:
        raise HTTPException(status_code=500, detail="Protected purchase link target unavailable")

    return RedirectResponse(target_url, status_code=302)


@app.post("/confirm-payment")
async def confirm_payment(request: dict, user=Depends(get_current_user)):
    """
    Process confirmed payment and settle on Kite chain
    CRITICAL: Verifies wallet has BOTH USDT and KITE before ANY settlement
    """
    product = request.get("product")
    product_token = request.get("product_token")
    wallet_address = request.get("wallet_address")
    signature = request.get("signature")

    if not product or not wallet_address or not signature:
        raise HTTPException(status_code=400, detail="product, wallet_address, signature required")

    # ============================================================
    # CRITICAL VALIDATION: Check wallet has BOTH tokens BEFORE payment
    # ============================================================
    print(f"\n{'='*80}")
    print(f"🔒 CRITICAL PRE-PAYMENT VALIDATION")
    print(f"{'='*80}")
    print(f"Wallet: {wallet_address}")
    
    wallet_ready = payment_processor.check_wallet_ready_for_payment(wallet_address)
    print(f"Wallet Status: {wallet_ready}")
    
    if not wallet_ready.get("ready", False):
        print(f"\n❌ PAYMENT BLOCKED: Wallet not ready")
        print(f"USDT: {wallet_ready.get('usdt', {}).get('message', 'N/A')}")
        print(f"KITE: {wallet_ready.get('kite', {}).get('message', 'N/A')}")
        print(f"{'='*80}\n")
        
        raise HTTPException(
            status_code=402,
            detail="Insufficient Fund"
        )
    
    print(f"✅ PAYMENT VALIDATION PASSED")
    print(f"{'='*80}\n")

    # Remove any client-supplied URL or token values; real URL will be attached only after successful payment
    product.pop("url", None)
    product.pop("purchase_token", None)

    # Validate and sanitize product name
    product_name = product.get("name", "").strip()
    if not product_name:
        raise HTTPException(status_code=400, detail="Product name is required")
    
    # Ensure product name is not too long (limit to 200 chars)
    if len(product_name) > 200:
        print(f"DEBUG: Product name too long ({len(product_name)} chars), truncating")
        product_name = product_name[:200] + "..."
    
    # Use Valora treasury as the recipient for all payments
    recipient_address = VALORA_TREASURY_ADDRESS
    if not recipient_address:
        raise HTTPException(status_code=500, detail="Treasury address not configured")
    print(f"💰 Valora Treasury Address: {recipient_address}")
    
    print(f"DEBUG: Using recipient_address: {recipient_address}")
    
    # Validate recipient address
    if not Web3.is_address(recipient_address):
        raise HTTPException(status_code=400, detail="Invalid recipient address")
    
    # Convert amount to USDT (minimal testnet charge)
    amount_usd = float(product.get("price", 0))
    charge_usdt = MIN_USDT_CHARGE  # Fixed testnet charge
    
    print(f"DEBUG: Product price: ${amount_usd}")
    print(f"DEBUG: USDT charge: {charge_usdt}")
    
    # Prepare USDT transfer transaction
    try:
        tx_data = payment_processor.prepare_usdt_transfer(
            wallet_address,
            recipient_address,
            charge_usdt
        )
        
        if not tx_data.get("success", False):
            raise HTTPException(status_code=400, detail=f"Failed to prepare transaction: {tx_data.get('errors', 'Unknown error')}")
        
        tx_payload = tx_data["tx_json"]
        print(f"DEBUG: Prepared unsigned transaction payload")
        
    except Exception as e:
        print(f"ERROR: Failed to prepare USDT transfer: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Transaction preparation failed: {str(e)}")
    
    # Verify signature
    payment_payload = {
        'currency': product.get('currency', 'USDT'),
        'price': product.get('price'),
        'product_name': product_name
    }
    message = f"Autobuy payment confirmation {json.dumps(payment_payload, sort_keys=True, separators=(',', ':'))}"
    
    try:
        recovered_address = payment_processor.verify_signature(message, signature)
        if recovered_address.lower() != wallet_address.lower():
            raise HTTPException(status_code=401, detail="Invalid signature")
        print(f"✅ Signature verified for address: {recovered_address}")
    except Exception as e:
        print(f"ERROR: Signature verification failed: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Signature verification failed: {str(e)}")
    
    # Return unsigned transaction payload for wallet signing and submission
    print(f"DEBUG: Prepared transaction payload ready for wallet signing")

    if product_token and product_token in pending_purchase_links:
        product_url = f"{APP_BASE_URL}/redeem/{product_token}"
    else:
        product_url = None
        if product_token:
            print(f"WARNING: product_token {product_token} not found in pending_purchase_links")

    return {
        "status": "pending_wallet_submission",
        "message": "Signature verified. Submit this transaction from the user's wallet to complete payment.",
        "payment_status": "wallet_submission_required",
        "product_url": product_url,
        "payment_tx": tx_payload,
        "details": tx_data.get("details", {}),
        "recipient": recipient_address,
        "amount_usdt": charge_usdt,
        "product": {
            "name": product_name,
            "price": amount_usd,
            "url": product_url,
        }
    }


@app.post("/subscribe")
async def subscribe(request: dict, user=Depends(get_current_user)):
    """Create subscription"""
    decision = decide_purchase(request)
    if decision["status"] != "approved":
        return decision

    product = decision["product"]
    valid, reason = validate(product, request["budget"])
    if not valid:
        return {"status": "rejected", "reason": reason}

    frequency = request.get("frequency_days", 30)
    sub = create_subscription(
        user_id=user["id"],
        product=product,
        budget=request["budget"],
        frequency_days=frequency
    )

    payment_info = {
        "status": "payment_required",
        "subscription": sub,
        "product": product,
        "amount": product["price"],
        "currency": "USDT",
        "frequency_days": frequency
    }
    return JSONResponse(status_code=402, content=payment_info)


# ============ BLOCKCHAIN WALLET ENDPOINTS ============

from .blockchain_requirements import wallet_service
from .blockchain_payment import payment_processor

@app.post("/wallet/check-requirements")
async def check_wallet_requirements(request: dict, user=Depends(get_current_user)):
    """
    Check if user's wallet has:
    1. KITE AI network configured
    2. Sufficient KITE for gas fees
    3. Sufficient USDT for purchases
    
    Returns setup instructions if needed
    """
    wallet_address = request.get("wallet_address")
    if not wallet_address:
        raise HTTPException(status_code=400, detail="wallet_address required")

    requirements = wallet_service.check_wallet_requirements(wallet_address)
    
    return {
        "wallet": wallet_address,
        "requirements": requirements,
        "setup_required": not requirements["ready_to_purchase"],
        "issues": requirements["issues"],
    }


@app.get("/wallet/balances/{wallet_address}")
async def get_wallet_balances(wallet_address: str, user=Depends(get_current_user)):
    """Get real-time KITE and USDT balances from blockchain"""
    kite = wallet_service.get_kite_balance(wallet_address)
    usdc = wallet_service.get_usdt_balance(wallet_address)
    
    return {
        "wallet": wallet_address,
        "kite": kite,
        "usdc": usdc,
        "network": {
            "name": "KITE AI Testnet",
            "chainId": KITE_CHAIN_ID,
            "explorer": "https://testnet.kitescan.ai/",
        }
    }


@app.get("/wallet/ready-for-payment/{wallet_address}")
async def check_wallet_ready_for_payment(wallet_address: str, user=Depends(get_current_user)):
    """
    Check if wallet has BOTH KITE and USDT tokens for payment
    Returns ready status and simple message
    """
    wallet_ready = payment_processor.check_wallet_ready_for_payment(wallet_address)
    
    if not wallet_ready.get("ready", False):
        wallet_ready["formatted_message"] = "Insufficient Fund"
    else:
        wallet_ready["formatted_message"] = "Ready"
    
    return wallet_ready


@app.get("/wallet/network-config")
async def get_network_config():
    """Get KITE AI network configuration for MetaMask"""
    return {
        "network": wallet_service.check_wallet_requirements("0x0")["network"],
        "usdt": wallet_service.check_wallet_requirements("0x0")["usdt"],
    }


@app.get("/wallet/faucets")
async def get_faucet_links():
    """Get faucet links for acquiring test tokens"""
    return wallet_service.get_faucet_info()


@app.post("/payment/prepare")
async def prepare_payment(request: dict, user=Depends(get_current_user)):
    """
    Prepare USDT transfer transaction
    Frontend signs and sends back the transaction
    """
    from_address = request.get("from_address")
    to_address = request.get("to_address")
    amount_usd = request.get("amount_usd")

    if not all([from_address, to_address, amount_usd]):
        raise HTTPException(status_code=400, detail="from_address, to_address, amount_usd required")

    # Validate parameters
    validation = payment_processor.validate_payment_params(from_address, to_address, amount_usd)
    if not validation["valid"]:
        return {"success": False, "errors": validation["errors"]}

    # Prepare transaction
    tx_prep = payment_processor.prepare_usdt_transfer(from_address, to_address, amount_usd)
    
    if tx_prep["success"]:
        # Add gas estimation
        gas_estimate = payment_processor.estimate_gas_cost()
        tx_prep["gas_estimate"] = gas_estimate
    
    return tx_prep


@app.post("/payment/submit")
async def submit_payment(request: dict, user=Depends(get_current_user)):
    """
    Submit signed transaction to blockchain
    Triggered after user signs in MetaMask
    """
    signed_tx = request.get("signed_tx")
    if not signed_tx:
        raise HTTPException(status_code=400, detail="signed_tx required")

    result = payment_processor.send_usdt_transaction(signed_tx)
    
    return result


@app.get("/payment/status/{tx_hash}")
async def get_payment_status(tx_hash: str, user=Depends(get_current_user)):
    """Get real-time transaction status"""
    status = payment_processor.get_transaction_status(tx_hash)
    
    # Also wait briefly for confirmation
    if status.get("status") == "pending":
        confirmation = payment_processor.wait_for_transaction(tx_hash, timeout=30)
        if confirmation.get("success"):
            return confirmation
    
    return status


@app.post("/payment/confirm")
async def confirm_payment_blockchain(request: dict, user=Depends(get_current_user)):
    """
    Confirm payment and verify on blockchain
    Called after transaction is mined
    """
    tx_hash = request.get("tx_hash")
    product_id = request.get("product_id")
    
    if not tx_hash:
        raise HTTPException(status_code=400, detail="tx_hash required")

    # Wait for confirmation
    confirmation = payment_processor.wait_for_transaction(tx_hash)
    
    if not confirmation.get("success"):
        return {
            "status": "failed",
            "error": confirmation.get("error", "Transaction failed"),
            "tx_hash": tx_hash
        }

    # Record on Kite attestation
    attestation = record_attestation_on_kite(
        task_id=tx_hash,
        user_address=request.get("from_address"),
        payment_amount=request.get("amount_usd"),
        output_hash=product_id or ""
    )

    return {
        "status": "confirmed",
        "tx_hash": tx_hash,
        "block_number": confirmation.get("block_number"),
        "transaction_fee_kite": confirmation.get("transaction_fee_kite"),
        "attestation": attestation,
        "explorer_url": confirmation.get("explorer_url")
    }


# Health check
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "services": {
            "commerce": "operational",
            "kite": kite_health_check(),
            "blockchain": "connected" if wallet_service.is_connected() else "disconnected"
        }
    }
