"use strict";

import { apiUrl } from "./api-url.js";

const CHAIN_ID = 421614;
const CHAIN_HEX = `0x${CHAIN_ID.toString(16)}`;
const PENDING_KEY = "orb-sepolia-pending-payment";

export function initWallet({ onBalance }) {
  const el = (id) => document.getElementById(id);
  const panel = el("wallet-panel");
  const feedback = el("wallet-feedback");
  const connectButton = el("wallet-connect");
  const switchButton = el("wallet-switch");
  const buyButton = el("wallet-buy");
  const retryButton = el("wallet-retry");
  const count = el("credit-count");
  let config = null;
  let token = null;
  let address = null;
  let balance = 0;
  let busy = false;
  let verifyTimer = null;

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
    el("wallet-address").textContent = address ? `${address.slice(0, 6)}…${address.slice(-4)}` : "";
    el("wallet-address").title = address || "";
    el("wallet-balance").textContent = `${balance} testnet credit${balance === 1 ? "" : "s"} available`;
    el("wallet-purchase").classList.toggle("hidden", !token || !config?.enabled);
    connectButton.textContent = token ? "Sign again" : "Connect and sign";
    connectButton.disabled = busy || !config?.enabled;
    buyButton.disabled = busy || !token;
    retryButton.disabled = busy || !token;
    onBalance(balance);
  }

  function clearSession(message = "Wallet session cleared. Connect and sign again.") {
    token = null;
    address = null;
    balance = 0;
    clearTimeout(verifyTimer);
    setFeedback(message);
    update();
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
    if (!token) return;
    try {
      const result = await json("/api/orb/credits/balance", { headers: headers() });
      balance = result.available;
      update();
    } catch (error) {
      if (error.status === 401) clearSession("Wallet session expired. Sign again.");
      else setFeedback(`Could not refresh balance: ${error.message}`);
    }
  }

  async function connect() {
    if (busy) return;
    busy = true;
    update();
    try {
      if (!config?.enabled) throw new Error("Testnet credits are not configured on this Orb server.");
      const accounts = await window.ethereum?.request?.({ method: "eth_requestAccounts" });
      if (!accounts?.[0]) throw new Error("No wallet account was selected.");
      if (!await network()) await switchNetwork();
      const challenge = await json("/api/orb/wallet/challenge", { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ address: accounts[0] }) });
      const signature = await window.ethereum.request({ method: "personal_sign", params: [challenge.message, accounts[0]] });
      const session = await json("/api/orb/wallet/sign-in", { method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nonce: challenge.nonce, signature }) });
      token = session.token;
      address = session.wallet;
      setFeedback("Wallet authenticated for this session. Testnet credits only.");
      await refresh();
      const pending = pendingPayment();
      if (pending && pending.wallet.toLowerCase() === address.toLowerCase()) retryButton.classList.remove("hidden");
    } catch (error) {
      clearSession(error.message || "Wallet connection was cancelled.");
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

  async function verifyPending(attempts = 0) {
    const pending = pendingPayment();
    if (!pending || !token || pending.wallet.toLowerCase() !== address?.toLowerCase()) return;
    retryButton.classList.remove("hidden");
    setFeedback(`Verifying transaction ${pending.txHash.slice(0, 10)}… on Arbitrum Sepolia.`);
    try {
      const result = await json(`/api/orb/credits/quotes/${encodeURIComponent(pending.quoteId)}/verify`, {
        method: "POST", headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ tx_hash: pending.txHash }),
      });
      sessionStorage.removeItem(PENDING_KEY);
      retryButton.classList.add("hidden");
      balance = result.balance.available;
      setFeedback(`${result.credits} testnet credit${result.credits === 1 ? "" : "s"} added.`);
      update();
    } catch (error) {
      if (error.status === 409 && attempts < 30) {
        setFeedback("Waiting for the required testnet confirmations…");
        verifyTimer = setTimeout(() => void verifyPending(attempts + 1), 5000);
      } else setFeedback(`Verification pending: ${error.message} Use “Check pending transaction” to retry.`);
    }
  }

  async function buy() {
    if (busy || !token) return;
    busy = true;
    update();
    try {
      if (!await network()) await switchNetwork();
      const quote = await json("/api/orb/credits/quotes", { method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ credits: Number(count.value) }) });
      if (quote.chain_id !== CHAIN_ID) throw new Error("Server quote has the wrong chain.");
      setFeedback("Confirm the Arbitrum Sepolia testnet transfer in your wallet…");
      const txHash = await window.ethereum.request({ method: "eth_sendTransaction", params: [{
        from: address, to: quote.to, value: `0x${BigInt(quote.value_wei).toString(16)}`, data: quote.data,
      }] });
      if (!/^0x[0-9a-fA-F]{64}$/.test(txHash)) throw new Error("Wallet did not return a valid transaction hash.");
      sessionStorage.setItem(PENDING_KEY, JSON.stringify({ quoteId: quote.quote_id, txHash, wallet: address }));
      setFeedback("Transaction sent. Waiting for independent server verification…");
      void verifyPending();
    } catch (error) { setFeedback(error.message || "Testnet payment was cancelled."); }
    finally { busy = false; update(); }
  }

  function open() { panel.classList.remove("hidden"); el("wallet-close").focus(); }
  function close(restoreFocus = false) {
    panel.classList.add("hidden");
    if (restoreFocus) el("menu-toggle").focus();
  }

  el("wallet-close").addEventListener("click", () => close(true));
  connectButton.addEventListener("click", () => void connect());
  switchButton.addEventListener("click", async () => {
    try { await switchNetwork(); setFeedback("Arbitrum Sepolia selected. Connect and sign to continue."); }
    catch (error) { setFeedback(error.message || "Network switch cancelled."); }
  });
  buyButton.addEventListener("click", () => void buy());
  retryButton.addEventListener("click", () => void verifyPending());
  count.addEventListener("change", () => {
    if (config) el("credit-price").textContent = `${formatTestnetEth(BigInt(config.price_wei) * BigInt(count.value))} testnet ETH for ${count.value} credit${count.value === "1" ? "" : "s"} (plus gas). Quote expires in 15 minutes.`;
  });
  window.ethereum?.on?.("accountsChanged", () => clearSession("Wallet account changed. Sign again."));
  window.ethereum?.on?.("chainChanged", () => {
    clearSession("Wallet network changed. Switch to Arbitrum Sepolia and sign again.");
    void network().catch(() => {});
  });
  void (async () => {
    try {
      config = await json("/api/orb/credits/config");
      if (!config.enabled) setFeedback("Testnet payments are not configured on this server.");
      else setFeedback("Connect a wallet to see your testnet credits.");
      count.dispatchEvent(new Event("change"));
      if (window.ethereum?.request) await network();
    } catch { setFeedback("Could not load testnet payment configuration."); }
    update();
  })();
  update();
  return { open, close, refresh, headers, hasCredit: () => !!token && balance > 0,
    isAuthenticated: () => !!token, walletAddress: () => address,
    isEnabled: () => !!config?.enabled };
}
