# Exact trusted browser origins (backend test branch)

Branch: `staging-origin-allowlist-test`, based on main
`2399c9f896f2f9264b8f0e2e42de8a733e07768b`.
No deployment, merge, database migration or service configuration change has
been performed as part of this work.

## Configuration

Keep the staging service's existing `ORB_PUBLIC_ORIGIN` unchanged. After a
separately approved deployment of this backend branch, add only:

```env
ORB_ADDITIONAL_PUBLIC_ORIGINS=https://orb-fchisqse8-samuelid22.vercel.app
```

The intended service is `https://orb-api-usdg-test.onrender.com`. Do not apply
this setting to `https://orb-api-7qwv.onrender.com` or change production Vercel.
The Preview must continue pointing to staging. The current staging primary
origin is not inferred from the service URL; retain its actual existing value.

The optional variable may contain several comma-separated **exact** origins.
Unset, empty or whitespace-only means no additions. The primary remains required
for paid access and must never contain a list. Surrounding configuration whitespace
is trimmed; an empty list entry, including a trailing comma, fails startup.
At most eight distinct canonical origins are accepted, including primary.

## Validation and matching

- An origin is `scheme://host[:port]`, optionally ending in one `/`.
- Reject paths, queries (even an empty `?`), fragments, credentials, wildcards,
  regexes, malformed hosts/ports, control characters and ambiguous numeric IPs.
- Use ASCII DNS names or explicit punycode. DNS/scheme case, default ports and
  the optional root slash are canonicalized; IPv6 uses bracketed canonical form.
- HTTP is allowed only for `localhost`, `127.0.0.1` and `::1` in local mode.
  Every configured public origin must be non-local HTTPS.
- Matching is exact canonical equality. No suffix, substring or wildcard matching.
- Invalid configuration fails startup with a value-free diagnostic before
  accessing the production ledger. Unknown/missing request origins fail the
  existing origin-protected wallet and paid-operation checks.

`prometheus/api/orb_origins.py` supplies the authoritative parser/config to CORS,
wallet authorization, challenge creation and challenge verification. CORS keeps
the existing GET/POST/OPTIONS, allowed headers and `allow_credentials=False`.
An unknown origin receives no allow-origin header and preflight is rejected.
Existing local-only legacy development CORS remains CORS-only: it does not grant
wallet trust and is prohibited by the public deployment guard as before.

## Signed challenge binding and compatibility

The challenge's domain and `URI` identify the **requesting** trusted origin.
The existing challenge `message` column stores this signed binding; no new
columns, migrations or origin-independent challenge are introduced.
Verification requires the stored signed origin to equal the current request's
canonical origin before recovering the signature or consuming the nonce.
Thus A-to-B replay is rejected even when both A and B are trusted; the original
A request can still use its unconsumed challenge. Normal consumption, five-minute
challenge expiry, one-hour sessions, wallet/chain binding and replay rules remain.

With additions unset, the primary challenge format and normal single-origin
behavior are retained. Existing canonical-primary challenges and valid bearer
sessions remain usable across restart. Sessions remain wallet-bound bearer
sessions under their existing policy; this change does not introduce a new
session-origin binding or change read-only endpoint authentication.

Payment quotes, ETH and USDG receipt verification, transaction uniqueness,
credit reservations/settlement, pricing and result recovery are unchanged.

## Validation and deployment safety

`tests/test_orb_origins.py` exercises the parser, HTTP CORS, both trusted origins,
untrusted/missing origins, cross-origin replay, old challenge/session compatibility,
invalid startup and both payment methods using disposable SQLite and mocked RPC.
Existing Postgres/payment suites remain regression protection; no live service
or paid provider call is needed. Run:

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q tests/test_orb_origins.py
```

The branch-specific Vercel Git deployment restriction prevents this backend
test branch from automatically deploying a frontend when pushed. It leaves main's
settings and the existing USDG restriction unchanged. Merge and deployment require
separate approval; no Render settings are changed by this work.
