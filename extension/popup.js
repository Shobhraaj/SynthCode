const scanButton = document.getElementById("scanButton");
const saveSettingsButton = document.getElementById("saveSettings");
const statusPill = document.getElementById("statusPill");
const repoName = document.getElementById("repoName");
const scoreBlock = document.getElementById("scoreBlock");
const scoreValue = document.getElementById("scoreValue");
const scoreLabel = document.getElementById("scoreLabel");
const scoreMeta = document.getElementById("scoreMeta");
const apiBaseUrl = document.getElementById("apiBaseUrl");

let activeRepo = null;

document.addEventListener("DOMContentLoaded", init);
scanButton.addEventListener("click", () => scanActiveRepo(true));
saveSettingsButton.addEventListener("click", saveSettings);

async function init() {
  const config = await sendMessage({ type: "SYNTHCODE_GET_CONFIG" });
  apiBaseUrl.value = config?.config?.apiBaseUrl || "http://localhost:8000";

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  activeRepo = parseGitHubRepo(tab?.url || "");

  if (!activeRepo) {
    scanButton.disabled = true;
    setStatus("Open GitHub", "warn");
    return;
  }

  repoName.textContent = `${activeRepo.owner}/${activeRepo.repo}`;
  const cached = await sendMessage({ type: "SYNTHCODE_GET_CACHED", repo: activeRepo });
  if (cached?.result) {
    renderScore(cached.result);
    setStatus("Cached", "good");
  } else {
    setStatus("Ready", "");
  }
}

async function scanActiveRepo(forceRescan) {
  if (!activeRepo) {
    return;
  }

  scanButton.disabled = true;
  setStatus("Scanning", "warn");
  try {
    const response = await sendMessage({
      type: "SYNTHCODE_ANALYZE_REPO",
      repo: activeRepo,
      forceRescan
    });

    if (!response?.result) {
      throw new Error(response?.error || "No result returned");
    }

    renderScore(response.result);
    setStatus(response.result.source === "mock-fallback" ? "Mock" : "Scanned", response.result.overall_score > 0.5 ? "bad" : "good");
  } catch (error) {
    setStatus("Failed", "bad");
    scoreBlock.hidden = false;
    scoreValue.textContent = "--";
    scoreLabel.textContent = "Analysis unavailable";
    scoreMeta.textContent = error.message;
  } finally {
    scanButton.disabled = false;
  }
}

async function saveSettings() {
  saveSettingsButton.disabled = true;
  await sendMessage({
    type: "SYNTHCODE_SET_CONFIG",
    config: { apiBaseUrl: apiBaseUrl.value }
  });
  saveSettingsButton.disabled = false;
  setStatus("Saved", "good");
}

function renderScore(result) {
  const score = Number(result.overall_score || 0);
  const percent = Math.round(score * 100);
  scoreBlock.hidden = false;
  scoreValue.textContent = `${percent}%`;
  scoreLabel.textContent = result.label || labelForScore(score);
  scoreMeta.textContent = `${Number(result.files_analyzed || 0)} files, ${formatDate(result.scanned_at)}`;
}

function parseGitHubRepo(url) {
  try {
    const parsed = new URL(url);
    if (parsed.hostname !== "github.com") {
      return null;
    }

    const parts = parsed.pathname.split("/").filter(Boolean);
    if (parts.length < 2) {
      return null;
    }

    return { owner: parts[0], repo: parts[1], branch: "main" };
  } catch {
    return null;
  }
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

function setStatus(text, tone) {
  statusPill.textContent = text;
  if (tone) {
    statusPill.dataset.tone = tone;
  } else {
    delete statusPill.dataset.tone;
  }
}

function formatDate(value) {
  if (!value) {
    return "just now";
  }
  return new Date(value).toLocaleDateString();
}

function sendMessage(message) {
  return chrome.runtime.sendMessage(message).catch((error) => ({ ok: false, error: error.message }));
}
