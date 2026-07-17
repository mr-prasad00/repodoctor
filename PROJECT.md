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
│   └── calculator.py
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
  "extracted": { "function": "get_discount", "inputs": [100, 20], "expected": 80, "observed": 120 },
  "generated_test": "from target_repo.calculator import get_discount\n\ndef test_repro():\n    assert get_discount(100, 20) == 80",
  "run_output": "E   assert 120 == 80",
  "explanation": "Reproduced. get_discount(100, 20) returned 120, expected 80.",
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
    { "seq": 1, "status": "reproduced",        "explanation": "get_discount returned 120, expected 80" },
    { "seq": 2, "status": "not_reproducible",  "explanation": "divide(10, 2) correctly returns 5" },
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
pass | fail | error
   ▼  (4) VERDICT ENGINE — deterministic
fail → 🔴 reproduced   pass → 🟢 not_reproducible   error → 🟡 insufficient_info
```

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
USER: module=target_repo.calculator  claim={function, inputs, expected}
→ e.g.  from target_repo.calculator import get_discount
        def test_repro():
            assert get_discount(100, 20) == 80
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
2. **(0:30–1:15) Real bug.** Paste a real bug report → 20 seconds later a **red failing test** appears: "Reproduced ✅, returned 120, expected 80."
3. **(1:15–2:00) False report.** Paste an invalid report → **green** result: "Couldn't reproduce — works correctly."
4. **(2:00–2:40) The payoff.** "It didn't guess — it *ran the code*. Real bug caught, false alarm rejected, automatically."
5. **(2:40–3:00) Vision.** "Ships as a GitHub App that triages every incoming issue before a human touches it."

**The beat that lands:** the red failing test appearing live, proving the bug is real on camera.

---

## 14. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Sandbox setup eats time | Pre-build the Docker image Day 1 morning; keep target repo tiny |
| LLM generates an invalid test | Validate it parses/imports before running; fall back to 🟡 insufficient_info |
| Arbitrary code execution danger | Sandbox only runs against *your* target repo; no network; resource limits |
| Demo flakiness | Pre-script the exact 2 reports used in the video; test them beforehand |
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

## 17. Demo Test Data (pre-scripted, rehearse these)

Build `target_repo/calculator.py` with these exact planted bugs so the demo is reliable:

```python
# target_repo/calculator.py
def get_discount(price, percent):
    return price + (price * percent / 100)   # BUG: should subtract

def divide(a, b):
    return a / b                              # correct — used for the false report
```

**Report A → expect 🔴 reproduced**
> Title: "get_discount returns wrong value"
> Body: "Calling get_discount(100, 20) returns 120 but it should return 80."

**Report B → expect 🟢 not reproducible**
> Title: "divide is broken"
> Body: "divide(10, 2) returns 5 but I expected 4."  *(reporter is simply wrong)*

**Report C → expect 🟡 insufficient_info**
> Title: "it doesn't work"
> Body: "nothing works please fix"

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
- [ ] Build `target_repo/calculator.py` with the 2 planted bugs above.
- [ ] Get the Docker sandbox running `pytest` with the security controls in §4.1.
- [ ] Wire the `POST /analyze` pipeline end to end.
- [ ] Confirm Reports A / B / C give 🔴 / 🟢 / 🟡 respectively.
