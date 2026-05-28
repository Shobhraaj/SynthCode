# SynthCode

SynthCode is a Manifest V3 browser extension and local FastAPI MVP for surfacing AI-generated code confidence signals on GitHub repository pages.

This implements the planning document's Phase 1 workflow:

- GitHub repository detection through a content script
- Badge injection next to the repository title
- Sidebar score card with file-level signals and disclaimer
- Popup UI with scan controls and API endpoint settings
- `chrome.storage.local` result caching
- FastAPI endpoints matching the planned API contract
- Deterministic heuristic scoring for local development

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
+-- main.py
+-- requirements.txt
+-- synthcode_planning.md
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

to `POST /api/v1/analyze` on the configured API endpoint.

The local MVP backend currently uses deterministic heuristic scoring, not a trained AI detector. It creates a repeatable sample of likely source files, assigns file-level confidence scores, combines those signals into an overall score, and returns a label:

- `human`: score below 30%
- `mixed`: score from 30% to 50%
- `AI-coded`: score above 50%

The extension renders that confidence as a badge beside the GitHub repository name, a sidebar score card, and a per-file mini badge on file pages. If the backend is not running, the extension falls back to a deterministic mock score so the UI can still be tested.

Planned production scanning will replace the local heuristic with the pipeline described in `synthcode_planning.md`: fetch a filtered sample of repository files from the GitHub API, exclude generated or vendored paths, run static heuristics plus a fine-tuned code classifier, then combine those scores into the final confidence value.

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
node --test tests/extension-smoke.test.js
node --check extension/background.js
node --check extension/content.js
node --check extension/popup.js
python -m py_compile main.py
```

## Current Limits

The MVP uses deterministic heuristic scoring instead of a trained CodeBERT or StarCoder classifier. PostgreSQL, Redis, Celery, real GitHub API sampling, authentication, and rate limiting are scaffold targets for the next phase.
