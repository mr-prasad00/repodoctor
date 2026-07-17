# AGENTS.md

This project is "RepoDoctor". Read PROJECT.md for full context before any task.
 
## Rules

- Backend: Python + FastAPI. Frontend: Next.js + React + Tailwind.

- Sandbox runs a single generated pytest file inside Docker with the security

  controls in PROJECT.md §4.1 (no network, non-root, read-only FS, 10s timeout).

- Verdict statuses are EXACTLY: reproduced | not_reproducible | insufficient_info.
 
- Build MVP scope only. Do NOT build auto-fix. Batch/PDF upload is stretch — only

  after the single-bug loop works.

- After each change, ensure `pip install -r backend/requirements.txt` works and any

  tests pass. Keep changes small and reviewable.
 