const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");

test("background worker analyzes through API and caches results", async () => {
  const { listener, storage } = loadBackground({
    fetch: async () => ({
      ok: true,
      json: async () => ({
        owner: "openai",
        repo: "openai-python",
        overall_score: 0.72,
        label: "AI-coded",
        files_analyzed: 2,
        file_scores: [
          { path: "src/index.ts", score: 0.81 },
          { path: "app/main.py", score: 0.63 }
        ],
        scanned_at: "2026-05-28T10:00:00Z",
        model_version: "test-model"
      })
    })
  });

  const repo = { owner: "openai", repo: "openai-python", branch: "main" };
  const analyzed = await send(listener, {
    type: "SYNTHCODE_ANALYZE_REPO",
    repo,
    forceRescan: true
  });

  assert.equal(analyzed.ok, true);
  assert.equal(analyzed.result.source, "backend");
  assert.equal(analyzed.result.label, "AI-coded");
  assert.equal(analyzed.result.file_scores.length, 2);

  const cached = await send(listener, { type: "SYNTHCODE_GET_CACHED", repo });
  assert.equal(cached.ok, true);
  assert.equal(cached.result.overall_score, 0.72);
  assert.ok(storage["synthcode:openai/openai-python:main"]);
});

test("background worker falls back to deterministic mock result", async () => {
  const { listener } = loadBackground({
    fetch: async () => {
      throw new Error("offline");
    }
  });

  const repo = { owner: "octocat", repo: "hello-world", branch: "main" };
  const first = await send(listener, {
    type: "SYNTHCODE_ANALYZE_REPO",
    repo,
    forceRescan: true
  });
  const second = await send(listener, {
    type: "SYNTHCODE_ANALYZE_REPO",
    repo,
    forceRescan: true
  });

  assert.equal(first.ok, true);
  assert.equal(first.result.source, "mock-fallback");
  assert.equal(first.result.overall_score, second.result.overall_score);
  assert.equal(first.result.file_scores.length, 5);
});

test("content script parses GitHub repository and file routes", () => {
  const context = loadContentScript("/openai/openai-python/blob/main/src/index.ts");

  assert.deepEqual(plain(context.parseGitHubRepo("/openai/openai-python")), {
    owner: "openai",
    repo: "openai-python",
    branch: "main"
  });
  assert.deepEqual(plain(context.parseGitHubRepo("/owner/repo.with.dots")), {
    owner: "owner",
    repo: "repo.with.dots",
    branch: "main"
  });
  assert.equal(
    context.parseGitHubFilePath("/openai/openai-python/blob/main/src/index.ts"),
    "src/index.ts"
  );
  assert.equal(context.parseGitHubRepo("/settings/profile"), null);
});

function loadBackground(overrides = {}) {
  const storage = {};
  let listener = null;
  const context = {
    console,
    fetch: overrides.fetch,
    setTimeout,
    clearTimeout,
    chrome: {
      runtime: {
        onMessage: {
          addListener(callback) {
            listener = callback;
          }
        }
      },
      storage: {
        local: {
          async get(keys) {
            return keys.reduce((values, key) => {
              if (Object.prototype.hasOwnProperty.call(storage, key)) {
                values[key] = storage[key];
              }
              return values;
            }, {});
          },
          async set(values) {
            Object.assign(storage, values);
          }
        }
      }
    }
  };

  vm.runInNewContext(readExtensionFile("background.js"), context);
  assert.equal(typeof listener, "function");
  return { listener, storage };
}

function loadContentScript(pathname) {
  const context = {
    console,
    setTimeout,
    clearTimeout,
    location: { pathname, search: "" },
    window: { setTimeout, clearTimeout },
    chrome: {
      runtime: {
        sendMessage: async () => ({ ok: true, result: null })
      }
    },
    document: {
      documentElement: {},
      getElementById: () => null,
      querySelector: () => null
    },
    MutationObserver: class {
      observe() {}
    }
  };

  vm.runInNewContext(readExtensionFile("content.js"), context);
  return context;
}

function send(listener, message) {
  return new Promise((resolve) => {
    listener(message, {}, resolve);
  });
}

function readExtensionFile(file) {
  return fs.readFileSync(path.join(root, "extension", file), "utf8");
}

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}
