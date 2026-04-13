import React, { useState, useEffect } from "react";
import axios from "axios";
import "./App.css";

export default function App() {
  const [screen, setScreen] = useState("login");
  const [token, setToken] = useState(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [walletAddress, setWalletAddress] = useState(null);
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState(null);
  
  // Product search
  const [productQuery, setProductQuery] = useState("");
  const [productBudget, setProductBudget] = useState("");
  const [productResults, setProductResults] = useState(null);
  const [searchingProduct, setSearchingProduct] = useState(false);
  const [confirmingPayment, setConfirmingPayment] = useState(false);
  const [confirmPaymentResult, setConfirmPaymentResult] = useState(null);
  
  // Kite health
  const [kiteStatus, setKiteStatus] = useState(null);
  const [settlements, setSettlements] = useState([]);
  const [remainingBudget, setRemainingBudget] = useState(null);

  const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8001";
  const headers = token ? { Authorization: `Bearer ${token}` } : {};

  // Debug - log API base on mount
  useEffect(() => {
    console.log("🚀 App loaded");
    console.log("📡 API_BASE:", API_BASE);
    console.log("🌍 Environment REACT_APP_API_URL:", process.env.REACT_APP_API_URL);
  }, [API_BASE]);

  const handleRegister = async () => {
    console.log("🔵 Register button clicked");
    
    if (!username.trim() || !password.trim()) {
      console.warn("⚠️ Username or password empty");
      setAuthError("Please enter username and password");
      return;
    }

    setAuthLoading(true);
    setAuthError(null);
    
    try {
      console.log("📤 Sending register request to:", `${API_BASE}/register`);
      const res = await axios.post(`${API_BASE}/register`, { username, password });
      console.log("✅ Registration successful:", res.data);
      setToken(res.data.token);
      setScreen("commerce");
      setUsername("");
      setPassword("");
      setAuthError(null);
    } catch (e) {
      console.error("❌ Registration failed:", e);
      const errorMsg = e.response?.data?.detail || e.message || "Unknown error";
      console.error("Error details:", errorMsg);
      setAuthError(`Registration failed: ${errorMsg}`);
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogin = async () => {
    console.log("🔵 Login button clicked");
    
    if (!username.trim() || !password.trim()) {
      console.warn("⚠️ Username or password empty");
      setAuthError("Please enter username and password");
      return;
    }

    setAuthLoading(true);
    setAuthError(null);
    
    try {
      console.log("📤 Sending login request to:", `${API_BASE}/login`);
      const res = await axios.post(`${API_BASE}/login`, { username, password });
      console.log("✅ Login successful:", res.data);
      setToken(res.data.token);
      setScreen("commerce");
      setUsername("");
      setPassword("");
      setAuthError(null);
      checkKiteHealth();
      await loadKiteSettlements();
    } catch (e) {
      console.error("❌ Login failed:", e);
      const errorMsg = e.response?.data?.detail || e.message || "Unknown error";
      console.error("Error details:", errorMsg);
      console.error("Full error:", e);
      setAuthError(`Login failed: ${errorMsg}`);
    } finally {
      setAuthLoading(false);
    }
  };

  const checkKiteHealth = async () => {
    try {
      const res = await axios.get(`${API_BASE}/kite/health`);
      setKiteStatus(res.data);
    } catch (e) {
      console.error("Kite health check failed:", e);
    }
  };

  const loadKiteSettlements = async () => {
    try {
      const res = await axios.get(`${API_BASE}/kite/settlements`, { headers });
      setSettlements(res.data.settlements || []);
    } catch (e) {
      console.error("Failed to load kite settlements:", e);
    }
  };

  const getApiErrorMessage = (error) => {
    if (!error) return "Unknown error";
    if (typeof error === "string") return error;
    if (error.detail) return error.detail;
    if (error.message) return error.message;
    return JSON.stringify(error);
  };

  const handleProductSearch = async () => {
    if (!productQuery.trim() || !productBudget || Number(productBudget) <= 0) {
      alert("Enter product and budget");
      return;
    }

    setSearchingProduct(true);
    setProductResults(null);
    setConfirmPaymentResult(null);
    setRemainingBudget(Number(productBudget));

    try {
      const res = await axios.post(
        `${API_BASE}/buy`,
        {
          query: productQuery,
          budget: Number(productBudget),
          search_online: true
        },
        { headers }
      );

      setProductResults(res.data);
      if (res.data.status === "payment_required") {
        const used = Number(res.data.product?.price || 0);
        setRemainingBudget(Number(productBudget) - used);
      }
    } catch (e) {
      // Handle 402 (Payment Required) as success
      if (e.response?.status === 402) {
        setProductResults(e.response.data);
        const used = Number(e.response.data.product?.price || 0);
        setRemainingBudget(Number(productBudget) - used);
      } else {
        const error = getApiErrorMessage(e.response?.data || e.message);
        setProductResults({ status: "error", error });
      }
    } finally {
      setSearchingProduct(false);
    }
  };

  const connectWallet = async () => {
    if (!window.ethereum) {
      alert("MetaMask not detected. Please install MetaMask.");
      return;
    }

    // Check for multiple wallet providers
    const providers = [];
    if (window.ethereum) {
      providers.push("MetaMask");
      console.log("🔍 MetaMask detected, isMetaMask:", window.ethereum.isMetaMask);
      console.log("🔍 MetaMask version:", window.ethereum.isMetaMask ? "MetaMask" : "Unknown MetaMask-like wallet");
    }
    if (window.coinbaseWalletExtension) providers.push("Coinbase Wallet");
    if (window.trustwallet) providers.push("Trust Wallet");
    if (window.binance) providers.push("Binance Wallet");
    if (window.phantom) providers.push("Phantom");
    if (window.solflare) providers.push("Solflare");
    if (window.exodus) providers.push("Exodus");
    if (window.tally) providers.push("Tally");
    if (window.brave) providers.push("Brave Wallet");
    
    console.log("🔍 Available wallet providers:", providers);
    if (providers.length > 1) {
      console.warn("⚠️ Multiple wallet extensions detected! This could cause signature conflicts.");
      console.warn("Available providers:", providers);
      alert("WARNING: Multiple wallet extensions detected! This may cause signature issues.");
    }

    // Check if the ethereum provider is actually MetaMask
    if (window.ethereum && !window.ethereum.isMetaMask) {
      console.warn("⚠️ window.ethereum is not MetaMask! It might be another wallet.");
      console.warn("Provider name:", window.ethereum.constructor?.name);
      console.warn("Provider isCoinbaseWallet:", window.ethereum.isCoinbaseWallet);
      console.warn("Provider isTrust:", window.ethereum.isTrust);
      console.warn("Provider isBraveWallet:", window.ethereum.isBraveWallet);
      alert("WARNING: Your browser has a non-MetaMask ethereum provider. This could cause signature issues.");
    }

    try {
      const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
      const address = accounts[0];
      setWalletAddress(address);
      
      // List all available accounts
      const allAccounts = await window.ethereum.request({ method: "eth_accounts" });
      console.log("✅ Connected wallet:", address);
      console.log("📋 All available accounts in MetaMask:", allAccounts);
      
      if (allAccounts.length > 1) {
        console.warn("⚠️ You have multiple accounts in MetaMask!");
        console.warn("Available accounts:");
        allAccounts.forEach((acc, i) => console.warn(`  ${i+1}. ${acc}`));
        console.warn(`Make sure ${address} is selected when signing!`);
      }
      
      return address;
    } catch (e) {
      console.error("Wallet connect failed", e);
      alert("Wallet connection failed: " + e.message);
      return null;
    }
  };

  const handleConfirmProductPayment = async () => {
    if (!productResults || productResults.status !== "payment_required") {
      alert("No payable product selected");
      return;
    }

    // Always get the current connected account from MetaMask
    let address;
    try {
      const accounts = await window.ethereum.request({ method: "eth_accounts" });
      address = accounts[0];
      if (!address) {
        address = await connectWallet();
        if (!address) return;
      }
      // Update state to keep UI in sync
      setWalletAddress(address);
    } catch (e) {
      console.error("Failed to get current account:", e);
      alert("Please connect your wallet first");
      return;
    }

    console.log("DEBUG: Using wallet address for payment:", address);

    // List all accounts for debugging
    try {
      const allAccounts = await window.ethereum.request({ method: "eth_accounts" });
      console.log("📋 All available accounts in MetaMask:", allAccounts);
      
      if (allAccounts.length > 1) {
        console.warn("⚠️ Multiple accounts detected!");
        console.warn("Available accounts:");
        allAccounts.forEach((acc, i) => console.warn(`  ${i+1}. ${acc}`));
        console.warn(`Make sure ${address} is selected when signing!`);
      }
    } catch (e) {
      console.log("Could not list accounts:", e);
    }

    const product = productResults.product;

    // Sanitize product name - remove newlines and extra whitespace
    const cleanProductName = product.name.replace(/\s+/g, ' ').trim();
    
    // Create a clean product object with sanitized name for both signing AND sending
    const cleanProduct = {
      ...product,
      name: cleanProductName
    };
    
    const paymentPayload = {
      currency: cleanProduct.currency || "USDT",
      price: cleanProduct.price,
      product_name: cleanProductName
    };

    const purchaseToken = productResults.product?.purchase_token;

    // Create message with keys in sorted order (matching backend JSON dumps sort_keys=True)
    const sortedKeys = Object.keys(paymentPayload).sort();
    const sortedPayload = {};
    sortedKeys.forEach(key => {
      sortedPayload[key] = paymentPayload[key];
    });
    const message = `Autobuy payment confirmation ${JSON.stringify(sortedPayload)}`;

    console.log("DEBUG: Payment payload:", paymentPayload);
    console.log("DEBUG: Sorted payload:", sortedPayload);
    console.log("DEBUG: Message to sign:", message);
    console.log("DEBUG: Wallet address:", address);

    try {
      console.log("DEBUG: About to request signature from MetaMask");
      console.log("DEBUG: IMPORTANT - Make sure the correct account is selected in MetaMask popup!");
      console.log(`DEBUG: Expected account: ${address}`);
      
      // Request accounts again to ensure we have the latest
      const currentAccounts = await window.ethereum.request({
        method: "eth_accounts",
      });
      const currentAddress = currentAccounts[0];
      console.log(`DEBUG: Current active account: ${currentAddress}`);
      
      if (currentAddress.toLowerCase() !== address.toLowerCase()) {
        console.warn(`⚠️ Account mismatch! Current: ${currentAddress}, Expected: ${address}`);
        console.warn("Please switch to the correct account in MetaMask first!");
        alert(`Please switch to account ${address} in MetaMask before signing!`);
        return;
      }
      
      // Double-check we're on the right account right before signing
      console.log("🔍 Double-checking account before signing...");
      const finalCheckAccounts = await window.ethereum.request({ method: "eth_accounts" });
      const finalAddress = finalCheckAccounts[0];
      if (finalAddress.toLowerCase() !== address.toLowerCase()) {
        console.error(`❌ Account changed! Was: ${address}, Now: ${finalAddress}`);
        alert(`Account changed! Please keep ${address} selected in MetaMask.`);
        return;
      }
      
      console.log("✅ Account confirmed, requesting signature...");
      console.log("DEBUG: Final message being signed:", JSON.stringify(message));
      console.log("DEBUG: Message length:", message.length);
      console.log("DEBUG: Message bytes (first 100):", message.slice(0, 100));
      
      // Check wallet provider details right before signing
      console.log("🔍 About to request signature from ethereum provider...");
      console.log("🔍 Provider details:");
      console.log("  - isMetaMask:", window.ethereum?.isMetaMask);
      console.log("  - isCoinbaseWallet:", window.ethereum?.isCoinbaseWallet);
      console.log("  - isTrust:", window.ethereum?.isTrust);
      console.log("  - provider name:", window.ethereum?.constructor?.name);
      console.log("  - provider keys:", Object.keys(window.ethereum || {}));
      
      // Check for other wallet extensions
      const otherWallets = [];
      if (window.coinbaseWalletExtension) otherWallets.push("Coinbase Wallet");
      if (window.trustwallet) otherWallets.push("Trust Wallet");
      if (window.binance) otherWallets.push("Binance Wallet");
      if (window.phantom) otherWallets.push("Phantom");
      if (window.solflare) otherWallets.push("Solflare");
      if (window.exodus) otherWallets.push("Exodus");
      if (window.tally) otherWallets.push("Tally");
      if (window.brave) otherWallets.push("Brave Wallet");
      
      if (otherWallets.length > 0) {
        console.warn("⚠️ Other wallet extensions detected:", otherWallets);
        console.warn("These might be intercepting your MetaMask requests!");
        alert("WARNING: Other wallet extensions detected! They might be signing instead of MetaMask.");
      }
      
      const signature = await window.ethereum.request({
        method: "personal_sign",
        params: [message, finalAddress]
      });

      console.log("☑️ Signature received:", signature);
      console.log("DEBUG: Signature length:", signature.length);
      console.log("DEBUG: Signature starts with 0x:", signature.startsWith("0x"));
      console.log("DEBUG: Signature length:", signature.length);
      console.log("DEBUG: Clean product being sent:", cleanProduct);
      console.log("⚠️ IMPORTANT: If you see 401 Unauthorized error, check that you signed with the correct MetaMask account!");

      setConfirmingPayment(true);
      setConfirmPaymentResult(null);

      const response = await axios.post(
        `${API_BASE}/confirm-payment`,
        {
          product: cleanProduct,
          product_token: purchaseToken,
          wallet_address: address,
          signature
        },
        { headers }
      );

      if (response.data?.payment_tx) {
        console.log("DEBUG: Unsigned payment tx payload:", response.data.payment_tx);
        const txHash = await window.ethereum.request({
          method: "eth_sendTransaction",
          params: [response.data.payment_tx]
        });

        setConfirmPaymentResult({
          status: "success",
          data: {
            ...response.data,
            payment_status: "wallet_submission_completed"
          },
          txHash,
          message: "Payment submitted from wallet."
        });
      } else {
        setConfirmPaymentResult({
          status: "success",
          data: {
            ...response.data,
            payment_status: response.data?.payment_status || response.data?.status || "completed"
          },
          txHash: null,
          message: response.data?.message || "Payment flow completed."
        });
      }
    } catch (e) {
      const error = getApiErrorMessage(e.response?.data || e.message || e);
      setConfirmPaymentResult({ status: "error", error });
    } finally {
      setConfirmingPayment(false);
    }
  };

  const handleLogout = () => {
    setToken(null);
    setScreen("login");
    setWalletAddress(null);
    setProductResults(null);
    setConfirmPaymentResult(null);
    setKiteStatus(null);
    setSettlements([]);
    setRemainingBudget(null);
    setAuthError(null);
  };

  return (
    <div className="App">
      <header className="header">
        <h1>🤖 Valora AutoBuy Agent AI E-Commerces</h1>
        {token && (
          <div>
            <button onClick={handleLogout} className="logout-btn">Logout</button>
          </div>
        )}
      </header>

      {/* Login / Register */}
      {screen === "login" && (
        <div className="auth-container">
          <div className="auth-box">
            <h2>Get Started</h2>
            {authError && (
              <div style={{
                background: '#fee',
                color: '#c33',
                padding: '12px',
                borderRadius: '6px',
                marginBottom: '12px',
                border: '1px solid #fcc'
              }}>
                {authError}
              </div>
            )}
            <input
              type="text"
              placeholder="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={authLoading}
            />
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={authLoading}
            />
            <button 
              onClick={handleLogin}
              disabled={authLoading || !username.trim() || !password.trim()}
              style={{opacity: authLoading || !username.trim() || !password.trim() ? 0.6 : 1}}
            >
              {authLoading ? "🔄 Logging in..." : "Login"}
            </button>
            <button 
              onClick={handleRegister} 
              className="secondary"
              disabled={authLoading || !username.trim() || !password.trim()}
              style={{opacity: authLoading || !username.trim() || !password.trim() ? 0.6 : 1}}
            >
              {authLoading ? "🔄 Registering..." : "Register"}
            </button>
          </div>
        </div>
      )}

      {/* Commerce */}
      {screen === "commerce" && token && (
        <div className="container">
          <div className="kite-status">
            {kiteStatus && (
              <p>
                🔗 Kite: <strong>{kiteStatus.status}</strong> on{" "}
                {kiteStatus.network}
              </p>
            )}
          </div>

          <div className="product-search-box">
            
            {/* Wallet Connection */}
            {!walletAddress ? (
              <div style={{marginBottom: '20px'}}>
                <button onClick={connectWallet} className="connect-wallet-btn">
                  🔐 Connect MetaMask Wallet
                </button>
              </div>
            ) : (
              <div style={{marginBottom: '20px'}} />
            )}

            {walletAddress && (
              <>
                <input
                  type="text"
                  placeholder="e.g. laptop $500 to $600"
                  value={productQuery}
                  onChange={(e) => setProductQuery(e.target.value)}
                />
                <input
                  type="number"
                  placeholder="Budget (USD / USDC)"
                  value={productBudget}
                  onChange={(e) => setProductBudget(e.target.value)}
                />
                <button onClick={handleProductSearch} disabled={searchingProduct}>
                  {searchingProduct ? "🔍 Searching..." : "🔍 Search Product"}
                </button>

                {productResults && (
                  <div className="product-results">
                    {productResults.status === "error" ? (
                      <p className="error">Error: {productResults.error}</p>
                    ) : productResults.status === "payment_required" ? (
                      <>
                        <h3>Best Match</h3>
                        <p>{productResults.product.name}</p>
                        <p>Price: ${productResults.product.price.toFixed(2)}</p>
                        <p>Source: {productResults.product.store || productResults.product.source}</p>
                        <p>Remaining budget: ${remainingBudget != null ? remainingBudget.toFixed(2) : 'N/A'}</p>
                        <p>In-range: {productResults.product.price <= Number(productBudget) ? 'yes' : 'no'}</p>
                        <p>Not sponsor: {(!productResults.product.name.toLowerCase().includes('ad based') && !productResults.product.name.toLowerCase().includes('sponsored')) ? 'yes' : 'no'}</p>
                        <p className="payment-message">{productResults.message}</p>

                        <h4>Top Results</h4>
                        <ul>
                          {productResults.search_results?.map((item, idx) => (
                            <li key={idx}>
                              <strong>{item.name}</strong> - ${item.price.toFixed(2)} - {item.store}
                            </li>
                          ))}
                        </ul>

                        <div className="payment-confirmation">
                          <button onClick={handleConfirmProductPayment} disabled={confirmingPayment}>
                            {confirmingPayment ? "⏳ Confirming payment..." : "💳 Confirm KITE Payment"}
                          </button>

                          {confirmPaymentResult && confirmPaymentResult.status === "success" && (
                            <div className="success">
                              <h5>✅ Payment Settled on KITE</h5>
                              <p>Tx Hash: {confirmPaymentResult.txHash || confirmPaymentResult.data?.tx_hash || "Pending"}</p>
                              <p>Status: {confirmPaymentResult.txHash ? "Submitted from wallet" : confirmPaymentResult.data?.payment_status || confirmPaymentResult.message || "Submitted"}</p>
                              {(confirmPaymentResult.data?.product_url || confirmPaymentResult.data?.product?.url) ? (
                                <p><a href={confirmPaymentResult.data.product_url || confirmPaymentResult.data.product.url} target="_blank" rel="noreferrer">🔗 Open secured purchase link</a></p>
                              ) : (
                                <p>Your service charge payment is complete. A protected purchase URL will be shown once confirmation is complete.</p>
                              )}
                            </div>
                          )}

                          {confirmPaymentResult && confirmPaymentResult.status === "error" && (
                            <div className="error">Error: {confirmPaymentResult.error}</div>
                          )}
                        </div>
                      </>
                    ) : (
                      <p>No matching product found within budget.</p>
                    )}
                  </div>
                )}
              </>
            )}
          </div>

          {/* Settlements on Kite */}
          {settlements.length > 0 && (
            <div className="settlements-box">
              <h3>Kite Settlements ({settlements.length})</h3>
              <div className="settlement-list">
                {settlements.map((s) => (
                  <div key={s.settlement_id} className="settlement-item">
                    <p>🧾 ID: {s.settlement_id}</p>
                    <p>Amount: ${s.amount}</p>
                    <p>Tx: {s.tx_hash.substring(0, 20)}...</p>
                    <p>Status: <strong>{s.status}</strong></p>
                    <small>{new Date(s.settled_at).toLocaleString()}</small>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

    </div>
  );
}