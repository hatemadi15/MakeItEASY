# MakeItEASY

Cheapest Makeup Finder MVP prototype that calls external discovery APIs on demand (no persistence) to surface the lowest visible makeup offers. The repo contains:

- **Backend** under `backend/` with a lightweight API layer, live discovery pipeline, a queryable `/search` endpoint, and per-offer reasoning data.
- **Static frontend** under `frontend/` styled with the baby pink & navy palette described in the spec and an in-card “Why cheapest?” details drawer.
- **Tests** covering the search flow and filtering logic.

## Getting started

1. (Optional) Create a virtual environment with Python 3.11+.
2. Install the project in editable mode with the test extras:

   ```bash
   pip install -e .[test]
   ```

   Runtime dependencies are intentionally lightweight (the code will fall back to Python's standard library HTTP client if `requests` is unavailable) so the stack remains easy to run locally.

3. Provide the discovery credentials (set the variables in your shell or `.env` file):

   ```bash
   export GOOGLE_SEARCH_API_KEY="<Google Programmable Search API key>"
   export GOOGLE_SEARCH_ENGINE_ID="<Programmable Search Engine ID>"
   export GEMINI_API_KEY="<Google Gemini API key>"
   # optional: export GEMINI_MODEL="gemini-2.0-flash"
   ```

   The backend degrades gracefully if any key is missing (it simply returns an empty suggestion/result set), but enabling them unlocks live crawling.

4. Run the API locally:

   ```bash
   python -m backend.app.server
   ```

   The server listens on `http://localhost:8000`.

   The prototype enforces a soft rate limit of 30 requests per minute per client (burst 60). If you exceed the limit the API
   returns `429` with a `Retry-After` hint.

5. Open the static frontend (`frontend/index.html`) with a simple file server and make sure it talks to the backend on `http://localhost:8000`.

  The search bar supports datalist autocomplete for popular makeup brands. Offer cards show price breakdowns, confidence badges, and a modal with supporting evidence explaining why the top result is cheapest.

## Running tests

```bash
pytest
```

## Troubleshooting

- **Google Programmable Search returns HTTP 403/blocked** – The live discovery
  pipeline relies on outbound requests to the Custom Search JSON API. If the
  environment cannot reach `https://customsearch.googleapis.com` (common in
  locked-down CI containers), the backend surfaces empty offer lists and the
  logs show `403 Forbidden` errors from the Google client. Run the service from
  a network with internet access to Google APIs or configure an allow-list/
  proxy that lets the requests reach Google.

## API quick reference

- `GET /healthz` → health check.
- `GET /search?q=<query>&country=<ISO2>&condition=<new|any>` → runs the live discovery pipeline (no caching) and returns sorted offers with native-currency totals, shipping breakdown, condition, and confidence badge.
- `POST /crawl/test` with `{"url": "https://example.com/product"}` → queues a crawl in the real service (stubbed here to return a JSON acknowledgement with `202 Accepted`).
