# RepoDoctor — Project Kickoff Document

> **One-liner:** An automated maintainer assistant that reproduces a reported bug by
> actually running code in a sandbox, then tells you whether the bug is **real**,
> **not a bug**, or **needs more info** — with a failing test as proof.

**Hackathon:** OpenAI × NamasteDev Codex Hackathon
**Core build tool:** OpenAI Codex (chatgpt.com/codex)
**Team size:** 1–3
**Deliverables:** live URL · public repo + README · ≤3-min demo video · (optional deck)

---

## 1. The Problem

Popular open-source projects get flooded with bug reports. The hard part isn't fixing
bugs — it's figuring out **which reports are even valid**. A large share of issues are:

- **User error** — they used the tool wrong (e.g. "floating point is broken").
- **Environment problems** — works fine, their setup is broken (wrong version, venv, firewall).
- **Already fixed** — real once, but patched in a newer version.
- **Too vague** — "it doesn't work", no steps, nothing to test.
- **Duplicates** — same bug reported many times.
- **Misunderstanding** — a feature mistaken for a bug.

Maintainers burn hours triaging this noise before doing real work. Existing bots only
sort issues by **labels** — they never actually **run the code** to verify the claim.

---

## 2. The Solution

When a bug report arrives, RepoDoctor:

1. **Reads** the issue and extracts a structured reproduction: `function`, `inputs`,
   `expected` output, and `observed` output.
2. **Generates** a `pytest` test that asserts the **expected (correct) behavior** the
   reporter claims should happen (Codex-assisted).
3. **Runs** that test in an isolated sandbox against the current code.
4. **Decides** a verdict from the actual pass/fail result and replies with evidence.

### The core mechanic: reproduction, not opinion

The generated test asserts what the reporter says **should** happen. Running it against
the real code produces a fact:

- **Test fails** → the code's actual output differs from the claimed-correct output →
  the discrepancy is **real and reproducible**.
- **Test passes** → the code already produces the claimed-correct output →
  the discrepancy **cannot be reproduced**.

### Three possible verdicts

| Verdict | Test result | Meaning | Message posted |
|---|---|---|---|
| 🔴 **Reproduced** | Test **fails** | Observed ≠ expected, confirmed live | "Reproduced ✅ — failing test attached as proof. Observed `X`, expected `Y`." |
| 🟢 **Not reproducible** | Test **passes** | Code already behaves as asked | "Couldn't reproduce — code returns the expected value. Likely your version/environment." |
| 🟡 **Insufficient info** | Can't build a valid test | Missing function/inputs/expected | "Need more info: exact version, inputs, and expected vs. actual output." |

### Important nuance — reproduction ≠ "the reporter is right"

A 🔴 verdict proves the code's behavior **differs from what the reporter expected**. It
does *not* prove the reporter's expectation is legitimate (they may misunderstand the
library's intended contract). RepoDoctor therefore frames 🔴 as *"discrepancy reproduced —
maintainer to confirm intended behavior,"* and — when a docstring or spec for the target
function exists — cross-checks the claimed-expected value against it and surfaces any
conflict. This honesty is a strength: RepoDoctor automates the expensive, mechanical
**reproduction** step and hands the maintainer a ready-made test, leaving the
*intent judgment* (which requires human/domain context) explicitly to them.

**Why it's hard to fake:** the verdict comes from *executing real code in a sandbox and
reading the actual pass/fail output* — not from generating a paragraph of text.

---

## 3. Scope (be disciplined)

| Level | What it does | Decision |
|---|---|---|
| **MVP — build this** | Confirm real/false/unclear + attach failing test | ✅ In scope |
| **Stretch** | Suggest a fix / open a draft PR that makes the test pass | ⏩ Only if time |

**MVP boundaries for the hackathon:**
- One target repository (a demo Python library you control).
- **Python only.**
- One trigger path (webhook OR a paste-the-issue web form — form is safer for demo).
- One sandbox runner.
- The three-verdict output with a visible failing/passing test.

---

## 4. Architecture

```
┌─────────────┐     issue text      ┌──────────────────┐
│  Web UI     │ ──────────────────▶ │   Backend API    │
│ (paste bug) │                     │   (FastAPI)      │
└─────────────┘                     └────────┬─────────┘
      ▲                                       │
      │  verdict + test + logs                │ 1. extract repro (LLM)
      │                                       │ 2. generate test  (LLM/Codex)
      │                                       ▼
      │                             ┌──────────────────┐
      │                             │  Sandbox Runner  │
      └──────────────── verdict ◀───│ (Docker: run     │
                                    │  pytest safely)  │
                                    └────────┬─────────┘
                                             │ pass / fail / error
                                             ▼
                                    ┌──────────────────┐
                                    │  Verdict Engine  │
                                    │ fail→🔴 pass→🟢   │
                                    │ no-test→🟡        │
                                    └──────────────────┘
```

**Flow:** UI → API → LLM extracts steps → LLM/Codex writes a `pytest` test → sandbox runs
it against the target repo → verdict engine maps the exit code to 🔴/🟢/🟡 → result +
generated test + run logs returned to the UI (and optionally posted to GitHub).

### 4.1 Sandbox security model (non-negotiable)

RepoDoctor executes **LLM-generated code**, so the sandbox is the single most important
component to get right. The Docker runner MUST enforce:

| Control | Setting | Why |
|---|---|---|
| No network | `--network none` | Prevents exfiltration / calling out |
| Non-root user | `USER nobody` in image | Limits blast radius |
| Read-only FS | `--read-only` + tmpfs for `/tmp` | Test can't tamper with the image |
| CPU/memory caps | `--cpus=1 --memory=256m` | Prevents runaway/OOM |
| Hard timeout | kill container after **10s** | Prevents infinite loops (`while True`) |
| One test only | run a single generated `test_*` file | Predictable, auditable |
| Fresh container | new container per request | No state bleed between reports |

> Even though the MVP only runs tests against *your own* target repo, treat every
> generated test as untrusted. Judges (and real users) will ask about this — having a
> clear answer is a credibility win.

### 4.2 Sequence (happy path)

```
UI        API           Extractor   TestGen     Sandbox     Verdict
 │  POST   │               │           │           │           │
 │ /analyze│               │           │           │           │
 │────────▶│  extract      │           │           │           │
 │         │──────────────▶│           │           │           │
 │         │◀── JSON ──────│           │           │           │
 │         │  generate test│           │           │           │
 │         │──────────────────────────▶│           │           │
 │         │◀── pytest src ────────────│           │           │
 │         │  run in docker            │           │           │
 │         │──────────────────────────────────────▶│           │
 │         │◀── pass/fail/logs ────────────────────│           │
 │         │  decide                               │           │
 │         │──────────────────────────────────────────────────▶│
 │         │◀── verdict ───────────────────────────────────────│
 │◀ JSON ──│  (persist to DB)                                  │
```


---

## 5. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js + React + Tailwind | Fast to build, clean demo UI |
| Backend | Python + FastAPI | Same language as the code we test; simple async API |
| AI | OpenAI API (via Codex-assisted dev) | Extraction + test generation |
| Sandbox | Docker container running `pytest` | Isolation, safety, real execution |
| DB | SQLite (MVP) → Postgres (later) | Zero-setup for a hackathon |
| Hosting | Vercel (frontend) + Render/Railway (backend) | Free tiers, fast deploy |
| Repo/CI | GitHub + GitHub Actions | Required deliverable; optional webhook |

---

## 6. Folder Structure

```
RepoDoctor/
├── PROJECT.md                 # this document
├── README.md                  # public-facing, required deliverable
├── frontend/                  # Next.js app
│   ├── app/
│   │   └── page.tsx           # paste-issue form + document upload + results list
│   └── package.json
├── backend/
│   ├── main.py                # FastAPI entrypoint + routes
│   ├── parser.py              # extract raw text from uploaded .txt/.md/.pdf
│   ├── splitter.py            # LLM: one document -> list of individual bug claims
│   ├── extractor.py           # LLM: issue text -> structured repro steps
│   ├── test_generator.py      # LLM/Codex: repro steps -> pytest test
│   ├── sandbox.py             # run test in Docker, capture result
│   ├── verdict.py             # map result -> 🔴/🟢/🟡
│   ├── models.py              # DB models (Document, Report, Verdict)
│   ├── db.py                  # SQLite connection
│   └── requirements.txt
├── sandbox/
│   └── Dockerfile             # image with the target repo + pytest
├── target_repo/               # the demo library we test against (has planted bugs)
│   └── billing.py
└── .env.example               # OPENAI_API_KEY, etc.
```

---

## 7. Database Schema (SQLite MVP)

```sql
CREATE TABLE documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    filename      TEXT,              -- null for pasted text
    raw_text      TEXT NOT NULL,     -- full uploaded/pasted content
    bug_count     INTEGER DEFAULT 0, -- how many bugs the splitter found
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE reports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id   INTEGER REFERENCES documents(id),  -- which doc it came from
    seq           INTEGER,           -- order within the document (1, 2, 3...)
    issue_title   TEXT NOT NULL,
    issue_body    TEXT NOT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE verdicts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id      INTEGER NOT NULL REFERENCES reports(id),
    status         TEXT NOT NULL,     -- 'reproduced' | 'not_reproducible' | 'insufficient_info'
    extracted_json TEXT,              -- structured repro from the extractor
    generated_test TEXT,              -- the pytest code we produced
    run_output     TEXT,              -- captured stdout/stderr from the sandbox
    explanation    TEXT,              -- human-readable reasoning
    duration_ms    INTEGER,           -- end-to-end latency (nice for the demo)
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_reports_document ON reports(document_id);
CREATE INDEX idx_verdicts_report ON verdicts(report_id);
CREATE INDEX idx_verdicts_status ON verdicts(status);
```

> `status` values match the verdict engine exactly: `reproduced` (🔴),
> `not_reproducible` (🟢), `insufficient_info` (🟡). A single pasted report is just a
> `document` with `bug_count = 1`, so both input paths share the same storage.

---

## 8. API Endpoints

| Method | Path | Purpose | Success |
|---|---|---|---|
| `POST` | `/analyze` | Body: `{ title, body }`. Single pasted report | `200` |
| `POST` | `/analyze-document` | Multipart file upload (.txt/.md/.pdf). Splits into many bugs, tests each in sequence | `200` |
| `GET`  | `/documents/{id}` | Fetch an uploaded document and all its verdicts | `200` / `404` |
| `GET`  | `/reports/{id}` | Fetch a single report and its verdict | `200` / `404` |
| `GET`  | `/health` | Health check for the host | `200` |
| `POST` | `/webhook` *(stretch)* | GitHub issue webhook entrypoint | `202` |

**Status codes for `POST /analyze`:**

| Code | When |
|---|---|
| `200` | Pipeline ran; body carries the verdict (including 🟡 insufficient_info) |
| `422` | Missing/blank `title` or `body` |
| `429` | OpenAI rate limit hit — retry with backoff |
| `500` | Sandbox/Docker unavailable or unexpected error |

**`POST /analyze` response shape:**
```json
{
  "status": "reproduced",
  "extracted": { "function": "add_loyalty_points", "inputs": [2147483647, 1], "expected": 2147483648, "observed": -2147483648 },
  "generated_test": "from target_repo.billing import add_loyalty_points\n\ndef test_repro():\n    assert add_loyalty_points(2147483647, 1) == 2147483648",
  "run_output": "E   assert -2147483648 == 2147483648",
  "explanation": "Reproduced. add_loyalty_points(2147483647, 1) returned -2147483648, expected 2147483648.",
  "duration_ms": 4200
}
```

**Error response shape (`4xx`/`5xx`):**
```json
{ "error": "sandbox_unavailable", "detail": "Docker daemon not reachable" }
```

**`POST /analyze-document` response shape (batch):**
```json
{
  "document_id": 7,
  "bug_count": 3,
  "results": [
    { "seq": 1, "status": "reproduced",        "explanation": "add_loyalty_points overflowed to a negative balance" },
    { "seq": 2, "status": "not_reproducible",  "explanation": "calculate_interest(1000, 5, 2) correctly returns 100" },
    { "seq": 3, "status": "insufficient_info", "explanation": "no function/inputs given" }
  ]
}
```

---

## 9. AI Workflow

### Pipeline

```
issue text
   │
   ▼  (1) EXTRACTOR — LLM, JSON mode
{ function, inputs, expected, observed, version? }
   │
   ├── any required field missing? ──▶ 🟡 insufficient_info (skip the rest)
   ▼  (2) TEST GENERATOR — LLM/Codex
pytest source asserting the EXPECTED value
   │
   ├── does not parse / import fails? ──▶ 🟡 insufficient_info
   ▼  (3) SANDBOX — Docker, run pytest
pass | fail | timeout | error
   ▼  (4) VERDICT ENGINE — deterministic
fail    → 🔴 reproduced
timeout → 🔴 reproduced (non-termination)   # valid test that hangs proves a hang bug
pass    → 🟢 not_reproducible
error   → 🟡 insufficient_info               # test never ran cleanly (import/collection)
```

> **Timeout is a real verdict, not a failure to answer.** Once the test *parsed and
> imported the target function cleanly*, a 10s wall-clock kill means the code did not
> terminate on that input — a reproduced defect (see `find_next_leap_year` in §17).
> Only errors *before* the test runs (import/collection errors) fall back to 🟡.

### Why each step is AI-load-bearing (not a wrapper)

- **Extractor** turns messy prose into a typed contract; its output *decides whether a
  test is even buildable* (gates the 🟡 path).
- **Test generator** must map a natural-language claim onto the target repo's real API
  (correct import path, function name, argument order) — a code-synthesis task, not text.
- **Verdict engine is deterministic on purpose:** the AI reasons and writes code; the
  *sandbox result* makes the final call. That separation is what makes it trustworthy.

### Extractor prompt (sketch)

```
SYSTEM: You extract a reproducible bug claim from an issue. Return ONLY JSON:
{ "function": str|null, "inputs": list|null, "expected": any|null,
  "observed": any|null, "version": str|null, "confidence": 0..1 }
If a field is not clearly stated, set it to null. Never invent values.
USER: <issue title + body>
```

### Test generator prompt (sketch)

```
SYSTEM: Given a target module and a bug claim, write ONE minimal pytest function that
asserts the EXPECTED (correct) result. Import from `target_repo`. Output only Python.
USER: module=target_repo.billing  claim={function, inputs, expected}
→ e.g.  from target_repo.billing import add_loyalty_points
        def test_repro():
            assert add_loyalty_points(2147483647, 1) == 2147483648
```

### Validation before running (guards the 🟡 path)

1. `ast.parse()` the generated test — reject if it doesn't parse.
2. Static check that it imports from `target_repo` and defines exactly one `test_*`.
3. Only then hand it to the sandbox. Any failure → 🟡 with reason.

### 9.1 Batch mode — document upload & multi-bug segregation

Users can't always paste one clean report. RepoDoctor also accepts an **uploaded
document** that may describe **many bugs**, splits them apart, and tests each in turn.
This reuses the core pipeline unchanged — it only adds a **parser** and a **splitter** in
front, then loops.

```
uploaded document (.txt / .md / .pdf)
   │
   ▼  (0) PARSER — extract raw text from the file
raw text (may contain many bugs)
   │
   ▼  (1) SPLITTER — LLM: document → list of separate bug claims
[ bug#1, bug#2, bug#3, ... ]
   │
   ▼  for each bug, in sequence, run the EXISTING pipeline:
        EXTRACTOR → TEST GENERATOR → SANDBOX → VERDICT
   │
   ▼  collect verdicts → results list
[ 🔴 bug#1, 🟢 bug#2, 🟡 bug#3 ]
```

**Parser (`parser.py`):** `.txt`/`.md` read directly; `.pdf` via `pypdf`. Output: one string.

**Splitter prompt (sketch):**
```
SYSTEM: A document may describe multiple bugs. Split it into a JSON array, one object
per distinct bug: [{ "title": str, "body": str }]. If only one bug, return one item.
Do not merge unrelated bugs. Do not invent bugs.
USER: <raw document text>
```

**Sequential processing (`main.py`):** loop one bug at a time — keeps sandbox load safe
and makes the demo readable ("Testing bug 2 of 3…"):
```python
results = []
for i, bug in enumerate(split_bugs, start=1):
    verdict = run_pipeline(bug["title"], bug["body"])   # existing single-bug logic
    results.append({ "seq": i, **verdict })
```

**UI:** two input modes on one page — *Paste text* (existing) and *Upload document*
(file picker for `.txt`/`.md`/`.pdf`). Results render as a list, one card per bug with its
🔴/🟢/🟡 badge, generated test, and run output, plus a "Testing bug X of N" progress bar.

**Scope note:** splitter + `.txt`/`.md` upload → build only once the single-bug loop works.
PDF parsing + progress UI → stretch. A single pasted report is just a document with
`bug_count = 1`, so both paths share the same storage and pipeline.

---

## 10. Setup Steps (Day 0)

```bash
# from the RepoDoctor/ folder
python -m venv .venv && source .venv/bin/activate
pip install fastapi uvicorn openai pytest python-dotenv

# frontend
npx create-next-app@latest frontend
cd frontend && npm install && cd ..

# env
cp .env.example .env      # add OPENAI_API_KEY

# run backend
uvicorn backend.main:app --reload

# run frontend
cd frontend && npm run dev
```

**Docker sandbox (build once):**
```bash
docker build -t repodoctor-sandbox ./sandbox
```

---

## 11. 2-Day Build Timeline

**Day 1 — make the core loop work end to end (no UI polish)**
- AM: Scaffold FastAPI + the `target_repo` demo library with 2 planted bugs.
- AM: Build the Docker sandbox that runs `pytest` and captures pass/fail.
- PM: Wire the extractor (LLM) → test generator (LLM) → sandbox → verdict engine.
- PM: `POST /analyze` returns a correct verdict for a real bug from the terminal.
- **End-of-day goal:** a real bug and a false report both produce correct verdicts via curl.

**Day 2 — UI, deploy, demo**
- AM: Build the paste-issue form + verdict display in Next.js.
- AM: Show the generated test and the red/green run output prominently.
- PM: Deploy frontend (Vercel) + backend (Render/Railway); write README.
- PM: Record the 3-minute demo video; (optional) build the deck.
- **End-of-day goal:** live URL working, video recorded, repo public.

---

## 12. Team Task Split

**Solo:** follow the timeline top to bottom; skip stretch goals; keep UI minimal.

**2 people:**
- **A (backend/AI):** extractor, test generator, sandbox, verdict engine, deploy backend.
- **B (frontend/story):** UI, verdict display, README, demo video, deck.

**3 people:**
- **A (AI pipeline):** extractor + test generator + prompt tuning.
- **B (infra):** Docker sandbox + verdict engine + backend deploy.
- **C (product):** frontend + README + demo video + pitch.

---

## 13. Demo Script (≤3 min)

1. **(0:00–0:30) Problem.** "Maintainers drown in bug reports — most aren't even real bugs."
2. **(0:30–1:15) Real bug.** Paste Report A (loyalty-points overflow) → 20 seconds later a **red failing test** appears: "Reproduced ✅ — returned -2147483648, expected 2147483648." Mention it's the same bug class that broke YouTube's counter.
3. **(1:15–1:50) The safety beat.** Paste Report E (leap-year infinite loop) → the sandbox **kills it at 10s** and reports "Reproduced 🔴 — non-termination." "That's the Azure 2012 leap-day outage — and our timeout just contained it."
4. **(1:50–2:20) False report.** Paste Report G (interest calc) → **green** result: "Couldn't reproduce — works correctly."
5. **(2:20–2:40) The payoff.** "It didn't guess — it *ran the code*. Real bug caught, infinite loop contained, false alarm rejected, automatically."
6. **(2:40–3:00) Vision.** "Ships as a GitHub App that triages every incoming issue before a human touches it."

**The beat that lands:** the red failing test appearing live, then the infinite-loop demo timing out safely on camera.

---

## 14. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Sandbox setup eats time | Pre-build the Docker image Day 1 morning; keep target repo tiny |
| LLM generates an invalid test | Validate it parses/imports before running; fall back to 🟡 insufficient_info |
| Arbitrary code execution danger | Sandbox only runs against *your* target repo; no network; resource limits |
| Demo flakiness | Pre-script the exact reports in §17 (A, E, G, H) and test them beforehand |
| Scope creep (auto-fix) | Auto-fix is stretch only — do NOT start it until MVP is deployed |

---

## 15. Honest Limitations & Edge Cases

Being explicit about these makes the project more credible with judges, not less.

| Limitation | Why it exists | How we handle it |
|---|---|---|
| Can't judge if the reporter's *expectation* is legitimate | Requires domain/API-contract knowledge | 🔴 is framed as "discrepancy reproduced — maintainer confirms intent"; cross-check docstring when present |
| Only reproduces deterministic, function-level claims | Flaky/time/network bugs aren't repeatable in a clean sandbox | Out of MVP scope; state it plainly |
| Depends on the reporter naming a function + inputs | Vague reports can't become tests | Routed to 🟡 with a request for specifics |
| LLM may pick the wrong function/overload | Ambiguous natural language | Validation step + show the generated test so a human can verify |
| Single target repo in MVP | Time constraint | Architecture is repo-agnostic; multi-repo is roadmap |

**Edge cases the code must handle gracefully:**
- Empty/blank issue body → `422`.
- Test that imports a nonexistent function → caught in validation → 🟡.
- Test that hangs (`while True`) → 10s sandbox timeout → 🟡 with "timed out".
- Non-deterministic test (uses `random`/`time`) → flag as low-confidence.

---

## 16. Judging Alignment

How each build decision maps to the six equally-weighted lenses:

| Lens | What earns the score |
|---|---|
| **Originality** | Verifying bugs by *executing* generated tests, not label-sorting |
| **Impact** | Removes the real, universal maintainer triage bottleneck |
| **AI fluency** | LLM synthesizes runnable code mapped to a real API; deletion breaks the product |
| **Prototype quality** | Live URL where a judge pastes their own report and sees a real run |
| **Demo clarity** | Real bug 🔴 vs. false report 🟢 shown back-to-back in <3 min |
| **Creativity** | The red-failing-test-appears-live moment as the emotional beat |

**The one-sentence pitch:** *"RepoDoctor doesn't guess whether a bug is real — it writes
a test, runs your code, and proves it."*

---

## 17. Demo Test Data — production-grade bugs from real incidents

The target repo is a small **payments / billing library** (`target_repo/billing.py`).
Every planted bug is a *deterministic, function-level* defect (so the sandbox can
reproduce it with a single `assert`) **and** is modeled on a documented real-world
outage or exploit. This makes the demo tell one coherent story — "a billing service
that shipped six famous classes of bug" — instead of one toy example.

> **Why these and not, say, a flaky-network bug?** RepoDoctor can only prove bugs it can
> re-run deterministically (§15). Each bug below reduces to `f(known_inputs) == expected`
> (or a hang, or a raise), which is exactly what the sandbox verifies. Race conditions,
> timing, and UI bugs are intentionally excluded.

### The target repo

```python
# target_repo/billing.py
"""A minimal billing library — every function here shipped a real-world class of bug."""

INT32_MAX = 2_147_483_647


def add_loyalty_points(current, earned):
    """Accumulate a customer's loyalty points."""
    total = current + earned
    # BUG: simulates a signed 32-bit counter that wraps to negative on overflow.
    # Real incident: YouTube "Gangnam Style" broke the signed-int32 view counter (2014).
    if total > INT32_MAX:
        total = -(total - INT32_MAX) + INT32_MAX * 0  # wraps negative instead of growing
    return total


def split_payment(total_cents, ways):
    """Split a bill of `total_cents` evenly across `ways` people."""
    # BUG: integer-truncates each share, so leftover cents silently vanish.
    # Real incident: Vancouver Stock Exchange index (1982) truncated instead of rounding
    # and drifted from 1000.000 to ~524.811 over 22 months.
    share = total_cents // ways
    return [share] * ways


def apply_coupon(price, coupon_pct):
    """Apply a percentage-off coupon to a price."""
    # BUG: the discount line was duplicated in a refactor, so the coupon applies TWICE.
    # Real incident: recurring class of checkout/coupon-stacking overcharge bugs.
    discounted = price - price * coupon_pct / 100
    discounted = discounted - price * coupon_pct / 100
    return discounted


def is_within_rate_limit(request_count, limit):
    """Return True while a client is still allowed to make requests."""
    # BUG: off-by-one — uses <= so it lets ONE request over the limit through.
    # Real incident: the classic `>` vs `>=` API rate-limit / quota bypass.
    return request_count <= limit


def find_next_leap_year(year):
    """Return the first leap year strictly after `year`."""
    # BUG: increments by 4, so a non-multiple-of-4 start NEVER becomes divisible by 4
    #      → infinite loop. Real incident: Microsoft Azure's Feb 29, 2012 leap-day
    #      outage; the Zune 30 hung on Dec 31, 2008 for the same family of reason.
    candidate = year + 1
    while not (candidate % 4 == 0 and (candidate % 100 != 0 or candidate % 400 == 0)):
        candidate += 4
    return candidate


def cart_total(unit_price, quantity):
    """Compute the charge for `quantity` items at `unit_price`."""
    # BUG: no validation — a negative quantity yields a NEGATIVE charge (store pays you).
    # Real incident: negative-quantity cart exploits on multiple e-commerce platforms.
    return unit_price * quantity


def calculate_interest(principal, rate_pct, years):
    """Simple interest = principal * rate * years. (This one is CORRECT.)"""
    return principal * (rate_pct / 100) * years
```

### Bug → incident → verdict map

| Function | Real incident it mirrors | Bug class | Demo report | Expected |
|---|---|---|---|---|
| `add_loyalty_points` | YouTube "Gangnam Style" counter, 2014 | 32-bit integer overflow | A | 🔴 reproduced |
| `split_payment` | Vancouver Stock Exchange index, 1982 | truncation / lost cents | B | 🔴 reproduced |
| `apply_coupon` | checkout coupon-stacking overcharge | double-applied discount | C | 🔴 reproduced |
| `is_within_rate_limit` | `>` vs `>=` quota bypass | off-by-one | D | 🔴 reproduced |
| `find_next_leap_year` | Azure Feb 29 2012 / Zune 2008 | infinite loop (non-termination) | E | 🔴 reproduced (timeout) |
| `cart_total` | negative-quantity cart exploit | missing input validation | F | 🔴 reproduced |
| `calculate_interest` | — (correct code) | none | G | 🟢 not reproducible |
| — | — | unanswerable | H | 🟡 insufficient_info |

### The pre-scripted reports

**Report A → 🔴 reproduced (integer overflow)**
> Title: "Loyalty points go negative for high-spend customers"
> Body: "add_loyalty_points(2147483647, 1) returns a negative number. It should return 2147483648. Our top customers' balances flipped negative overnight."

**Report B → 🔴 reproduced (lost cents)**
> Title: "Splitting a bill loses money"
> Body: "split_payment(100, 3) returns [33, 33, 33], which only adds up to 99. One cent disappears every time. Expected the shares to sum back to 100."

**Report C → 🔴 reproduced (double discount)**
> Title: "20% coupon takes 40% off"
> Body: "apply_coupon(100, 20) returns 60 but a 20% coupon should leave 80. We lost margin on every promo order."

**Report D → 🔴 reproduced (off-by-one rate limit)**
> Title: "Rate limiter allows one request too many"
> Body: "is_within_rate_limit(100, 100) returns True, so a client at the limit still gets through. At exactly the limit it should return False."

**Report E → 🔴 reproduced (infinite loop — the 'wow' beat)**
> Title: "find_next_leap_year hangs the worker"
> Body: "find_next_leap_year(2001) never returns and pins a CPU. It should return 2004."
> *(The generated test never finishes; the sandbox kills it at 10s and RepoDoctor
> reports "reproduced — non-termination". This is where the 10s timeout in §4.1
> visibly saves the service — a great live moment for judges.)*

**Report F → 🔴 reproduced (negative-quantity exploit)**
> Title: "Negative quantity produces a negative charge"
> Body: "cart_total(50, -2) returns -100 — the store would refund an attacker. It should reject a negative quantity with a ValueError."

**Report G → 🟢 not reproducible (reporter is simply wrong)**
> Title: "Interest calculation is broken"
> Body: "calculate_interest(1000, 5, 2) returns 100 but I expected 105."
> *(The code is correct; 1000 × 5% × 2 = 100. The test passes, proving no discrepancy.)*

**Report H → 🟡 insufficient_info**
> Title: "it doesn't work"
> Body: "billing is wrong please fix everything"
> *(No function, inputs, or expected value → no test can be built.)*

> **Demo tip:** you don't need all eight live. A tight run is **A (overflow) → E (the
> infinite-loop timeout) → G (false report) → H (vague)** — it shows a severe real bug,
> the safety timeout firing, an honest 🟢, and graceful 🟡 in under three minutes.

---

## 18. Post-Hackathon Roadmap

1. Multi-language support (JS, Go).
2. Auto-suggest a fix / draft PR (Level 2).
3. Real GitHub App with issue webhooks.
4. Duplicate detection across the issue tracker.
5. Confidence scoring + human-in-the-loop review dashboard.

---

## 19. Next Actions

- [ ] Create the public GitHub repo and push this document + a README.
- [ ] Build `target_repo/billing.py` with the six planted incident-based bugs above.
- [ ] Get the Docker sandbox running `pytest` with the security controls in §4.1.
- [ ] Make sure the 10s timeout kills `find_next_leap_year(2001)` and reports 🔴 (non-termination).
- [ ] Wire the `POST /analyze` pipeline end to end.
- [ ] Confirm Reports A–H give the verdicts in the §17 map.
