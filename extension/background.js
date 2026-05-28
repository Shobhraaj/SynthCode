const DEFAULT_API_BASE = "http://localhost:8000";
const CACHE_TTL_MS = 24 * 60 * 60 * 1000;
const MODEL_VERSION = "mock-extension-v1";

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  handleMessage(message)
    .then((response) => sendResponse({ ok: true, ...response }))
    .catch((error) => sendResponse({ ok: false, error: error.message }));
  return true;
});

async function handleMessage(message) {
  switch (message?.type) {
    case "SYNTHCODE_GET_CONFIG":
      return { config: await getConfig() };
    case "SYNTHCODE_SET_CONFIG":
      await setConfig(message.config || {});
      return { config: await getConfig() };
    case "SYNTHCODE_GET_CACHED":
      return { result: await getCachedResult(message.repo) };
    case "SYNTHCODE_ANALYZE_REPO":
      return { result: await analyzeRepo(message.repo, Boolean(message.forceRescan)) };
    default:
      throw new Error("Unknown SynthCode message");
  }
}

async function getConfig() {
  const values = await storageGet(["apiBaseUrl"]);
  return {
    apiBaseUrl: values.apiBaseUrl || DEFAULT_API_BASE
  };
}

async function setConfig(config) {
  const apiBaseUrl = String(config.apiBaseUrl || DEFAULT_API_BASE).replace(/\/+$/, "");
  await storageSet({ apiBaseUrl });
}

async function analyzeRepo(repo, forceRescan = false) {
  validateRepo(repo);

  const cached = await getCachedResult(repo);
  if (!forceRescan && cached) {
    return { ...cached, source: cached.source || "client-cache" };
  }

  const config = await getConfig();
  try {
    const result = await requestBackendAnalysis(config.apiBaseUrl, repo, forceRescan);
    await cacheResult(repo, result);
    return result;
  } catch (error) {
    const result = buildMockResult(repo, error.message);
    await cacheResult(repo, result);
    return result;
  }
}

async function requestBackendAnalysis(apiBaseUrl, repo, forceRescan) {
  const body = {
    owner: repo.owner,
    repo: repo.repo,
    branch: repo.branch || "main",
    force_rescan: forceRescan
  };

  const analyzeResponse = await fetch(`${apiBaseUrl}/api/v1/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });

  if (!analyzeResponse.ok) {
    throw new Error(`API returned ${analyzeResponse.status}`);
  }

  const payload = await analyzeResponse.json();
  if (payload.result || payload.overall_score !== undefined) {
    return normalizeResult(payload.result || payload, "backend");
  }

  if (!payload.job_id) {
    throw new Error("API response did not include a result or job_id");
  }

  return pollJob(apiBaseUrl, payload.job_id);
}

async function pollJob(apiBaseUrl, jobId) {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    await sleep(2000);
    const response = await fetch(`${apiBaseUrl}/api/v1/status/${encodeURIComponent(jobId)}`);
    if (!response.ok) {
      throw new Error(`Status API returned ${response.status}`);
    }

    const payload = await response.json();
    if (payload.status === "completed" && payload.result) {
      return normalizeResult(payload.result, "backend");
    }
    if (payload.status === "completed" && payload.result_url) {
      const resultUrl = new URL(payload.result_url, apiBaseUrl);
      const resultResponse = await fetch(resultUrl.toString());
      if (!resultResponse.ok) {
        throw new Error(`Results API returned ${resultResponse.status}`);
      }
      return normalizeResult(await resultResponse.json(), "backend");
    }
    if (payload.status === "failed" || payload.status === "timeout") {
      throw new Error(payload.error || payload.message || "Analysis failed");
    }
  }

  throw new Error("Analysis timed out");
}

function normalizeResult(result, source) {
  const score = clamp(Number(result.overall_score ?? result.score ?? 0), 0, 1);
  const fileScores = Array.isArray(result.file_scores) ? result.file_scores : [];

  return {
    owner: result.owner,
    repo: result.repo,
    branch: result.branch || "main",
    overall_score: score,
    label: result.label || labelForScore(score),
    files_analyzed: Number(result.files_analyzed ?? fileScores.length ?? 0),
    file_scores: fileScores.slice(0, 8).map((file) => ({
      path: String(file.path || file.file_path || "unknown"),
      score: clamp(Number(file.score || 0), 0, 1),
      language: file.language || inferLanguage(file.path || file.file_path || "")
    })),
    scanned_at: result.scanned_at || new Date().toISOString(),
    model_version: result.model_version || MODEL_VERSION,
    source
  };
}

function buildMockResult(repo, fallbackReason) {
  const seed = hashString(`${repo.owner}/${repo.repo}/${repo.branch || "main"}`);
  const score = 0.18 + (seed % 7200) / 10000;
  const paths = [
    "src/index.ts",
    "src/utils.ts",
    "app/main.py",
    "lib/analyzer.js",
    "README.md"
  ];

  const file_scores = paths.map((path, index) => {
    const drift = (((seed >> (index * 3)) % 18) - 9) / 100;
    return {
      path,
      score: clamp(score + drift, 0.03, 0.97),
      language: inferLanguage(path)
    };
  });

  return {
    owner: repo.owner,
    repo: repo.repo,
    branch: repo.branch || "main",
    overall_score: clamp(score, 0.03, 0.97),
    label: labelForScore(score),
    files_analyzed: file_scores.length,
    file_scores,
    scanned_at: new Date().toISOString(),
    model_version: MODEL_VERSION,
    source: "mock-fallback",
    note: `Backend unavailable, using deterministic mock score. ${fallbackReason || ""}`.trim()
  };
}

async function getCachedResult(repo) {
  if (!repo?.owner || !repo?.repo) {
    return null;
  }

  const key = cacheKey(repo);
  const values = await storageGet([key]);
  const cached = values[key];
  if (!cached || Date.now() - cached.cached_at > CACHE_TTL_MS) {
    return null;
  }

  return cached.result;
}

async function cacheResult(repo, result) {
  await storageSet({
    [cacheKey(repo)]: {
      cached_at: Date.now(),
      result
    }
  });
}

function cacheKey(repo) {
  return `synthcode:${repo.owner}/${repo.repo}:${repo.branch || "main"}`;
}

function validateRepo(repo) {
  if (!repo?.owner || !repo?.repo) {
    throw new Error("Missing repository owner or name");
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

function inferLanguage(path) {
  const extension = String(path).split(".").pop();
  const languages = {
    js: "JavaScript",
    jsx: "JavaScript",
    ts: "TypeScript",
    tsx: "TypeScript",
    py: "Python",
    java: "Java",
    cpp: "C++",
    cc: "C++",
    go: "Go",
    rs: "Rust",
    rb: "Ruby",
    php: "PHP",
    md: "Markdown"
  };
  return languages[extension] || "Code";
}

function hashString(value) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function storageGet(keys) {
  return chrome.storage.local.get(keys);
}

function storageSet(values) {
  return chrome.storage.local.set(values);
}
