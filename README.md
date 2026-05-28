# SynthCode

SynthCode is a Manifest V3 browser extension and Phase 2 FastAPI backend for surfacing AI-generated code confidence signals on GitHub repository pages.

This now includes the Phase 2 backend and AI-integration scaffold described in `phase2_backend_ai_plan.md`.

Implemented now:

- GitHub repository detection through the extension content script
- Badge injection beside the repository title
- Sidebar score card with file-level signals and disclaimer
- Popup UI with scan controls and API endpoint settings
- `chrome.storage.local` result caching
- FastAPI API gateway with queued job/status/results endpoints
- GitHub API fetcher using repository tree and contents APIs
- Stratified file sampler for supported source files
- Heuristic signal analyzer with composite scoring
- Ensemble scorer that combines ML-style and heuristic signals
- Optional HTTP client for the separate inference service
- Extension polling support for queued jobs, `result_url`, failed, and timeout states
- Root `main.py` compatibility shim for `uvicorn main:app --reload`

Scaffolded for production:

- Redis cache helper, sliding-window rate limiter, and in-memory fallback
- PostgreSQL SQLAlchemy models and initial Alembic migration
- Celery worker app and analysis task shell
- Separate `inference/` FastAPI service for CodeBERT-style batch prediction
- Inference model loader, predictor, schemas, and heuristic fallback
- Dataset collection, generation, preprocessing, training, and evaluation placeholders
- Dockerfiles, Docker Compose stack, env examples, and GitHub Actions CI

## Project Structure

```text
.
+-- extension/
|   +-- manifest.json
|   +-- background.js
|   +-- content.js
|   +-- content.css
|   +-- popup.html
|   +-- popup.css
|   +-- popup.js
|   +-- icons/icon.svg
+-- tests/extension-smoke.test.js
+-- .github/workflows/ci.yml
+-- backend/
|   +-- Dockerfile
|   +-- pyproject.toml
|   +-- alembic.ini
|   +-- .env.example
|   +-- app/
|   |   +-- api/v1/
|   |   +-- services/
|   |   +-- workers/
|   |   +-- cache/
|   |   +-- db/
|   |   +-- models/
|   +-- tests/test_services/
+-- inference/
|   +-- Dockerfile.gpu
|   +-- pyproject.toml
|   +-- .env.example
|   +-- app/
|   +-- ml/
+-- docker-compose.yml
+-- main.py
+-- requirements.txt
+-- synthcode_planning.md
+-- phase2_backend_ai_plan.md
```

## How Repository Scanning Works

When you open a GitHub repository page, the content script reads the URL to identify the `owner` and `repo`, then asks the background service worker for a score. The service worker first checks `chrome.storage.local`; cached results are reused for 24 hours to avoid repeated scans.

If there is no fresh cache entry, the extension sends:

```json
{
  "owner": "username",
  "repo": "repo-name",
  "branch": "main",
  "force_rescan": false
}
```

to `POST /api/v1/analyze` on the configured API endpoint. The backend returns a `job_id`; the extension polls `GET /api/v1/status/{job_id}` until the result is embedded in the status response or available at `result_url`.

The Phase 2 backend fetches a repository tree from GitHub, filters and samples source files, fetches raw file contents, runs heuristic analysis, optionally calls the separate inference service, then combines those signals into an overall score:

- `human`: score below 30%
- `mixed`: score from 30% to 50%
- `AI-coded`: score above 50%

The extension renders that confidence as a badge beside the GitHub repository name, a sidebar score card, and a per-file mini badge on file pages. If the backend is not running, the extension falls back to a deterministic mock score so the UI can still be tested.

ML inference is disabled by default with `INFERENCE_ENABLED=false`; in that mode, the ensemble uses heuristic scores as the ML stand-in. Set `INFERENCE_ENABLED=true` and run the inference service when trained weights are available under `inference/ml/weights`.

## Phase 2 Backend Features

The backend is now split into focused modules under `backend/app`:

- `api/v1/`: health, analyze, status, and results routes.
- `services/github_fetcher.py`: GitHub repo validation, tree fetching, file content fetching, PAT auth, and rate-limit awareness.
- `services/sampler.py`: supported extension filtering, generated/vendor exclusion, size limits, and stratified sampling.
- `services/heuristic.py`: comment uniformity, naming entropy, boilerplate ratio, structure repetition, comment/code ratio, and import-style signals.
- `services/inference_client.py`: async HTTP client for `/predict/batch` with retry behavior.
- `services/scorer.py`: file-size-weighted ensemble scoring and `human` / `mixed` / `AI-coded` labeling.
- `services/pipeline.py`: end-to-end repository analysis orchestration.
- `cache/redis_client.py`: JSON cache helper and sliding-window rate limiter.
- `models/db.py`: SQLAlchemy tables for repo analyses, file scores, and API usage.
- `db/migrations/versions/0001_initial_schema.py`: initial Alembic schema and indexes.

The local API currently uses in-memory job/result state for fast development. Redis, PostgreSQL, and Celery are present as production-ready integration points.

## Phase 2 Inference Features

The separate inference service under `inference/app` exposes:

- `GET /health`
- `POST /predict/batch`

It includes:

- Config-driven model path, device, batch size, token window, and overlap.
- Model/tokenizer loading through Hugging Face Transformers when weights are available.
- Batch prediction and token-window chunking.
- Heuristic fallback prediction when model dependencies or weights are unavailable.
- Dataset/training/evaluation placeholders under `inference/ml`.

## Note - SynthCode results should always be treated as a signal, not proof.

## Run The Backend

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`.

Useful endpoints:

- `GET /api/v1/health`
- `POST /api/v1/analyze`
- `GET /api/v1/results/{owner}/{repo}`
- `GET /api/v1/status/{job_id}`

The unversioned route aliases are also mounted for development, so `/health`, `/analyze`, `/results/{owner}/{repo}`, and `/status/{job_id}` work too.

For real GitHub analysis, set `GITHUB_TOKEN` in your environment or in `backend/.env.example` when using Docker. Public repositories can work without a token, but the unauthenticated GitHub rate limit is much lower.

The root `main.py` is a compatibility shim to `backend.app.main`, so existing local commands continue to work.

## Run The Phase 2 Stack

```bash
docker compose up --build
```

Services:

- API gateway: `http://localhost:8000`
- Inference service: `http://localhost:8001`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

Docker Compose starts:

- `api`: FastAPI gateway
- `worker`: Celery worker
- `inference`: GPU-oriented inference service image
- `db`: PostgreSQL 16
- `redis`: Redis 7

## Load The Extension

1. Open Chrome or Edge.
2. Go to `chrome://extensions`.
3. Enable Developer mode.
4. Choose **Load unpacked**.
5. Select the `extension` directory.
6. Open a GitHub repository page.

If the local backend is not running, the extension falls back to a deterministic mock score so the UI remains testable.

## Test

```bash
node --test tests/*.test.js
node --check extension/background.js
node --check extension/content.js
node --check extension/popup.js
python -m compileall main.py backend inference
python -m py_compile main.py
python -m unittest discover -s tests -p "test_*.py"
```

Optional backend service tests:

```bash
pip install pytest
python -m pytest backend/tests -q
```

Last verified checks:

- Extension smoke tests pass.
- Extension JavaScript syntax checks pass.
- Python compilation passes for `main.py`, `backend`, and `inference`.
- FastAPI smoke check returns `200` for `/api/v1/health` and a valid response shape for `/api/v1/analyze`.
- `pytest` was not installed in the local environment during the last verification, so backend service tests were added but not executed there.

## Current Limits

The inference service includes a heuristic fallback until trained CodeBERT weights are available. PostgreSQL persistence, Redis-backed job state/cache, and Celery execution are scaffolded, while the local API path currently keeps in-memory job/result state for fast development. Dataset licensing and GitHub Terms of Service still need review before large-scale training data collection.
