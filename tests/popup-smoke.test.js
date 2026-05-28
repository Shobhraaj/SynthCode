const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");

test("popup parses repository URLs", () => {
  const { context } = loadPopup({
    tabUrl: "https://github.com/openai/openai-python"
  });

  assert.deepEqual(
    plain(context.parseGitHubRepo("https://github.com/openai/openai-python")),
    { owner: "openai", repo: "openai-python", branch: "main" }
  );
  assert.equal(context.parseGitHubRepo("https://example.com/openai/openai-python"), null);
  assert.equal(context.parseGitHubRepo("not-a-url"), null);
});

test("popup init disables scanning for non GitHub tabs", async () => {
  const { context, elements } = loadPopup({
    tabUrl: "https://example.com/"
  });

  await context.init();
  assert.equal(elements.scanButton.disabled, true);
  assert.equal(elements.statusPill.textContent, "Open GitHub");
});

test("popup init renders cached analysis", async () => {
  const cachedResult = {
    overall_score: 0.44,
    label: "mixed",
    files_analyzed: 7,
    scanned_at: "2026-05-28T10:00:00Z"
  };
  const { context, elements } = loadPopup({
    tabUrl: "https://github.com/octocat/hello-world",
    sendMessage: async (message) => {
      if (message.type === "SYNTHCODE_GET_CONFIG") {
        return { config: { apiBaseUrl: "http://localhost:8000" } };
      }
      if (message.type === "SYNTHCODE_GET_CACHED") {
        return { result: cachedResult };
      }
      return {};
    }
  });

  await context.init();
  assert.equal(elements.repoName.textContent, "octocat/hello-world");
  assert.equal(elements.statusPill.textContent, "Cached");
  assert.equal(elements.scoreBlock.hidden, false);
  assert.equal(elements.scoreLabel.textContent, "mixed");
});

test("popup scan handles failure responses", async () => {
  const { context, elements } = loadPopup({
    tabUrl: "https://github.com/octocat/hello-world",
    sendMessage: async (message) => {
      if (message.type === "SYNTHCODE_GET_CONFIG") {
        return { config: { apiBaseUrl: "http://localhost:8000" } };
      }
      if (message.type === "SYNTHCODE_GET_CACHED") {
        return { result: null };
      }
      if (message.type === "SYNTHCODE_ANALYZE_REPO") {
        return { ok: false, error: "network unavailable" };
      }
      return {};
    }
  });

  await context.init();
  await context.scanActiveRepo(true);

  assert.equal(elements.statusPill.textContent, "Failed");
  assert.equal(elements.scoreLabel.textContent, "Analysis unavailable");
  assert.equal(elements.scoreMeta.textContent, "network unavailable");
  assert.equal(elements.scanButton.disabled, false);
});

function loadPopup(overrides = {}) {
  const eventHandlers = {};
  const elements = {
    scanButton: makeElement("scanButton"),
    saveSettings: makeElement("saveSettings"),
    statusPill: makeElement("statusPill"),
    repoName: makeElement("repoName"),
    scoreBlock: makeElement("scoreBlock"),
    scoreValue: makeElement("scoreValue"),
    scoreLabel: makeElement("scoreLabel"),
    scoreMeta: makeElement("scoreMeta"),
    apiBaseUrl: makeElement("apiBaseUrl")
  };
  elements.scoreBlock.hidden = true;

  const context = {
    console,
    URL,
    Date,
    document: {
      getElementById(id) {
        return elements[id];
      },
      addEventListener(type, callback) {
        eventHandlers[type] = callback;
      }
    },
    chrome: {
      tabs: {
        async query() {
          return [{ url: overrides.tabUrl || "https://github.com/openai/openai-python" }];
        }
      },
      runtime: {
        async sendMessage(message) {
          if (overrides.sendMessage) {
            return overrides.sendMessage(message);
          }
          if (message.type === "SYNTHCODE_GET_CONFIG") {
            return { config: { apiBaseUrl: "http://localhost:8000" } };
          }
          if (message.type === "SYNTHCODE_GET_CACHED") {
            return { result: null };
          }
          if (message.type === "SYNTHCODE_ANALYZE_REPO") {
            return {
              result: {
                overall_score: 0.33,
                label: "mixed",
                files_analyzed: 2,
                scanned_at: "2026-05-28T10:00:00Z",
                source: "backend"
              }
            };
          }
          return {};
        }
      }
    }
  };

  vm.runInNewContext(readExtensionFile("popup.js"), context);
  assert.equal(typeof eventHandlers.DOMContentLoaded, "function");
  return { context, elements, eventHandlers };
}

function makeElement(id) {
  return {
    id,
    textContent: "",
    disabled: false,
    hidden: false,
    value: "",
    dataset: {},
    listeners: {},
    addEventListener(type, callback) {
      this.listeners[type] = callback;
    }
  };
}

function readExtensionFile(file) {
  return fs.readFileSync(path.join(root, "extension", file), "utf8");
}

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}
