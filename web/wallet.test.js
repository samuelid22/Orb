import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { initWallet } from "./wallet.js";

const html = readFileSync(resolve(process.cwd(), "web/index.html"), "utf8");
const firstAddress = `0x${"11".repeat(20)}`;
const secondAddress = `0x${"22".repeat(20)}`;
const sessionKey = "orb-wallet-session";

function response(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

async function flush() {
  for (let index = 0; index < 6; index += 1) await new Promise((resolve) => setTimeout(resolve, 0));
}

function setup({ account = firstAddress, balanceStatus = 200, revokeError = null } = {}) {
  let selectedAccount = account;
  let currentBalanceStatus = balanceStatus;
  let sessionValid = true;
  const handlers = new Map();
  const provider = {
    on: vi.fn((event, listener) => handlers.set(event, listener)),
    request: vi.fn(async ({ method }) => {
      if (method === "eth_accounts") return selectedAccount ? [selectedAccount] : [];
      if (method === "eth_requestAccounts") return selectedAccount ? [selectedAccount] : [];
      if (method === "eth_chainId") return "0x66eee";
      if (method === "personal_sign") return `0x${"cd".repeat(65)}`;
      if (method === "wallet_revokePermissions") {
        if (revokeError) throw revokeError;
        return null;
      }
      throw new Error(`Unexpected wallet method: ${method}`);
    }),
  };
  window.ethereum = provider;
  const fetchMock = vi.fn(async (url, options = {}) => {
    const path = String(url);
    if (path === "/api/orb/credits/config") return response({ enabled: true, price_wei: "1000" });
    if (path === "/api/orb/wallet/challenge") return response({ nonce: "nonce", message: "Sign in to Orb" });
    if (path === "/api/orb/wallet/sign-in") {
      sessionValid = true;
      return response({ wallet: selectedAccount,
        token: "test-session-token", expires_at: Math.floor(Date.now() / 1000) + 3600 });
    }
    if (path === "/api/orb/wallet/logout") {
      if (!sessionValid || options.headers?.Authorization !== "Bearer test-session-token") {
        return response({ detail: "Session expired" }, 401);
      }
      sessionValid = false;
      return response({ status: "signed_out" });
    }
    if (path === "/api/orb/credits/balance" && !sessionValid) return response({ detail: "Session expired" }, 401);
    if (path === "/api/orb/credits/balance") return response(currentBalanceStatus === 200
      ? { wallet: selectedAccount, available: 2 } : { detail: "Session unavailable" }, currentBalanceStatus);
    throw new Error(`Unexpected API request: ${path}`);
  });
  globalThis.fetch = fetchMock;
  return {
    provider, fetchMock,
    changeAccount(next) {
      selectedAccount = next;
      handlers.get("accountsChanged")?.(next ? [next] : []);
    },
    setBalanceStatus(status) { currentBalanceStatus = status; },
  };
}

function renderWallet() {
  document.open();
  document.write(html);
  document.close();
  return initWallet({ onBalance: vi.fn() });
}

describe("Orb wallet authentication UI", () => {
  beforeEach(() => {
    sessionStorage.clear();
    document.open();
    document.write(html);
    document.close();
    HTMLElement.prototype.focus = vi.fn();
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
    delete window.ethereum;
  });

  it("shows Connected immediately after signed authentication", async () => {
    const { provider, fetchMock } = setup();
    const wallet = renderWallet();
    await flush();
    expect(document.getElementById("wallet-connect").textContent).toBe("Sign again");
    document.getElementById("wallet-connect").click();
    await flush();

    const button = document.getElementById("wallet-connect");
    expect(button.textContent).toBe("Connected");
    expect(button.disabled).toBe(true);
    expect(wallet.isAuthenticated()).toBe(true);
    expect(document.getElementById("wallet-address").title).toBe(firstAddress);
    expect(document.getElementById("wallet-balance").textContent).toContain("2 testnet credits");
    expect(provider.request.mock.calls.filter(([request]) => request.method === "personal_sign")).toHaveLength(1);
    expect(fetchMock.mock.calls.filter(([url]) => url === "/api/orb/credits/balance")).toHaveLength(1);
  });

  it("accepts the account event emitted during an initial MetaMask connection", async () => {
    const { changeAccount, provider } = setup({ account: null });
    const ordinaryRequest = provider.request.getMockImplementation();
    provider.request.mockImplementation((request) => {
      if (request.method === "eth_requestAccounts") {
        changeAccount(firstAddress);
        return Promise.resolve([firstAddress]);
      }
      return ordinaryRequest(request);
    });
    const wallet = renderWallet();
    await flush();
    expect(document.getElementById("wallet-connect").textContent).toBe("Connect and sign");
    document.getElementById("wallet-connect").click();
    await flush();
    expect(wallet.isAuthenticated()).toBe(true);
    expect(document.getElementById("wallet-connect").textContent).toBe("Connected");
  });

  it("restores a valid backend session after reload without another signature", async () => {
    const { provider, fetchMock } = setup();
    renderWallet();
    await flush();
    document.getElementById("wallet-connect").click();
    await flush();
    expect(sessionStorage.getItem(sessionKey)).toBeTruthy();

    const restoredWallet = renderWallet();
    await flush();
    expect(restoredWallet.isAuthenticated()).toBe(true);
    expect(document.getElementById("wallet-connect").textContent).toBe("Connected");
    expect(document.getElementById("wallet-balance").textContent).toContain("2 testnet credits");
    expect(provider.request.mock.calls.filter(([request]) => request.method === "personal_sign")).toHaveLength(1);
    expect(fetchMock.mock.calls.filter(([url]) => url === "/api/orb/credits/balance")).toHaveLength(2);
  });

  it("requires signing again for an expired saved session", async () => {
    setup();
    sessionStorage.setItem(sessionKey, JSON.stringify({ token: "old-session", address: firstAddress,
      expiresAt: Math.floor(Date.now() / 1000) - 1 }));
    const wallet = renderWallet();
    await flush();

    expect(wallet.isAuthenticated()).toBe(false);
    expect(document.getElementById("wallet-connect").textContent).toBe("Sign again");
    expect(sessionStorage.getItem(sessionKey)).toBeNull();
  });

  it("clears an expired backend session on reload", async () => {
    const { provider } = setup({ balanceStatus: 401 });
    sessionStorage.setItem(sessionKey, JSON.stringify({ token: "old-session", address: firstAddress,
      expiresAt: Math.floor(Date.now() / 1000) + 3600 }));
    const wallet = renderWallet();
    await flush();

    expect(wallet.isAuthenticated()).toBe(false);
    expect(document.getElementById("wallet-connect").textContent).toBe("Sign again");
    expect(sessionStorage.getItem(sessionKey)).toBeNull();
    expect(provider.request.mock.calls.some(([request]) => request.method === "personal_sign")).toBe(false);
  });

  it("rechecks a temporarily unavailable saved session without another signature", async () => {
    const { provider, setBalanceStatus } = setup({ balanceStatus: 503 });
    sessionStorage.setItem(sessionKey, JSON.stringify({ token: "saved-session", address: firstAddress,
      expiresAt: Math.floor(Date.now() / 1000) + 3600 }));
    const wallet = renderWallet();
    await flush();
    expect(wallet.isAuthenticated()).toBe(false);
    expect(document.getElementById("wallet-connect").textContent).toBe("Retry session");

    setBalanceStatus(200);
    document.getElementById("wallet-connect").click();
    await flush();
    expect(wallet.isAuthenticated()).toBe(true);
    expect(document.getElementById("wallet-connect").textContent).toBe("Connected");
    expect(provider.request.mock.calls.some(([request]) => request.method === "personal_sign")).toBe(false);
  });

  it("invalidates the old account and signs a fresh challenge for the new one", async () => {
    const { changeAccount, fetchMock, provider } = setup();
    const wallet = renderWallet();
    await flush();
    document.getElementById("wallet-connect").click();
    await flush();
    expect(wallet.walletAddress()).toBe(firstAddress);

    changeAccount(secondAddress);
    expect(wallet.isAuthenticated()).toBe(false);
    expect(wallet.walletAddress()).toBeNull();
    expect(document.getElementById("wallet-connect").textContent).toBe("Sign again");
    expect(document.getElementById("wallet-balance").textContent).toContain("0 testnet credits");
    expect(sessionStorage.getItem(sessionKey)).toBeNull();

    document.getElementById("wallet-connect").click();
    await flush();
    expect(wallet.walletAddress()).toBe(secondAddress);
    expect(document.getElementById("wallet-connect").textContent).toBe("Connected");
    expect(provider.request.mock.calls.filter(([request]) => request.method === "personal_sign")).toHaveLength(2);
    const challenges = fetchMock.mock.calls.filter(([url]) => url === "/api/orb/wallet/challenge");
    expect(JSON.parse(challenges[1][1].body).address).toBe(secondAddress);

    changeAccount(null);
    expect(wallet.isAuthenticated()).toBe(false);
    expect(document.getElementById("wallet-connect").textContent).toBe("Connect and sign");
    expect(sessionStorage.getItem(sessionKey)).toBeNull();
  });

  it("ignores a signature completed after the wallet account changes", async () => {
    const { changeAccount, fetchMock, provider } = setup();
    const ordinaryRequest = provider.request.getMockImplementation();
    let finishSignature;
    provider.request.mockImplementation((request) => request.method === "personal_sign"
      ? new Promise((resolve) => { finishSignature = resolve; }) : ordinaryRequest(request));
    const wallet = renderWallet();
    await flush();
    document.getElementById("wallet-connect").click();
    await flush();
    expect(finishSignature).toBeTypeOf("function");

    changeAccount(secondAddress);
    finishSignature(`0x${"cd".repeat(65)}`);
    await flush();
    expect(wallet.isAuthenticated()).toBe(false);
    expect(document.getElementById("wallet-connect").textContent).toBe("Sign again");
    expect(fetchMock.mock.calls.filter(([url]) => url === "/api/orb/wallet/sign-in")).toHaveLength(0);
  });

  it("disconnects Orb, clears saved state, and keeps the wallet disconnected after reload", async () => {
    const { fetchMock, provider } = setup();
    const wallet = renderWallet();
    await flush();
    expect(document.getElementById("wallet-disconnect").classList.contains("hidden")).toBe(true);
    document.getElementById("wallet-connect").click();
    await flush();
    expect(document.getElementById("wallet-disconnect").classList.contains("hidden")).toBe(false);
    sessionStorage.setItem("orb-sepolia-pending-payment", JSON.stringify({ quoteId: "quote" }));
    sessionStorage.setItem("orb-active-paid-job", JSON.stringify({ jobId: "job" }));

    document.getElementById("wallet-disconnect").click();
    expect(wallet.isAuthenticated()).toBe(false);
    expect(wallet.walletAddress()).toBeNull();
    expect(wallet.headers()).toEqual({});
    expect(document.getElementById("wallet-connect").textContent).toBe("Connect and sign");
    expect(document.getElementById("wallet-balance").textContent).toContain("0 testnet credits");
    expect(document.getElementById("wallet-disconnect").classList.contains("hidden")).toBe(true);
    expect(sessionStorage.getItem(sessionKey)).toBeNull();
    expect(sessionStorage.getItem("orb-sepolia-pending-payment")).toBeNull();
    expect(sessionStorage.getItem("orb-active-paid-job")).toBeNull();
    await flush();
    const logoutCall = fetchMock.mock.calls.find(([url]) => url === "/api/orb/wallet/logout");
    expect(logoutCall[1]).toMatchObject({ method: "POST", headers: { Authorization: "Bearer test-session-token" } });
    expect(provider.request.mock.calls.find(([request]) => request.method === "wallet_revokePermissions")[0])
      .toEqual({ method: "wallet_revokePermissions", params: [{ eth_accounts: {} }] });
    expect((await fetchMock("/api/orb/credits/balance", { headers: logoutCall[1].headers })).status).toBe(401);

    const reloaded = renderWallet();
    await flush();
    expect(reloaded.isAuthenticated()).toBe(false);
    expect(document.getElementById("wallet-connect").textContent).toBe("Connect and sign");
  });

  it("completes logout when MetaMask cannot revoke access, then requires a new signature", async () => {
    const { fetchMock, provider } = setup({ revokeError: new Error("method not supported") });
    const wallet = renderWallet();
    await flush();
    document.getElementById("wallet-connect").click();
    await flush();
    document.getElementById("wallet-disconnect").click();
    await flush();
    expect(wallet.isAuthenticated()).toBe(false);
    expect(document.getElementById("wallet-connect").textContent).toBe("Connect and sign");
    expect(document.getElementById("wallet-feedback").textContent).toBe("Wallet disconnected from Orb.");
    expect(provider.request.mock.calls.filter(([request]) => request.method === "eth_sendTransaction")).toHaveLength(0);

    document.getElementById("wallet-connect").click();
    await flush();
    expect(wallet.isAuthenticated()).toBe(true);
    expect(document.getElementById("wallet-connect").textContent).toBe("Connected");
    expect(provider.request.mock.calls.filter(([request]) => request.method === "personal_sign")).toHaveLength(2);
    expect(fetchMock.mock.calls.filter(([url]) => url === "/api/orb/wallet/challenge")).toHaveLength(2);
    expect(fetchMock.mock.calls.filter(([url]) => url === "/api/orb/wallet/sign-in")).toHaveLength(2);
  });
});
