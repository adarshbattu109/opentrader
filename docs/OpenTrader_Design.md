# OpenTrader — Architecture & Design Specification (v4)

**Status:** Revision 4 — reframed as a phased handoff. Part A defines the POC to build first. Part B is the full target architecture (v1→v3) from prior revisions, unchanged in substance but now explicitly labeled as "build incrementally, after the POC validates the idea" rather than a v1 starting point.

**Handoff note:** If you take only one thing from this document: **start at Part A, and do not start writing the Part B components until the POC's exit criteria (§5) are met.** Nearly everything in Part B exists to solve a problem that only appears once a specific condition is true (multiple strategies sharing a broker account, real capital at risk, unattended multi-day operation, real orders reaching an exchange). None of those conditions are true for a POC, and building for them now is solving problems you don't have yet at the cost of the one you do have: proving the core idea works.

---

# PART A — Proof of Concept (Build This First)

## 1. Revision Log

### v4 (this revision)
The prior revision (v3) is architecturally sound but is the correct **target** architecture, not a starting point — it assumes multiprocessing, shared broker connections, a Position Ledger, regulatory compliance, and unattended operation from day one, none of which a POC needs. This revision doesn't change any Part B design decision; it adds Part A (POC definition, phased component map, POC build order, exit criteria) and tags every Part B section with the phase it belongs to, so nothing gets built before it's needed. This mirrors a course-correction this project has made once already — the original v2/v3 target architecture was explicitly reframed as "the target, not the starting point" earlier in this project's design history, and this revision is that same discipline applied again, more concretely.

### v3 and earlier (unchanged, see Part B)
Broker Live Feed Adapter replacing the Screener as canonical price source; `auth_mode` on the Connection Manager; tightened Position Ledger conflict rule; restored Credential Store / OMS state machine / circuit breaker detail; verified free broker API options (Dhan, Upstox, Fyers, Angel One) with concrete package names; new SEBI compliance requirements (static IP, mandatory order tagging, OAuth-only auth) folded in; Implementation Hints and a technology/library map added throughout. Full detail in Part B.

---

## 2. POC Definition & Scope

**Goal:** prove that "strategy defined as JSON → signal generated → mock trade logged" actually works, end to end, against real market data — both historically (backtest) and live (paper). Nothing else.

### 2.1 What's IN scope
- **One** strategy, **one** symbol, **one** broker's data feed.
- Backtest first, against `tvdatafeed` historical replay — this validates the indicator/condition logic against known data before anything touches a live feed, which is the highest-value, lowest-risk thing to prove first.
- Then the *same* evaluation code, pointed at one broker's live (or paper-trading) quote endpoint — polled REST is fine, no WebSocket needed yet.
- A mock ledger that is genuinely just a Python dict (open positions) and a list or CSV (closed trades).
- Stop-loss and a risk-reward-derived target, computed once at entry — this is cheap to include now and is the one piece of Part B's risk logic worth not deferring, since it's simple and directly testable.

### 2.2 What's explicitly OUT of scope (deferred to Part B)
No multiprocessing (one script, one strategy, run it and watch it). No Redis. No Postgres — SQLite or flat CSV is enough. No Connection Manager (call the broker SDK directly in your script). No Position Ledger, no reconciliation (there's nothing to reconcile against yet — no second strategy, no real capital). No SEBI compliance handling (static IP / Algo-ID tagging only matters once a *real*, non-paper order reaches an exchange — see the Phased Component Map, §3). No alerting system beyond `print()`. No Validator/linter (you're hand-writing and eyeballing one strategy file). No exit-lock object, no two-phase write-ahead log — a simple in-order `if`/`elif` and "assume it filled" is fine at this scale.

### 2.3 Trimmed POC strategy shape (deliberately not the full v1.2 schema)

```json
{
  "name": "ema_cross_poc",
  "symbol": "RELIANCE",
  "exchange": "NSE",
  "indicators": [
    {"id": "ema9",  "type": "ema", "period": 9},
    {"id": "ema21", "type": "ema", "period": 21}
  ],
  "entry": {"left": "ema9", "op": "crosses_above", "right": "ema21"},
  "stop_loss_pct": 1.5,
  "risk_reward_ratio": 3.0
}
```

This is intentionally flatter and smaller than Part B's full schema (§8) — no `market`/`index`/`time_in_force`/`credential_alias` fields, no TradingView-compatible operator vocabulary, no linting. Migrating to the full schema is part of the POC→v1 transition (§5), not something to design for now. Don't build a generic DSL engine for this — hardcode the 2–3 indicators and 2–3 comparison operators your one strategy actually needs as plain functions.

---

## 3. Phased Component Map

The single source of truth for "what phase does X belong to." When in doubt about whether to build something now, find it here first.

| Component | POC | v1 | v2 | v3 |
|---|---|---|---|---|
| Strategy schema | Trimmed subset (§2.3), hand-written | Full schema (`time_in_force`, R:R derivation, `market`/`index`) | — | — |
| Rules DSL | Hardcoded small op set as plain functions | — | Full TradingView-compatible operator set + linter + canonical-price rule | — |
| Data source | `tvdatafeed` backtest replay only | + Broker Live Feed Adapter (polled REST is fine) | + Screener Aggregator for supplementary gating; full warm-start stitching | — |
| Order execution | Dict entry, assume instant full fill | Real broker place-order call, naive poll-for-status | Full OMS state machine, two-phase WAL, partial-fill tracking | — |
| Exit protection | Simple `if`/`elif` priority in one function | A basic flag/boolean guard | Full `PositionExitLock` object with release-on-reject | — |
| Risk / circuit breaker | Stop-loss + R:R-derived target only | Simple per-strategy daily-loss check | Full Position Ledger, account-level circuit breaker | — |
| Broker connection | One hardcoded SDK client instance in-script | — | Shared Connection Manager (one connection per broker+account) | — |
| SEBI compliance (static IP, order tagging, OAuth) | N/A — no real orders reach an exchange | **Required the moment the first real, non-paper order is placed** — this is a threshold, not a phase | — | — |
| Credentials | `.env` file / plain config | — | Credential Store (keyring/Fernet) | Vault/KMS |
| Persistence | In-memory dict + CSV export | SQLite | Postgres (+ Redis for hot state) | + retention/archival policy |
| Alerting | `print()` / log line | Email-on-critical (plain `smtplib`) | Full suppression/causal-collapse system | — |
| Reconciliation | None — nothing to reconcile against yet | Startup sanity check only | Full 3-trigger reconciliation loop | — |
| Concurrency | Single process, single strategy | — | Multiprocessing (one process per strategy) | — |
| Validator / dry-run | Manual eyeball of the one strategy file | — | Automated lint + dry-run against replay | — |
| Crash recovery | Restart the script manually | — | Checkpointing + warm-start-on-restart | — |
| Calendar / corporate actions / data retention | — | — | — | Full |

**Reading this table:** a component with content in the POC column is something to actually build now. A dash means don't build it yet, even if Part B describes it in detail — Part B is there for when you get to that column, not before.

---

## 4. POC Build Order & Suggested File Layout

```
1. Write ONE strategy JSON by hand (§2.3's trimmed shape).
2. Write plain functions for the 2–3 indicators and 2–3 comparison ops that one
   strategy needs (ema, rsi, crosses_above, crosses_below, greater, less) —
   hardcoded, not a generic engine.
3. Write a backtest loop: tvdatafeed.get_hist() → iterate bars → run your
   condition functions → append signals/mock trades to a list or CSV.
4. Eyeball the backtest output against a real chart for the same period —
   does it fire where you'd visually expect it to?
5. Swap the data source only: same evaluation loop, now polling the broker's
   live/paper quote endpoint instead of tvdatafeed replay.
6. Watch it run live for a session. Confirm signals fire sensibly; mock trades
   still just append to the same list/CSV.
7. Only once 4 and 6 both look right — move to Part B, §19 (v1 build order).
```

**Suggested minimal file layout** (planning, not a prescription — adjust freely):
```
poc/
  strategies/ema_cross.json     # one hand-written strategy (§2.3 shape)
  indicators.py                  # ema(), rsi() as plain functions over a list/pd.Series
  conditions.py                  # crosses_above(), crosses_below(), gt(), lt()
  backtest.py                    # tvdatafeed pull + replay loop + CSV trade log
  live_paper.py                  # broker feed poll + same eval loop + CSV trade log
  mock_ledger.py                 # a dict of open positions + a list of closed trades
```

No package structure, no abstract base classes, no config framework. If a file grows past a couple hundred lines, that's a signal you're ready for the next phase, not a signal to add abstraction to the POC.

---

## 5. POC Exit Criteria — When to Move to v1

Move to Part B's v1 phase when all of these are true, not before:

- [ ] Backtesting ≥1 month of historical data for the one symbol produces a trade log whose entries/exits match a manual visual read of the same chart.
- [ ] The *same* evaluation code, pointed at the live/paper feed instead of historical replay, correctly fires a mock trade at the right real-time moment — verified by watching it happen against a live chart, not just trusting the log.
- [ ] The stop-loss and R:R-derived target compute correctly and would have closed the mock position at the right price, checked by hand on at least one real trade.
- [ ] You've run at least 2–3 *different* strategy JSON files through the same code without touching the code itself — this is what actually proves the "strategies are data" premise, not just that one file works.
- [ ] You've hit at least one real edge case manually (market closed, feed drops, a symbol with no data) and watched how the script behaves, even if it just crashes — this gives you a real baseline for what v1's error-handling needs to cover, instead of guessing.

Moving to v1 means: swap the mock ledger's order call for a real broker order call, keep everything else from the POC largely intact, and *then* start pulling in Part B's components — starting with §11 (Broker Connection Management) and §14 (a basic OMS), in that order, not the full v2/v3 stack at once.

---

# PART B — Target Architecture (v1 → v3)

**Everything below this line is unchanged in substance from the prior revision.** It's correct design for where this project is going — it is not where to start. Each section header is tagged with the phase it belongs to; use §3's table as the authority if a tag and the table ever seem to disagree.

---

## 6. Deployment Scope & Latency Class `[Phase: context for v1+]`

- **v1+ target: single deployment, single user/account set, self-hosted.** Session Manager, Market Data Aggregator, and Broker Connection Manager are scoped per-session/per-deployment, not multi-tenant. A hosted multi-user SaaS model would require promoting these to system-wide services — a v3+ consideration, not designed here.
- **Latency class: intraday/swing pattern trading (sub-minute to daily bars), not HFT.** Nothing here should be assumed to extend to scalping/HFT without a fundamentally different data layer.

---

## 7. High-Level Components `[Phase: v2 — full picture, do not build all at once]`

```
Store ──▶ Validator ──▶ Session Manager ──spawns──▶ Strategy Process (× N)
                              │                         ├─ Rules Engine (Condition Evaluator)
                              │                         ├─ OMS (state machine, exit-lock,
                              │                         │      partial-fill tracking, write-ahead)
                              │                         └─ Checkpoint writer
                              │
                       Watchdog + Status Service ◀──heartbeats──┘
                              │
                    Alerting (shared function + shared durable table)
                              │
                    Position Ledger (per broker account, shared, broker-truth-reconciled)
                              │
                    Broker Connection Manager  (one authenticated connection per (broker,account))
                       ├─ Order placement / cancel / status (with mandatory strategy tag)
                       ├─ Broker Live Feed Adapter   ◀── CANONICAL price source (v1)
                       │    (e.g. dhanhq / fyers-apiv3 / upstox-python-sdk / smartapi-python)
                       ├─ auth_mode handling (interactive_daily | automated_totp | persistent_token)
                       ├─ Static-IP compliance (SEBI-mandated, at first real order)
                       ├─ Capability flags (supports_bracket_orders, supports_live_feed, ...)
                       └─ Instrument master pull (tick_size / lot_size / price_precision, daily refresh)
                              │
                    Market Data Aggregator   (SUPPLEMENTARY path only — v2)
                       ├─ tradingview_screener   (live, batched — gating/scanning conditions ONLY)
                       └─ tvdatafeed             (cold: warm-start history + backtest pull — POC/v1)
                              │
                    Data Store (ticks, orders, fills, checkpoints, instrument_map, alerts, sessions)
                              │
                    Credential Store (secrets, resolved only by Connection Manager at connect time)
```

**Mapping to the original brief's naming:** the original brief's single "Transformer" role split into the **Broker Connection Manager** (broker connections, order placement, live price feed) and the **Market Data Aggregator** (the two TradingView-library integrations, now scoped to a supplementary role).

---

## 8. Strategy JSON Schema `[Phase: v1 — full shape]`

```json
{
  "strategy_id": "uuid",
  "schema_version": "1.2",
  "name": "ema_crossover_v1",
  "mode": "mock",
  "broker": {
    "name": "dhan",
    "account_id": "DHAN_ACC_001",
    "credential_alias": "dhan_main_001"
  },
  "market": {
    "type": "equity",
    "region": "india"
  },
  "instruments": [
    {
      "symbol": "RELIANCE",
      "exchange": "NSE",
      "index": ["NIFTY50", "NIFTYENERGY"]
    }
  ],
  "time_in_force": {
    "product_type": "intraday",
    "square_off_time": "15:15:00",
    "timezone": "Asia/Kolkata"
  },
  "data_window": {
    "type": "bar_count",
    "size": 50,
    "granularity": "1min",
    "empty_window_timeout_sec": 120
  },
  "rules": {
    "indicators": [
      {"id": "ema9",  "type": "ema", "params": {"period": 9},  "source": "close"},
      {"id": "ema21", "type": "ema", "params": {"period": 21}, "source": "close"}
    ],
    "entry": {
      "operator": "AND",
      "conditions": [
        {"left": "ema9", "operation": "crosses_above", "right": "ema21"}
      ]
    },
    "exit": {
      "operator": "OR",
      "conditions": [
        {"left": "close", "operation": "crosses_below", "right": "ema9", "role": "discretionary_exit"}
      ]
    }
  },
  "risk": {
    "max_capital": 50000,
    "position_size_pct": 10,
    "max_daily_loss": 5000,
    "stop_loss": {"type": "pct", "value": 1.5},
    "risk_reward_ratio": 3.0
  },
  "logging_level": "INFO"
}
```

**Why `"dhan"` here:** illustrative only — the `BrokerAdapter` interface is broker-agnostic. Dhan's API is free; Zerodha's Kite Connect (commonly cited around ₹2,000/month) is not, which matters if picking a broker from scratch.

### Key schema decisions
- `broker.account_id` is mandatory and distinct from `credential_alias`.
- `market.type` / `market.region` map to `tradingview_screener`'s market taxonomy for field-catalog validation (v2, once the Screener is in play).
- `time_in_force.product_type = intraday` **requires** `square_off_time`; `delivery`/`gtc` **must not** set it.
- `risk.stop_loss` is the single source of truth for downside; take-profit is derived at signal time by the OMS.
- **Still genuinely undecided:** whether `instruments[]` with multiple entries implies independent-per-instrument or combined cross-instrument signals (§16, item 5).

**POC note:** don't build toward this full shape yet — §2.3's trimmed version is what to actually write for the POC. Migrating a POC strategy file into this full shape is a v1 task, not something to front-load.

---

## 9. Declarative Rules DSL — TradingView-Screener Compatible `[Phase: v2]`

### 9.1 Operator vocabulary
Imported directly from `tradingview_screener`'s own operation enum, not duplicated: `greater`, `egreater`, `less`, `eless`, `equal`, `nequal`, `in_range`, `not_in_range`, `match`, `crosses`, `crosses_above`, `crosses_below`, `above%`, `below%`, `in_range%`, `not_in_range%`, `has`, `has_none_of` (plus newer: `not_like`, `empty`, `not_empty`, `in_day_range`, `in_week_range`, `in_month_range`).

### 9.2 Derived comparisons
Expressed via a `right` object (e.g. `{"pct_of": "entry_price", "factor": 0.985}`) rather than inventing new operation strings.

### 9.3 Canonical Price Rule
The Data Window and every locally-computed indicator are fed exclusively by the Broker Live Feed Adapter (live) and `tvdatafeed` (historical) — never the Screener. **Validator rule:** every condition inside `entry.conditions[]` must reference at least one local `indicator.id`; a condition composed entirely of raw screener fields cannot by itself arm an order. This is a *should*, not a *must*, for discretionary `exit.conditions`.

### 9.4 Linter requirements
Operation check → field check (against the daily-refreshed TV field catalog) → canonical-price check → shape check → dry-run against replayed data.

### 9.5 Implementation Hints
- **Schema/shape validation:** `pydantic` (v2) for the strategy JSON model; keep DSL-specific checks as separate functions run after the parse, since they need cross-field context.
- **Operator enum sync:** import `tradingview_screener`'s own operation constants rather than hand-copying them; add a CI check that fails if the imported enum drifts from test fixtures.
- **Indicator computation:** plain `pandas` (`.ewm()`, `.rolling()`, hand-rolled RSI) is enough; `pandas_ta`/`ta` are a reasonable development-speed tradeoff if the dependency cost is acceptable.
- **Field catalog cache:** a simple `(field_name, market_type, region, fetched_at)` table, refreshed daily via a scheduled job.

---

## 10. Market Data Sourcing `[Phase: split — see each subsection]`

### 10.1 Roles

| Source | Role | Phase | Frequency |
|---|---|---|---|
| `tvdatafeed` | Historical bars: warm-start + backtest | **POC** | Burst, one-time |
| **Broker Live Feed Adapter** | Canonical execution-grade price | **v1** | Continuous, pushed or polled |
| `tradingview_screener` | Supplementary gating/scanning fields | **v2** | Continuous, polled, batched |

**Why the Screener isn't the primary live source:** `tradingview_screener`'s real-time access is entitlement-gated per exchange/segment/account status and documented to regress to delayed data under common conditions (recurring reports of 15-minute delays affecting NSE; BSE F&O delayed by default without a paid data package). A strategy triggering off data that's actually stale isn't trading on noise — it's trading on the past with full confidence it's current.

### 10.2 Broker Live Feed Adapter — concrete SDK options `[Phase: v1]`

| Broker | Package | Import | Notes |
|---|---|---|---|
| **Dhan** | `pip install dhanhq` | `from dhanhq import dhanhq` | Live feed bundled free; official client exposes IP management directly from Python. Verify recent commit activity before committing — maintenance-status signals were mixed as of this revision. |
| **Upstox** | `pip install upstox-python-sdk` | `import upstox_client` | v2-generation (the old bare `upstox` package is deprecated). Order placement natively supports an algorithm/tag field. |
| **Fyers** | `pip install fyers-apiv3` | `from fyers_apiv3 import fyersModel` | v3-generation (don't use `fyers-api`/`fyers-apiv2`). Separate data-socket and order-socket WebSocket modules. |
| **Angel One** | `pip install smartapi-python` | `from SmartApi import SmartConnect` | Official docs list `pyotp`, `logzero`, `websocket-client` as companion installs — confirms TOTP-based login is the expected pattern. |

If a broker doesn't expose a streaming feed, fall back to high-frequency REST polling of its quote endpoint (`supports_live_feed: false`) — the canonical-price invariant holds either way.

### 10.3 Warm-Start `[Phase: v1]`
```
tvdatafeed.get_hist(...)  →  historical bars up to the last completed bar
        +
Broker Live Feed Adapter's current tick/in-progress bar  →  bridges the gap to "now"
        =
Full valid Data Window from tick 1, no organic wait for indicators to warm up
```
Reruns as step 0 of crash recovery (v2), before checkpoint replay.

### 10.4 Mock Mode — settled by necessity `[Phase: v1]`
Since canonical price must come from the Broker Live Feed Adapter, mock mode necessarily uses the same authenticated live connection as live mode; only the order-placement leg differs.

### 10.5 Market Data Aggregator — batching `[Phase: v2]`
One coalesced `Query().set_tickers(...).select(...)` call per poll interval for the union of every strategy's *supplementary* field needs. Default result size is 50 rows; the library's maintainers caution against raising this aggressively — paginate rather than assume unlimited batch size.

---

## 11. Broker Connection Management `[Phase: v1 basics, v2 for the shared manager]`

### 11.1 Connection model `[v2]`
One authenticated connection per `(broker_name, account_id)`, shared by every strategy process declaring that pair. For v1 (one strategy, one broker), this collapses to a single connection — build the shared-manager abstraction only once a second strategy actually needs it.

### 11.2 `auth_mode` `[v1]`
```
auth_mode: "interactive_daily" | "automated_totp" | "persistent_token"
```
- **`interactive_daily`** — a human completes login/2FA once per trading day.
- **`automated_totp`** — automated via a stored TOTP secret; document as an **accepted operational risk**.
- **`persistent_token`** — for APIs whose tokens don't expire daily.

**Implementation hints:** `pyotp.TOTP(secret).now()` for `automated_totp` (Angel One's own setup docs list `pyotp` as a companion install, confirming this pattern for that integration). For `interactive_daily`, a small local callback endpoint (stdlib `http.server`, or one Flask route) catches the OAuth redirect's token/code parameter.

### 11.3 Capability flags `[v1]`
`supports_bracket_orders`, `supports_live_feed`, `product_types_supported`, `supports_order_tagging`.

### 11.4 Credential Store `[v1 pragmatic, v2 production-grade]`
- **v1:** OS keyring or a Fernet-encrypted file mapping `credential_alias → secret`.
- **v2:** HashiCorp Vault or a cloud KMS, if this ever runs multi-user/hosted.

### 11.5 Serialization `[v2]`
Each shared connection serializes concurrent requests via a per-connection FIFO queue — only matters once more than one strategy process shares a connection.

### 11.6 SEBI Compliance — Static IP `[Phase: required at first real order, regardless of v-number]`
Static IP whitelisting is mandatory for API-based order placement (effective April 1, 2026) — dynamic IPs are rejected. Register a fixed IPv4 (ISP-issued, or a VPS/NAT-gateway address) in the broker's developer console. **Implementation hints:** a persistently-provisioned VPS, or a cloud NAT gateway with a fixed address, or a dedicated static-egress-IP proxy service. Dhan's SDK exposes IP registration directly from Python.

### 11.7 SEBI Compliance — Algo-ID / Order Tagging `[Phase: required at first real order]`
Every algorithmic order must carry a unique, exchange-traceable identifier. **Implementation hint:** Upstox's SDK exposes a plain `tag` field on order placement; confirm the equivalent for other brokers (`correlation_id`, `remark`, etc.). Generate the tag deterministically from `(strategy_id, session_id)`. **Does this solve the shared-position attribution problem (§13.2)?** Not necessarily — order-level tagging for compliance is different from a broker's *position* query supporting tag-filtered breakdowns. Verify per broker; don't assume.

### 11.8 SEBI Compliance — OAuth-Only Auth `[Phase: required at first real order]`
OAuth-based authentication is now the only permitted login mechanism — validates §11.2's `auth_mode` design rather than requiring changes to it.

### 11.9 Instrument master `[v1]`
Tick size / lot size / price precision pulled from the broker's own instrument master endpoint, refreshed daily. Explicitly rejected: deliberately-invalid orders as a discovery mechanism.

---

## 12. Position Ledger & Reconciliation `[Phase: v2]`

Not needed until a second strategy shares a broker account — nothing to reserve or reconcile against with just one.

### 12.1 Two-tier model
**Tier 1** — local, atomic, TTL-bound reservation gate. **Tier 2** — broker's own books, ultimate truth.

### 12.2 Reservation gate — conflict rule
**Rule: reject any second position in the same instrument+account, regardless of direction**, while one is already open — brokers net same-direction positions across strategies into one aggregate position, breaking per-strategy P&L attribution otherwise.

**Noted, not built:** a future alternative using broker order-tagging (§11.7) for per-strategy sub-position tracking, contingent on broker-specific position-query support that needs direct verification.

**Implementation hints:** a Redis Lua script via `EVAL` for atomic check-and-write, or `WATCH`/`MULTI`/`EXEC` with a retry loop as a plain-Python alternative.

### 12.3 Mock Broker fidelity requirement
The Mock Broker must simulate the same shared/netted position behavior, or this conflict scenario only surfaces in live, multi-strategy production.

### 12.4 Reconciliation
Startup (rebuild from broker truth) → crash recovery (step 0) → periodic drift-check (30–60s, broker always wins, drift beyond tolerance raises `CRITICAL`). **Implementation hint:** `APScheduler`'s interval trigger, or a bare `while True: sleep(30)` loop — no need for more.

### 12.5 Account-level circuit breaker
Per-strategy and account-level daily-loss ceilings tracked by the Ledger; either breached → hard stop, block new submissions until manually cleared.

---

## 13. Partial Fills `[Phase: v2]`

Not needed for a POC/v1 that assumes instant full fills at small size. Weighted-average entry via `Decimal`, bracket arms progressively per filled quantity, exit-lock cancels remaining unfilled entry qty on mid-fill exit triggers, residual fill/cancel race risk caught by reconciliation rather than fully prevented.

---

## 14. Order Management System `[Phase: v1 basics, v2 for the full machine]`

### 14.1 Order state machine `[v2]`
```
CREATED → SUBMITTED → ACKNOWLEDGED → [PARTIALLY_FILLED]* → FILLED
                    → REJECTED
                    → CANCEL_REQUESTED → CANCELLED
                    → (timeout) → UNKNOWN → RECONCILING → resolved
```
For v1, a much simpler status check (submitted → filled/rejected, polled) is enough — build the full machine once partial fills and crash-mid-order actually need handling.

### 14.2 Exit-Lock `[v1 simple version, v2 full object]`
For v1: even a single boolean flag ("has this position's exit already been triggered") prevents the double-exit race at small scale. **Implementation hint:** a plain `threading.Lock()` per open position is sufficient once formalized — no distributed lock needed, since one OMS owns its own positions.

### 14.3 Two-phase write-ahead `[v2]`
INTENT (durable, before broker call) → SUBMIT (persist result) → RECONCILE (on restart, query broker by idempotency key). **Implementation hint:** a Postgres `SEQUENCE` or Redis `INCR` for the idempotency key, combined with `session_id`.

### 14.4 Alerting `[v1 simple, v2 full suppression]`
For v1: `print()` plus an email-on-critical via plain `smtplib` is enough. The full suppression/causal-collapse/rate-ceiling system (§17) only matters once enough concurrent processes exist that a human can't just watch one terminal.

---

## 15. Explicitly Unconfirmed Assumptions — Needs Sign-off

- ~~Does `mode: "mock"` source data identically to `mode: "live"`?~~ **Settled** — §10.4, by structural necessity.
- **Should the Risk Layer enforce a minimum `risk_reward_ratio` floor platform-wide, or is this purely per-strategy/informational?** Still open — decide before the Validator's dry-run pass exists (v2).
- **Does your chosen broker's position API support tag-filtered queries?** Affects whether §11.7's mandatory tagging can ever help §12.2's attribution problem, or remains compliance-only. Verify per broker during v1/v2 implementation.

---

## 16. Remaining Open Points — Operational-Completeness Tier `[Phase: v3]`

1. Trading-calendar awareness.
2. Corporate actions — adjustment logic on top of the instrument-master pull.
3. Session Manager supervisor (external supervisor + persisted session state).
4. Bounded logging queue with explicit drop policy.
5. Multi-instrument strategy semantics — still genuinely undecided.
6. Backtest cost model (commissions, slippage, STT/stamp duty).
7. Hot-edit-while-running rule — needs enforcement, not just documentation.
8. Plugin sandbox honesty — trusted/reviewed-only, not a real security boundary.
9. Data retention/archival policy.

---

## 17. Infrastructure Recommendations Pending Confirmation `[Phase: v2]`

| Decision | Recommendation | Rationale |
|---|---|---|
| **IPC transport** | Redis (pub/sub + key-value), replacing raw `multiprocessing.Queue` | Covers pub/sub, Ledger atomicity, and alert suppression state in one piece of infrastructure. |
| **Data Store engine** | Postgres (or Timescale if volume warrants), replacing SQLite | SQLite's single-writer model becomes a bottleneck once many processes write concurrently. |
| **Static egress IP solution** | A persistently-provisioned VPS, or a cloud NAT gateway with a fixed address | Hard SEBI compliance requirement (§11.6) once real orders are live. |

None of these are POC/v1 concerns — SQLite/CSV and a single hardcoded connection are correct at that scale.

---

## 18. Cross-Cutting Rules `[Phase: mostly v1+, Decimal boundary from POC onward]`

- **Decimal boundary `[POC onward]`:** float/pandas for tick ingestion and indicator computation; `Decimal` from the moment a signal becomes an order intent onward. Worth adopting even in the POC once real prices are involved, since retrofitting later touches everything — one centralized `to_money()` helper (`Decimal(str(value))`, never `Decimal(value)` directly).
- **Broker JSON responses `[v1]`:** `json.loads(text, parse_float=Decimal)` at the boundary into money math.
- **Durable + synchronous `[v2]`:** order/fill state transitions, checkpoints, alerts. **Best-effort + async:** tick persistence, non-CRITICAL logs.
- **Broker truth always wins `[v2]`** over local cached state at reconciliation time — meaningless without a second source of local state to reconcile against.
- **Simplicity bias `[all phases]`:** reuse existing shared infrastructure before adding new services/classes/queues. This is the rule the whole Part A / Part B split is itself an application of.
- **Canonical price sourcing `[v1]`:** the Data Window and every locally-computed indicator are always broker-feed- or `tvdatafeed`-derived; the Screener never feeds price directly into anything that can trigger an order.
- **Mandatory order tagging `[required at first real order]`:** every order carries a tag traceable to `(strategy_id, session_id)` — a SEBI/exchange compliance requirement, independent of whether it's also used for internal attribution.

---

## 19. Suggested Post-POC Build Order (v1 → v2 → v3)

**Do not start here — start at Part A.** This is what comes after §5's exit criteria are met.

```
v1:
  1. Swap the POC's mock ledger order call for a real broker order call (§11.2, §11.9).
  2. Migrate the POC strategy file to the full schema (§8).
  3. Add basic OMS status polling + a simple exit-lock flag (§14.1, §14.2 — v1 versions).
  4. Add SEBI compliance: static IP (§11.6), order tagging (§11.7), confirm OAuth (§11.8) —
     required now, since real orders are reaching an exchange for the first time.
  5. Move persistence from CSV to SQLite.

v2 (once a second strategy or broker account enters the picture):
  6. Data Store schema upgraded to Postgres; Alerting function + shared table built early,
     since the next two steps depend on it.
  7. Full DSL + linter (§9), Broker Connection Manager + Position Ledger + reconciliation (§11, §12).
  8. Full OMS: state machine, exit-lock object, write-ahead persistence, partial-fill tracking (§13, §14).
  9. Market Data Aggregator + full warm-start stitching (§10.5).
  10. Session Manager + Watchdog + Validator; multiprocessing.

v3:
  11. Operational tier (§16), in the order listed, as time permits.
```

---

## 20. Suggested Technology & Library Map

| Need | Suggested library | Phase |
|---|---|---|
| Historical/backtest data | `tvdatafeed` | POC |
| Indicator math | `pandas` (`.ewm()`, `.rolling()`) | POC |
| Broker: Dhan / Upstox / Fyers / Angel One | `dhanhq` / `upstox-python-sdk` / `fyers-apiv3` / `smartapi-python` | v1 |
| TOTP generation | `pyotp` | v1 (if `automated_totp`) |
| OAuth redirect capture | stdlib `http.server`, or `Flask` | v1 (if `interactive_daily`) |
| Money math | stdlib `decimal.Decimal` | POC onward |
| Schema validation | `pydantic` (v2) | v2 |
| IPC / hot state | `redis-py` | v2 |
| Durable store | `psycopg2`/`psycopg3` or `asyncpg` | v2 |
| Scheduling | `APScheduler` | v2 |
| Logging | stdlib `logging.handlers.QueueHandler`/`QueueListener` | v2 |
| Alert notifications | stdlib `smtplib` + `email.message.EmailMessage` | v1 (simple), v2 (full system) |
| Secrets | `keyring`, or `cryptography`'s Fernet | v1 |

---

*End of v4 handoff document. Part A is the actual next step. Part B is where this goes once Part A earns it — nothing in Part B should be started before §5's exit criteria are met, and even then, pull it in one phase at a time per §19, not all at once.*
