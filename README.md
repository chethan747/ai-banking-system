# AI Banking System

> **DEMO / EDUCATIONAL ONLY — not a real bank.** All data is fictitious demo
> data. There is no real money, no real people, no real account numbers, no
> real payments, and no bank partnership. AI scores in this project are
> transparent, illustrative models — **not** regulated credit decisions and
> **not** production fraud detection. This system is **not** PCI-DSS or SOC 2
> compliant and must not be used with real financial data.

A complete AI full-stack banking demo in **pure Python (standard library
only — no external dependencies)**:

- **Frontend web app** — a polished dashboard with views for Dashboard,
  Accounts, Transactions, Transfers, Fraud Review, Loans, and Management.
- **Backend API** — a REST-style JSON API (stdlib `http.server`) with
  bearer-token login and role-based access.
- **Database** — SQLite persistence (`data/bank.db`, `data/management.db`).
- **AI layer, built from scratch** — fraud detection, transparent credit
  scoring, spending categorisation and insights, and a banking assistant
  answering from a built-in FAQ knowledge base with cited sources.
- **Management & compliance** — role-based access (customer, teller,
  manager, admin), KYC records, a loan approval workflow, a hash-chained
  (tamper-evident) audit log, and management reports.
- **CLI demo** — a full end-to-end scenario with no server needed.
- **Live browser demo** — a self-contained static frontend in `docs/`
  (no server, no build step) that runs the core demo in the browser.

**Read the full design first: [ARCHITECTURE.md](ARCHITECTURE.md)** — system
diagram, component map, end-to-end flows, database schema, how the AI
pieces work, security design, and how the live Pages demo relates to the
full Python stack.

## Two ways to use it — do not confuse them

| | Live browser demo (GitHub Pages) | Full Python stack (this repo) |
|---|---|---|
| URL / location | https://chethan747.github.io/ai-banking-system/ | https://github.com/chethan747/ai-banking-system |
| What it is | Static frontend in `docs/` (`index.html` + `app.js` + `style.css`). Runs entirely in your browser, state in `localStorage`. No server. | The complete system: `web/` dashboard + `api/` server + `banking/` + `ai_engine/` + `management/` + SQLite. Run it locally (see below). |
| Best for | Trying the demo instantly, with no install. | Running the real API, roles, audit log, and CLI demo. |

The Pages demo is a **separate, simplified in-browser re-implementation**
of the core demo (accounts, transfers, fraud flags, credit score,
management view). It does **not** talk to the Python server, and its role
switcher is a demo UI gate only — not access control. The Python stack
enforces roles on the server.

## Run it on your computer — step by step

### 1. Check Python is installed

You need **Python 3.10 or newer**. No other software, no installs, no
setup steps.

- Windows: open Command Prompt or PowerShell and run `py --version`
- macOS / Linux: open Terminal and run `python3 --version`

You should see something like `Python 3.12.x`. If you see "not recognized"
or "command not found", install Python from https://www.python.org/downloads/
and, on Windows, tick **"Add python.exe to PATH"** during install, then
close and reopen your terminal and check again.

### 2. Download and unzip

- Download the ZIP from this repo: `ai-banking-system.zip` (in the repo
  root), or clone the repo.
- Unzip it anywhere, e.g. your Desktop or Documents folder.
- Open a terminal **inside the unzipped `ai-banking-system` folder** — that
  folder must contain `run.py`, `demo.py`, `banking/`, `api/`, `web/`,
  `docs/`, and `tests/`.

> On Windows, in File Explorer you can click the folder's address bar,
> type `cmd`, and press Enter to open a terminal already in that folder.

### 3. Start the server / dashboard (one command)

| | Windows | macOS / Linux |
|---|---|---|
| Server / dashboard | `py run.py` | `python3 run.py` |
| Server on another port | `py run.py --port 8080` | `python3 run.py --port 8080` |
| Server, fresh demo data | `py run.py --reset` | `python3 run.py --reset` |

The first run seeds fictitious demo data (only if the databases are
empty) and prints the dashboard URL and the demo logins. Open this URL
in your browser:

```
http://127.0.0.1:8000/
```

(If you used `--port 8080`, open `http://127.0.0.1:8080/` instead.)

### 4. Log in with a demo user

| Username | Password | Role | What you can do |
|---|---|---|---|
| `admin` | `admin123` | admin | Everything, including users and reports |
| `manager` | `manager123` | manager | Fraud review, loan approve/reject, reports, KYC |
| `teller` | `teller123` | teller | Customers, accounts, transactions |
| `customer` | `customer123` | customer | Own accounts, transactions, and loans only |

These are demo credentials for fictitious demo users only. Change them
before any real use — better: do not use this system for anything real.

### 5. Try the CLI demo (no server needed)

| | Windows | macOS / Linux |
|---|---|---|
| CLI demo | `py demo.py` | `python3 demo.py` |

It opens accounts, deposits, withdraws, transfers, flags a fraud
transaction, scores credit, applies for and approves a loan, prints a
monthly statement, and verifies the audit chain — using a temporary
database that is deleted afterwards.

### 6. Run the tests

| | Windows | macOS / Linux |
|---|---|---|
| Tests | `py -m unittest discover -s tests` | `python3 -m unittest discover -s tests` |

67 tests, all passing at release (18 banking + 18 management + 22 AI +
9 API). The API tests start a real server on an ephemeral port.

### 7. Stop the server

Press `Ctrl+C` in the terminal where the server is running. That is all —
there is nothing else to shut down. Restarting reuses the existing demo
databases (it does not reseed); use `--reset` for a fresh demo.

## Troubleshooting

- **"Python was not found" / `py` or `python3` not recognized** — Python
  is not installed or not on your PATH. Reinstall from python.org
  (Windows: tick "Add python.exe to PATH"), reopen the terminal, and
  run `py --version` / `python3 --version` again.
- **"Address already in use" / port already in use** — something else is
  using port 8000. Either stop that program, or run on another port:
  `py run.py --port 8080` (Windows) / `python3 run.py --port 8080`
  (macOS/Linux) and open `http://127.0.0.1:8080/`.
- **Unzip issues** — if the download looks like a single `.zip` file that
  will not open, re-download it (do not rename it to anything else).
  Make sure you open a terminal *inside* the unzipped folder, not inside
  the `.zip` itself — `run.py` must be in your current folder.
- **"No module named banking"** — you are in the wrong folder. `cd` into
  the folder that contains `run.py` and try again.
- **Login fails** — use the exact demo credentials above (usernames are
  lowercase). If you started the server before, the demo users already
  exist; if you want a clean slate, stop the server and restart with
  `--reset`.
- **Dashboard loads but charts are empty** — make sure you logged in and
  that demo data was seeded (the first run prints "Seeded demo data").
  Restart with `--reset` if the databases were created empty.
- **I just want to try it without installing anything** — open the live
  browser demo instead: https://chethan747.github.io/ai-banking-system/
  (no Python, no server, demo data lives in your browser).

## Dashboard views (both dashboards)

Both the Python-server dashboard (`web/`) and the live Pages demo
(`docs/`) share the same view layout. See [ARCHITECTURE.md](ARCHITECTURE.md)
for the full description; in short:

- **Dashboard** — summary cards (total balance, account count, recent
  transactions, flagged transactions, loans in pipeline) plus three
  charts, all drawn with plain canvas/SVG from real demo data (no chart
  libraries, no hardcoded pictures): spending by category, balance over
  time, and fraud-flag trends.
- **Accounts** — account cards and balances, per-account detail and
  history, deposit/withdrawal/transfer forms.
- **Transactions** — chronological history table, filterable by account.
- **Transfers** — internal transfer form (validated: positive amounts,
  sufficient funds, no self-transfer).
- **Fraud Review** — flagged transactions table with score and reasons
  (manager/admin only in the Python dashboard; role-gated UI in the
  Pages demo).
- **Loans** — loan pipeline table with apply (customer) and
  approve/reject (manager/admin, once only — no re-review).
- **Management** — totals, flagged-transaction report, loan pipeline
  report, KYC records, and the audit log with chain verification
  (Python dashboard; the Pages demo shows management totals and the
  loan pipeline).

Role views: **customer** sees only their own accounts, transactions, and
loans; **manager/admin** additionally see the fraud queue, loan
approve/reject controls, management totals, KYC, and audit. In the
Python stack these gates are enforced on the server (403 otherwise);
in the Pages demo they are a UI gate only.

## Module map

```
ai-banking-system/
├── run.py                  # Server/dashboard entry point (single command)
├── demo.py                 # CLI demo (no server)
├── banking/                # Core banking: accounts, transfers, interest, statements
│   └── core.py             #   Bank class, SQLite, money as integer cents
├── ai_engine/              # AI, from scratch (stdlib math only)
│   ├── fraud.py            #   Fraud scoring + review queue
│   ├── credit.py           #   Transparent credit scoring
│   ├── insights.py         #   Categorisation + spending insights
│   └── assistant.py        #   FAQ banking assistant with cited sources
├── management/             # Management & compliance
│   ├── auth.py             #   Roles + PBKDF2 password hashing
│   ├── kyc.py              #   KYC records (ID stored as hash only)
│   ├── loans.py            #   Loan application + manager approval workflow
│   ├── audit.py            #   Hash-chained audit log
│   └── reports.py          #   Totals / flagged / loan-pipeline reports
├── api/                    # Backend API + seed data
│   ├── server.py           #   http.server API + serves web/
│   └── seed.py             #   Fictitious demo seed data
├── web/                    # Python-server dashboard (index.html, app.js, style.css)
├── docs/                   # Live browser demo for GitHub Pages (same 3 files, standalone)
├── tests/                  # unittest suites: banking, AI, management, API
├── data/                   # Created on first run (bank.db, management.db) — not shipped
├── ARCHITECTURE.md         # Full architecture and how-it-works documentation
└── ai-banking-system.zip   # ZIP of this project, for download
```

## API endpoints (Python server, JSON, Bearer token except login)

`POST /api/login` · `GET/POST /api/accounts` ·
`POST /api/accounts/<id>/deposit` · `POST /api/accounts/<id>/withdraw` ·
`POST /api/transfers` · `GET /api/accounts/<id>/transactions` ·
`GET /api/accounts/<id>/statement` · `POST /api/fraud/score` ·
`GET /api/fraud/review` · `POST /api/credit/score` · `GET /api/insights` ·
`POST /api/assistant/ask` · `GET/POST /api/kyc` · `GET/POST /api/loans` ·
`POST /api/loans/<id>/review` (manager/admin) · `GET /api/audit` ·
`GET /api/reports` (manager/admin). Errors: 400 invalid input, 401
missing/invalid token, 403 role violation, 404 not found.

## Limitations — read before using

- **Demonstration / educational only.** Not a production bank, not
  PCI-DSS/SOC 2 compliant, no HTTPS, no rate limiting, tokens live only
  in server memory (a restart invalidates logins), single-threaded
  demo server.
- **AI scores are illustrative.** Fraud rules and credit tiers are
  transparent demo heuristics, not tuned on real data, not regulated
  credit decisions, and no accuracy figures are claimed.
- **Audit chaining detects tampering; it does not prevent it.** Anyone
  with write access to the SQLite file could rewrite the whole chain.
  Production use would need append-only storage, signing, and
  independent retention.
- **KYC here is record-keeping only**, not real identity verification;
  loan review is a role check plus an optional illustrative credit
  score, not a real lending decision.
- **Interest is not auto-accrued on server start** (the core module has
  no idempotency guard, so accruing on every start would double-credit).
- **Pages demo limits:** it runs entirely in the browser (localStorage),
  does not talk to the Python server, and its role switcher is a UI
  gate only. Charts were verified at the data-function level, not by
  screenshot; do a quick visual pass on the Pages URL after publishing.
- **Seed timing:** first `run.py` and the API test suite take ~13–19
  seconds because seed transactions are spaced 1.1 s apart (bank
  timestamps have second precision and the fraud velocity rule needs a
  >0 gap between transactions for the seeded flagged transaction to
  score deterministically).
