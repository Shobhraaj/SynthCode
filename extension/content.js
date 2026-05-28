const BADGE_ID = "synthcode-repo-badge";
const CARD_ID = "synthcode-score-card";
const FILE_BADGE_ID = "synthcode-file-badge";
const ROUTE_DEBOUNCE_MS = 250;

let currentRoute = "";
let routeTimer = null;

init();

function init() {
  observeGitHubNavigation();
  renderForCurrentRoute();
}

function observeGitHubNavigation() {
  const observer = new MutationObserver(() => {
    window.clearTimeout(routeTimer);
    routeTimer = window.setTimeout(renderForCurrentRoute, ROUTE_DEBOUNCE_MS);
  });

  observer.observe(document.documentElement, {
    childList: true,
    subtree: true
  });
}

async function renderForCurrentRoute() {
  const routeKey = `${location.pathname}${location.search}`;
  const repo = parseGitHubRepo(location.pathname);
  if (!repo) {
    removeSynthCodeUi();
    return;
  }

  if (currentRoute !== routeKey) {
    currentRoute = routeKey;
    removeSynthCodeUi();
  }

  ensureLoadingBadge(repo);
  ensureLoadingCard(repo);
  ensureFileBadge(repo);

  const cached = await sendMessage({ type: "SYNTHCODE_GET_CACHED", repo });
  if (cached?.result) {
    renderResult(repo, cached.result);
    return;
  }

  const analysis = await sendMessage({ type: "SYNTHCODE_ANALYZE_REPO", repo });
  if (analysis?.result) {
    renderResult(repo, analysis.result);
  } else {
    renderError(repo, analysis?.error || "Unable to analyze repository");
  }
}

function ensureLoadingBadge(repo) {
  if (document.getElementById(BADGE_ID)) {
    return;
  }

  const title = findRepoTitle();
  if (!title) {
    return;
  }

  const badge = document.createElement("button");
  badge.id = BADGE_ID;
  badge.className = "synthcode-badge synthcode-badge--loading";
  badge.type = "button";
  badge.textContent = "SynthCode analyzing";
  badge.setAttribute("aria-label", `Analyze ${repo.owner}/${repo.repo} with SynthCode`);
  badge.addEventListener("click", () => rescan(repo));
  title.appendChild(badge);
}

function ensureLoadingCard(repo) {
  if (document.getElementById(CARD_ID)) {
    return;
  }

  const sidebar = findSidebar();
  if (!sidebar) {
    return;
  }

  const card = document.createElement("section");
  card.id = CARD_ID;
  card.className = "synthcode-card synthcode-card--loading";
  card.setAttribute("aria-label", `SynthCode score for ${repo.owner}/${repo.repo}`);
  card.innerHTML = `
    <div class="synthcode-card__header">
      <div>
        <div class="synthcode-kicker">SynthCode</div>
        <h2>Analyzing repository</h2>
      </div>
      <div class="synthcode-ring" aria-hidden="true"></div>
    </div>
    <p class="synthcode-muted">Checking cached results and preparing a confidence score.</p>
    ${disclaimerMarkup()}
  `;
  sidebar.prepend(card);
}

function ensureFileBadge(repo) {
  const filePath = parseGitHubFilePath(location.pathname);
  if (!filePath || document.getElementById(FILE_BADGE_ID)) {
    return;
  }

  const fileHeader = document.querySelector(".Box-header, [data-testid='breadcrumbs']") || findRepoTitle();
  if (!fileHeader) {
    return;
  }

  const badge = document.createElement("span");
  badge.id = FILE_BADGE_ID;
  badge.className = "synthcode-file-badge synthcode-file-badge--loading";
  badge.textContent = "SynthCode";
  badge.title = `${repo.owner}/${repo.repo}/${filePath}`;
  fileHeader.appendChild(badge);
}

function renderResult(repo, result) {
  const score = Number(result.overall_score || 0);
  const percent = Math.round(score * 100);
  const tone = toneForScore(score);
  const label = result.label || labelForScore(score);

  const badge = document.getElementById(BADGE_ID);
  if (badge) {
    badge.className = `synthcode-badge synthcode-badge--${tone}`;
    badge.textContent = `${percent}% ${label}`;
    badge.title = "Click to rescan with SynthCode";
  }

  const card = document.getElementById(CARD_ID);
  if (card) {
    card.className = `synthcode-card synthcode-card--${tone}`;
    card.innerHTML = scoreCardMarkup(repo, result, percent, label);
    const rescanButton = card.querySelector("[data-synthcode-rescan]");
    rescanButton?.addEventListener("click", () => rescan(repo));
  }

  renderFileResult(result);
}

function renderFileResult(result) {
  const fileBadge = document.getElementById(FILE_BADGE_ID);
  if (!fileBadge) {
    return;
  }

  const filePath = parseGitHubFilePath(location.pathname);
  const fileScore = (result.file_scores || []).find((file) => file.path === filePath);
  const score = Number(fileScore?.score ?? result.overall_score ?? 0);
  const percent = Math.round(score * 100);
  fileBadge.className = `synthcode-file-badge synthcode-file-badge--${toneForScore(score)}`;
  fileBadge.textContent = `${percent}% SynthCode`;
}

function renderError(repo, message) {
  const badge = document.getElementById(BADGE_ID);
  if (badge) {
    badge.className = "synthcode-badge synthcode-badge--error";
    badge.textContent = "SynthCode unavailable";
  }

  const card = document.getElementById(CARD_ID);
  if (card) {
    card.className = "synthcode-card synthcode-card--error";
    card.innerHTML = `
      <div class="synthcode-card__header">
        <div>
          <div class="synthcode-kicker">SynthCode</div>
          <h2>Analysis unavailable</h2>
        </div>
      </div>
      <p class="synthcode-muted">${escapeHtml(message)}</p>
      <button class="synthcode-action" type="button" data-synthcode-rescan>Try again</button>
      ${disclaimerMarkup()}
    `;
    card.querySelector("[data-synthcode-rescan]")?.addEventListener("click", () => rescan(repo));
  }
}

async function rescan(repo) {
  ensureLoadingBadge(repo);
  ensureLoadingCard(repo);
  const analysis = await sendMessage({ type: "SYNTHCODE_ANALYZE_REPO", repo, forceRescan: true });
  if (analysis?.result) {
    renderResult(repo, analysis.result);
  } else {
    renderError(repo, analysis?.error || "Unable to analyze repository");
  }
}

function scoreCardMarkup(repo, result, percent, label) {
  const scannedAt = result.scanned_at ? new Date(result.scanned_at).toLocaleString() : "Just now";
  const files = (result.file_scores || []).slice(0, 5);
  const sourceText = result.source === "mock-fallback" ? "Mock score" : "Analysis";

  return `
    <div class="synthcode-card__header">
      <div>
        <div class="synthcode-kicker">SynthCode</div>
        <h2>${percent}% ${escapeHtml(label)}</h2>
      </div>
      <div class="synthcode-score">${percent}</div>
    </div>
    <dl class="synthcode-meta">
      <div><dt>Repository</dt><dd>${escapeHtml(repo.owner)}/${escapeHtml(repo.repo)}</dd></div>
      <div><dt>Files</dt><dd>${Number(result.files_analyzed || files.length)}</dd></div>
      <div><dt>Source</dt><dd>${escapeHtml(sourceText)}</dd></div>
      <div><dt>Scanned</dt><dd>${escapeHtml(scannedAt)}</dd></div>
    </dl>
    ${files.length ? fileListMarkup(files) : ""}
    <button class="synthcode-action" type="button" data-synthcode-rescan>Rescan</button>
    ${disclaimerMarkup()}
  `;
}

function fileListMarkup(files) {
  const rows = files.map((file) => {
    const score = Number(file.score || 0);
    const percent = Math.round(score * 100);
    return `
      <li>
        <span title="${escapeHtml(file.path)}">${escapeHtml(file.path)}</span>
        <strong class="synthcode-file-score synthcode-file-score--${toneForScore(score)}">${percent}%</strong>
      </li>
    `;
  }).join("");

  return `
    <details class="synthcode-files" open>
      <summary>File signals</summary>
      <ul>${rows}</ul>
    </details>
  `;
}

function disclaimerMarkup() {
  return `
    <div class="synthcode-disclaimer">
      <strong>Important Notice</strong>
      <span>SynthCode can and will make mistakes. Treat results as one signal, never as definitive proof.</span>
    </div>
  `;
}

function parseGitHubRepo(pathname) {
  const parts = pathname.split("/").filter(Boolean);
  if (parts.length < 2) {
    return null;
  }

  const [owner, repo] = parts;
  const ignoredOwners = new Set(["features", "enterprise", "marketplace", "explore", "topics", "collections", "sponsors", "settings", "notifications", "pulls", "issues"]);
  if (ignoredOwners.has(owner)) {
    return null;
  }

  return { owner, repo, branch: "main" };
}

function parseGitHubFilePath(pathname) {
  const parts = pathname.split("/").filter(Boolean);
  const blobIndex = parts.indexOf("blob");
  if (parts.length < 5 || blobIndex === -1) {
    return "";
  }
  return parts.slice(blobIndex + 2).join("/");
}

function findRepoTitle() {
  return document.querySelector("strong[itemprop='name']")?.parentElement ||
    document.querySelector("[data-testid='repository-title']") ||
    document.querySelector("h1");
}

function findSidebar() {
  return document.querySelector("div.Layout-sidebar") ||
    document.querySelector("aside") ||
    document.querySelector("[data-testid='repository-sidebar']");
}

function removeSynthCodeUi() {
  document.getElementById(BADGE_ID)?.remove();
  document.getElementById(CARD_ID)?.remove();
  document.getElementById(FILE_BADGE_ID)?.remove();
}

function toneForScore(score) {
  if (score > 0.5) {
    return "high";
  }
  if (score >= 0.3) {
    return "medium";
  }
  return "low";
}

function labelForScore(score) {
  if (score > 0.5) {
    return "AI-coded";
  }
  if (score >= 0.3) {
    return "mixed";
  }
  return "human";
}

function sendMessage(message) {
  return chrome.runtime.sendMessage(message).catch((error) => ({ ok: false, error: error.message }));
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
