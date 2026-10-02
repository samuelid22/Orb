"use strict";

import { apiUrl } from "./api-url.js";

const CHAIN_ID = 421614;
const CHAIN_HEX = `0x${CHAIN_ID.toString(16)}`;
const PENDING_KEY = "orb-sepolia-pending-payment";
const SESSION_KEY = "orb-wallet-session";
const DISCONNECTED_KEY = "orb-wallet-disconnected";
const ACTIVE_JOB_KEY = "orb-active-paid-job";

export function initWallet({ onBalance }) {
  const el = (id) => document.getElementById(id);
  const panel = el("wallet-panel");
  const feedback = el("wallet-feedback");
  const connectButton = el("wallet-connect");
  const headerButton = el("header-wallet");
  const disconnectButton = el("wallet-disconnect");
  const switchButton = el("wallet-switch");
  const buyButton = el("wallet-buy");
  const retryButton = el("wallet-retry");
  const count = el("credit-count");
  let config = null;
  let token = null;
  let address = null;
  let walletAccount = null;
  let verified = false;
  let disconnected = sessionStorage.getItem(DISCONNECTED_KEY) === "1";
  let balance = 0;
  let busy = false;
  let verifyTimer = null;
  let sessionTimer = null;
  let authEpoch = 0;

  async function json(path, options = {}) {
    const response = await fetch(apiUrl(path), options);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(body.detail || `Request failed (${response.status}).`);
      error.status = response.status;
      throw error;
    }
    return body;
  }

  function headers() {
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  function setFeedback(message) { feedback.textContent = message; }

  function update() {
    el("wallet-address").textContent = address ? `Authenticated wallet · ${address.slice(0, 6)}…${address.slice(-4)}` : "";
    el("wallet-address").title = address || "";
    el("wallet-balance").textContent = `${balance} testnet credit${balance === 1 ? "" : "s"} available`;
    el("wallet-purchase").classList.toggle("hidden", !verified || !config?.enabled);
    disconnectButton.classList.toggle("hidden", !verified);
    disconnectButton.disabled = busy;
    connectButton.textContent = verified ? "Connected" : token ? "Retry session" : walletAccount ? "Sign again" : "Connect and sign";
    connectButton.disabled = busy || verified || !config?.enabled;
    headerButton.textContent = verified ? "Connected" : "Connect Wallet";
    headerButton.setAttribute("aria-label", verified ? "Wallet connected. Open Wallet & Credits" : "Connect wallet");
    headerButton.classList.toggle("connected", verified);
    headerButton.disabled = busy;
    buyButton.disabled = busy || !verified;
    retryButton.disabled = busy || !verified;
    onBalance(balance);
  }

  function clearSession(message = "Wallet session cleared. Connect and sign again.") {
    authEpoch += 1;
    token = null;
    address = null;
    verified = false;
    balance = 0;
    sessionStorage.removeItem(SESSION_KEY);
    clearTimeout(verifyTimer);
    clearTimeout(sessionTimer);
    retryButton.classList.add("hidden");
    setFeedback(message);
    update();
  }

  function requireAuthentication() {
    clearSession("Wallet session expired. Sign again.");
    open();
    connectButton.focus();
  }

  function scheduleExpiry(expiresAt) {
    clearTimeout(sessionTimer);
    const milliseconds = Math.max(0, expiresAt * 1000 - Date.now());
    sessionTimer = setTimeout(() => clearSession("Wallet session expired. Sign again."), milliseconds);
  }

  async function network() {
    if (!window.ethereum?.request) throw new Error("Install an Arbitrum-compatible wallet to connect.");
    const chain = await window.ethereum.request({ method: "eth_chainId" });
    const correct = Number.parseInt(chain, 16) === CHAIN_ID;
    el("wallet-network").textContent = correct ? "Network: Arbitrum Sepolia" : "Wrong network. Switch to Arbitrum Sepolia.";
    switchButton.classList.toggle("hidden", correct);
    return correct;
  }

  async function switchNetwork() {
    if (!window.ethereum?.request) throw new Error("An Arbitrum-compatible wallet is required.");
    try {
      await window.ethereum.request({ method: "wallet_switchEthereumChain", params: [{ chainId: CHAIN_HEX }] });
    } catch (error) {
      if (error?.code !== 4902) throw error;
      await window.ethereum.request({ method: "wallet_addEthereumChain", params: [{ chainId: CHAIN_HEX,
        chainName: "Arbitrum Sepolia", nativeCurrency: { name: "Sepolia Ether", symbol: "ETH", decimals: 18 },
        rpcUrls: ["https://sepolia-rollup.arbitrum.io/rpc"],
        blockExplorerUrls: ["https://sepolia.arbiscan.io"] }] });
    }
    if (!await network()) throw new Error("Switch your wallet to Arbitrum Sepolia before continuing.");
  }

  async function refresh() {
    if (!token) return false;
    const currentToken = token;
    const epoch = authEpoch;
    try {
      const result = await json("/api/orb/credits/balance", { headers: headers() });
      if (token !== currentToken || epoch !== authEpoch) return false;
      balance = result.available;
      verified = true;
      update();
      return true;
    } catch (error) {
      if (token !== currentToken || epoch !== authEpoch) return false;
      if (error.status === 401) clearSession("Wallet session expired. Sign again.");
      else {
        setFeedback(`Could not verify wallet session: ${error.message}`);
        update();
      }
      return false;
    }
  }

  async function restoreSession() {
    if (disconnected) {
      walletAccount = null;
      el("wallet-network").textContent = "Wallet not connected.";
      switchButton.classList.add("hidden");
      update();
      return;
    }
    const epoch = authEpoch;
    const accounts = await window.ethereum?.request?.({ method: "eth_accounts" }) || [];
    if (epoch !== authEpoch) return;
    walletAccount = accounts[0] || null;
    let saved = null;
    try { saved = JSON.parse(sessionStorage.getItem(SESSION_KEY) || "null"); }
    catch { sessionStorage.removeItem(SESSION_KEY); }
    if (!saved) { update(); return; }
    if (!walletAccount || saved.address?.toLowerCase() !== walletAccount.toLowerCase()) {
      clearSession("Wallet account changed. Sign again.");
      return;
    }
    if (typeof saved.token !== "string" || !saved.token ||
        !Number.isFinite(saved.expiresAt) || saved.expiresAt <= Date.now() / 1000) {
      clearSession("Wallet session expired. Sign again.");
      return;
    }
    token = saved.token;
    address = saved.address;
    verified = false;
    scheduleExpiry(saved.expiresAt);
    if (await refresh() && epoch === authEpoch) {
      setFeedback("Wallet session restored. Testnet credits only.");
      const pending = pendingPayment();
      if (pending && pending.wallet.toLowerCase() === address.toLowerCase()) retryButton.classList.remove("hidden");
    }
  }

  async function connect() {
    if (busy) return;
    busy = true;
    disconnected = false;
    sessionStorage.removeItem(DISCONNECTED_KEY);
    let attemptEpoch = authEpoch;
    update();
    try {
      if (!config?.enabled) throw new Error("Testnet credits are not configured on this Orb server.");
      const accounts = await window.ethereum?.request?.({ method: "eth_requestAccounts" });
      if (!accounts?.[0]) throw new Error("No wallet account was selected.");
      if (attemptEpoch !== authEpoch && walletAccount?.toLowerCase() !== accounts[0].toLowerCase()) return;
      walletAccount = accounts[0];
      if (!await network()) await switchNetwork();
      if (walletAccount?.toLowerCase() !== accounts[0].toLowerCase()) return;
      attemptEpoch = authEpoch;
      const challenge = await json("/api/orb/wallet/challenge", { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ address: accounts[0] }) });
      const signature = await window.ethereum.request({ method: "personal_sign", params: [challenge.message, accounts[0]] });
      if (attemptEpoch !== authEpoch || walletAccount?.toLowerCase() !== accounts[0].toLowerCase()) return;
      const session = await json("/api/orb/wallet/sign-in", { method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nonce: challenge.nonce, signature }) });
      if (attemptEpoch !== authEpoch || walletAccount?.toLowerCase() !== accounts[0].toLowerCase()) return;
      if (typeof session.token !== "string" || !session.token ||
          session.wallet?.toLowerCase() !== accounts[0].toLowerCase() ||
          !Number.isFinite(session.expires_at) || session.expires_at <= Date.now() / 1000) {
        throw new Error("Wallet session could not be verified. Sign again.");
      }
      token = session.token;
      address = session.wallet;
      verified = false;
      sessionStorage.setItem(SESSION_KEY, JSON.stringify({ token, address, expiresAt: session.expires_at }));
      scheduleExpiry(session.expires_at);
      setFeedback("Wallet authenticated for this session. Testnet credits only.");
      update();
      if (!await refresh()) return;
      const pending = pendingPayment();
      if (pending && pending.wallet.toLowerCase() === address.toLowerCase()) retryButton.classList.remove("hidden");
    } catch (error) {
      if (attemptEpoch === authEpoch) clearSession(error.message || "Wallet connection was cancelled.");
    } finally {
      busy = false;
      update();
    }
  }

  function pendingPayment() {
    try { return JSON.parse(sessionStorage.getItem(PENDING_KEY) || "null"); }
    catch { return null; }
  }

  function formatTestnetEth(wei) {
    const units = BigInt(wei);
    const whole = units / 1000000000000000000n;
    const fraction = (units % 1000000000000000000n).toString().padStart(18, "0").replace(/0+$/, "");
    return `${whole}${fraction ? `.${fraction}` : ""}`;
  }

  function formatUsdg(units) {
    const value = BigInt(units);
    const fraction = (value % 1000000n).toString().padStart(6, "0").replace(/0+$/, "").padEnd(2, "0");
    return `${value / 1000000n}.${fraction}`;
  }

  function showPrice(quote = null) {
    if (config?.payment_method === "usdg") {
      el("credit-price").textContent = quote
        ? `${quote.credits} credits · ${formatUsdg(quote.amount_base_units)} test USDG. Quote expires in 15 minutes.`
        : "Get a server quote for the exact test USDG price. Arbitrum Sepolia ETH is needed for gas.";
    } else if (config) {
      el("credit-price").textContent = `${formatTestnetEth(BigInt(config.price_wei) * BigInt(count.value))} testnet ETH for ${count.value} credit${count.value === "1" ? "" : "s"} (plus gas). Quote expires in 15 minutes.`;
    }
  }

  async function verifyPending(attempts = 0) {
    const pending = pendingPayment();
    if (!pending || !verified || !token || pending.wallet.toLowerCase() !== address?.toLowerCase()) return;
    const currentToken = token;
    const epoch = authEpoch;
    retryButton.classList.remove("hidden");
    setFeedback("Verifying payment on Arbitrum Sepolia…");
    try {
      const result = await json(`/api/orb/credits/quotes/${encodeURIComponent(pending.quoteId)}/verify`, {
        method: "POST", headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ tx_hash: pending.txHash }),
      });
      if (currentToken !== token || epoch !== authEpoch) return;
      sessionStorage.removeItem(PENDING_KEY);
      retryButton.classList.add("hidden");
      balance = result.balance.available;
      setFeedback(`${result.credits} testnet credit${result.credits === 1 ? "" : "s"} added.`);
      update();
    } catch (error) {
      if (currentToken !== token || epoch !== authEpoch) return;
      if (error.status === 409 && attempts < 30) {
        setFeedback("Waiting for the required testnet confirmations…");
        verifyTimer = setTimeout(() => void verifyPending(attempts + 1), 5000);
      } else setFeedback(`Verification pending: ${error.message} Use “Check pending transaction” to retry.`);
    }
  }

  async function buy() {
    if (busy || !token) return;
    if (pendingPayment()) {
      setFeedback("A payment is pending. Check pending transaction before buying again.");
      retryButton.classList.remove("hidden");
      return;
    }
    const payingWallet = address;
    let epoch = authEpoch;
    busy = true;
    update();
    try {
      if (!await network()) await switchNetwork();
      if (!verified || !address || payingWallet?.toLowerCase() !== walletAccount?.toLowerCase()) {
        throw new Error("Wallet changed. Sign again before buying credits.");
      }
      epoch = authEpoch;
      const quote = await json("/api/orb/credits/quotes", { method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ credits: Number(count.value) }) });
      if (quote.chain_id !== CHAIN_ID) throw new Error("Server quote has the wrong chain.");
      if (epoch !== authEpoch || !verified) throw new Error("Wallet changed. Sign again before buying credits.");
      if (quote.expires_at && quote.expires_at <= Date.now() / 1000) throw new Error("Payment quote expired. Request a new quote.");
      if (config?.payment_method === "usdg") {
        if (quote.payment_method !== "usdg" || quote.token_symbol !== "USDG" || quote.token_decimals !== 6
            || quote.token_contract?.toLowerCase() !== config.token_contract?.toLowerCase()
            || quote.to?.toLowerCase() !== quote.token_contract.toLowerCase()
            || quote.wallet?.toLowerCase() !== payingWallet.toLowerCase() || quote.value_wei !== "0"
            || !/^0x[0-9a-fA-F]{40}$/.test(quote.receiver)
            || !/^[1-9][0-9]*$/.test(quote.amount_base_units)) {
          throw new Error("Server returned an invalid USDG quote.");
        }
        const expectedData = `0xa9059cbb${quote.receiver.slice(2).toLowerCase().padStart(64, "0")}${BigInt(quote.amount_base_units).toString(16).padStart(64, "0")}`;
        if (quote.data?.toLowerCase() !== expectedData) throw new Error("Server returned invalid USDG transfer data.");
        showPrice(quote);
      }
      setFeedback("Confirm the Arbitrum Sepolia testnet transfer in your wallet…");
      const txHash = await window.ethereum.request({ method: "eth_sendTransaction", params: [{
        from: payingWallet, to: quote.to, value: `0x${BigInt(quote.value_wei).toString(16)}`, data: quote.data,
      }] });
      if (!/^0x[0-9a-fA-F]{64}$/.test(txHash)) throw new Error("Wallet did not return a valid transaction hash.");
      // Remember a submitted transfer even if the account changes while the
      // wallet approval dialog is open. Only its original wallet can verify it.
      sessionStorage.setItem(PENDING_KEY, JSON.stringify({ quoteId: quote.quote_id, txHash, wallet: payingWallet }));
      setFeedback("Payment submitted. Verifying payment…");
      void verifyPending();
    } catch (error) {
      const feeError = [error?.message, error?.data?.message, error?.data?.originalError?.message]
        .filter((message) => typeof message === "string").join(" ");
      if (/(?:max\s*fee\s*per\s*gas|maxFeePerGas).*(?:base\s*fee|baseFee)/i.test(feeError)) {
        setFeedback("MetaMask's gas estimate fell below Arbitrum Sepolia's current base fee. Check your wallet activity before retrying Buy Credits with a fresh Market or Aggressive fee estimate. Orb did not receive a transaction hash.");
      } else if (error?.code === 4001) setFeedback("Payment cancelled in your wallet. No new credits were charged.");
      else if (config?.payment_method === "usdg" && /insufficient|exceeds balance|transfer amount exceeds/i.test(feeError)
          && /token|usdg|transfer amount|balanceOf/i.test(feeError)) {
        setFeedback("Insufficient test USDG. Obtain Paxos test USDG on Arbitrum Sepolia and try again.");
      } else if (/insufficient funds|insufficient.*gas|gas.*insufficient/i.test(feeError)) {
        setFeedback("Insufficient Arbitrum Sepolia ETH for gas. Add testnet ETH and try again.");
      } else setFeedback(error.message || "Testnet payment was cancelled.");
    }
    finally { busy = false; update(); }
  }

  async function disconnect() {
    if (!verified || !token || busy) return;
    const oldToken = token;
    busy = true;
    disconnected = true;
    sessionStorage.setItem(DISCONNECTED_KEY, "1");
    walletAccount = null;
    clearSession("Disconnecting wallet from Orb…");
    sessionStorage.removeItem(PENDING_KEY);
    sessionStorage.removeItem(ACTIVE_JOB_KEY);
    el("wallet-network").textContent = "Wallet not connected.";
    switchButton.classList.add("hidden");
    update();
    let revoked = false;
    try {
      await json("/api/orb/wallet/logout", { method: "POST",
        headers: { Authorization: `Bearer ${oldToken}` } });
      revoked = true;
    } catch (error) {
      revoked = error.status === 401;
    }
    try {
      await window.ethereum?.request?.({ method: "wallet_revokePermissions",
        params: [{ eth_accounts: {} }] });
    } catch { /* Some wallets do not support site permission revocation. */ }
    setFeedback(revoked ? "Wallet disconnected from Orb." :
      "Wallet disconnected locally. Server sign-out could not be confirmed; the old session will expire.");
    busy = false;
    update();
  }

  function open() { panel.classList.remove("hidden"); headerButton.setAttribute("aria-expanded", "true"); el("wallet-close").focus(); }
  function close(restoreFocus = false) {
    panel.classList.add("hidden");
    headerButton.setAttribute("aria-expanded", "false");
    if (restoreFocus) headerButton.focus();
  }

  el("wallet-close").addEventListener("click", () => close(true));
  connectButton.addEventListener("click", () => void (token && !verified ? refresh() : connect()));
  headerButton.addEventListener("click", () => {
    open();
    if (!verified) void (token ? refresh() : connect());
  });
  disconnectButton.addEventListener("click", () => void disconnect());
  switchButton.addEventListener("click", async () => {
    try { await switchNetwork(); setFeedback("Arbitrum Sepolia selected. Connect and sign to continue."); }
    catch (error) { setFeedback(error.message || "Network switch cancelled."); }
  });
  buyButton.addEventListener("click", () => void buy());
  retryButton.addEventListener("click", () => void verifyPending());
  count.addEventListener("change", () => showPrice());
  window.ethereum?.on?.("accountsChanged", (accounts) => {
    if (disconnected) return;
    const next = accounts?.[0] || null;
    if (next?.toLowerCase() === walletAccount?.toLowerCase()) return;
    walletAccount = next;
    clearSession("Wallet account changed. Sign again.");
  });
  window.ethereum?.on?.("chainChanged", () => {
    if (disconnected) return;
    clearSession("Wallet network changed. Switch to Arbitrum Sepolia and sign again.");
    void network().catch(() => {});
  });
  void (async () => {
    try {
      const loadedConfig = await json("/api/orb/credits/config");
      if (import.meta.env.VITE_ORB_DEPLOYMENT_TARGET === "usdg-staging"
          && (loadedConfig.payment_method !== "usdg" || loadedConfig.deployment_target !== "usdg-staging")) {
        throw new Error("This preview requires the isolated USDG staging backend.");
      }
      config = loadedConfig;
      if (config.payment_method === "usdg") {
        buyButton.textContent = "Buy credits with USDG";
        el("wallet-testnet-notice").textContent = "Paxos USDG · Arbitrum Sepolia. Testnet USDG has no monetary value. Arbitrum Sepolia ETH is still needed for gas.";
      }
      if (!config.enabled) setFeedback("Testnet payments are not configured on this server.");
      else setFeedback("Connect a wallet to see your testnet credits.");
      count.dispatchEvent(new Event("change"));
      if (window.ethereum?.request) {
        await network().catch(() => {});
        await restoreSession();
      }
    } catch { setFeedback("Could not load testnet payment configuration."); }
    update();
  })();
  update();
  return { open, close, refresh, headers, requireAuthentication, hasCredit: () => verified && balance > 0,
    isAuthenticated: () => verified, walletAddress: () => verified ? address : null,
    isEnabled: () => !!config?.enabled };
}
