"use strict";

const runButton = document.querySelector("#run-demo");
const runLabel = document.querySelector("#run-label");
const runState = document.querySelector("#run-state");
const outputEmpty = document.querySelector("#output-empty");
const outputContent = document.querySelector("#output-content");
const outputError = document.querySelector("#output-error");
const resultHighlights = document.querySelector("#result-highlights");
const resultJson = document.querySelector("#result-json");
const sdkVersion = document.querySelector("#sdk-version");
const copyButton = document.querySelector("#copy-command");

function setState(state, label) {
  runState.dataset.state = state;
  runState.textContent = label;
}

function addHighlight(label, value) {
  const card = document.createElement("div");
  card.className = "highlight";
  const title = document.createElement("div");
  title.className = "highlight-label";
  title.textContent = label;
  const result = document.createElement("div");
  result.className = "highlight-value";
  result.textContent = String(value);
  card.append(title, result);
  resultHighlights.append(card);
}

function renderResult(data) {
  resultHighlights.replaceChildren();
  addHighlight("SDK package", `${data.package.distribution} v${data.package.version}`);
  addHighlight("Agent response", data.agent.content);
  addHighlight("Tool result", data.direct_sync_tool_result);
  addHighlight(
    "Consent lifecycle",
    data.governance.consent_active_after_revoke ? "still active" : "grant revoked",
  );
  addHighlight("HTTP adapter", data.http_adapter.ai_generated ? "model output" : "fixed local response");
  addHighlight("Clinical value", `${data.clinical_observation.value} ${data.clinical_observation.unit}`);
  addHighlight("Audit events", data.governance.audit_events.length);
  addHighlight("Handled SDK errors", Object.keys(data.handled_errors).length);
  resultJson.textContent = JSON.stringify(data, null, 2);
  outputEmpty.hidden = true;
  outputError.hidden = true;
  outputContent.hidden = false;
  setState("complete", "COMPLETE");
}

runButton.addEventListener("click", async () => {
  runButton.disabled = true;
  runLabel.textContent = "Running synthetic flow…";
  outputContent.hidden = true;
  outputError.hidden = true;
  outputEmpty.hidden = true;
  setState("running", "RUNNING");
  try {
    const response = await fetch("/api/demo", {
      method: "POST",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || `Demo failed (${response.status})`);
    }
    renderResult(payload);
  } catch (error) {
    outputError.textContent = error instanceof Error ? error.message : "Demo request failed.";
    outputError.hidden = false;
    setState("error", "ERROR");
  } finally {
    runButton.disabled = false;
    runLabel.textContent = "Run the integration demo";
  }
});

copyButton.addEventListener("click", async () => {
  const command = "python -m pip install -e C:\\Users\\abhis\\CitrusCare\\citruscare-sdk";
  try {
    await navigator.clipboard.writeText(command);
    copyButton.textContent = "COPIED";
  } catch {
    copyButton.textContent = "SELECT COMMAND";
  }
  window.setTimeout(() => {
    copyButton.textContent = "COPY";
  }, 1500);
});

fetch("/api/health", { headers: { Accept: "application/json" }, cache: "no-store" })
  .then((response) => {
    if (!response.ok) throw new Error("Health check failed");
    return response.json();
  })
  .then((health) => {
    sdkVersion.textContent = `SDK v${health.sdk_version}`;
  })
  .catch(() => {
    sdkVersion.textContent = "SDK status unavailable";
  });
