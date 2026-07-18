# repodoctor

Initial repository setup for RepoDoctor.

## Offline tests

Run the complete local test suite without an OpenAI API key, network access, or
Docker. OpenAI and Docker are mocked by the tests.

```bash
python3 -m pip install -r backend/requirements.txt
python3 -m pytest -q tests/test_offline.py
```

## Demo reports

To run with Gemini, add your key locally, build the sandbox image from the
repository root, then start the API:

```bash
cp .env.example .env
# Edit .env and set GEMINI_API_KEY to your key.
# Keep AI_PROVIDER=gemini.

docker build -f sandbox/Dockerfile -t repodoctor-sandbox .
python3 -m uvicorn backend.main:app --reload
```

In a second terminal, start the web UI:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`, paste a report, and RepoDoctor will display the
Gemini extraction, generated pytest test, sandbox output, and verdict.

### Report A — reproduced

```bash
curl -sS -X POST http://127.0.0.1:8000/analyze \
  -H 'Content-Type: application/json' \
  -d '{"title":"get_discount returns wrong value","body":"Calling get_discount(100, 20) returns 120 but it should return 80."}'
```

The response has `"status": "reproduced"`.

### Report B — reproduced under the current §9 rule

```bash
curl -sS -X POST http://127.0.0.1:8000/analyze \
  -H 'Content-Type: application/json' \
  -d '{"title":"divide is broken","body":"divide(10, 2) returns 5 but I expected 4."}'
```

This response has `"status": "reproduced"`: the reporter's stated expected value
is `4`, while `divide(10, 2)` returns `5`, so the generated expected-behavior test
fails. This conflicts with the expected Report B status in `PROJECT.md` §17.

To exercise `"status": "not_reproducible"`, use a claim whose expected value matches
the current code, for example `divide(10, 2) should return 5`.

### Report C — insufficient information

```bash
curl -sS -X POST http://127.0.0.1:8000/analyze \
  -H 'Content-Type: application/json' \
  -d '{"title":"it doesn't work","body":"nothing works please fix"}'
```

The response has `"status": "insufficient_info"`.
