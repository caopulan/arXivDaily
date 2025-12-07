# ResearchTok (frontend-only)

A stripped-down branch that keeps only the user-facing UI: browsing paper cards, managing favorites, and remembering simple filters/history. All ingestion, arXiv fetching, and LLM enrichment code has been removed so the project is safe to open source.

## What's included
- Flask pages (`index`, `paper_detail`, `favorites`, `settings`) backed by a lightweight SQLite DB for users/favorites/history.
- Minimal dependencies (`Flask`, `python-dotenv`) and optional auth bypass via `NO_AUTH_MODE`.
- No API keys, scrapers, LLM prompts, or thumbnail generators are present in this branch.

## Quickstart
1) Install deps: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
2) Create an `.env` (or export env vars) – start from `.env.example`. For a demo run you can keep `NO_AUTH_MODE=true`.
3) Initialize the DB: `flask --app app init-db`
4) Run the server: `flask --app app run --debug`

To display papers, place JSON files named `YYYY-MM-DD.json` under your `PAPERS_DATA_DIR` (matching the schema used by the app). Without data, the feed will render an empty state.

## Privacy & cleanup checklist
- Do not commit `.env`, local SQLite files, or any personal data directories. They are ignored in `.gitignore`.
- This branch ships no bundled data; add your own JSON under `PAPERS_DATA_DIR` when needed.
- If you previously used real data under `arXivDaily-data/`, keep it local or delete it before pushing.
