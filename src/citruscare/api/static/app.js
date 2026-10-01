const pages = {
  "/": ["CitrusCare dashboard", "Service overview for the running local intelligence engine."],
  "/playground": ["Intelligence playground", "Explore the real API-to-SDK flow using synthetic fixtures."],
  "/agents": ["Agent runner", "Run the informational orchestration path and inspect its policy and tool outcomes."],
  "/knowledge": ["Knowledge explorer", "Search the in-memory synthetic knowledge repository."],
  "/evidence": ["Evidence retrieval", "Run deterministic retrieval and inspect source provenance."],
  "/tools": ["Tool registry", "Inspect available tools and execute only registered synthetic-demo tools."],
  "/audit": ["Audit trail", "Look up in-memory events by request ID returned from an API call."],
  "/health": ["Service health", "Inspect the local API and configured model route."]
};

const path = location.pathname;
const page = pages[path] || pages["/"];
document.querySelector("#page-title").textContent = page[0];
document.querySelector("#page-subtitle").textContent = page[1];
for (const link of document.querySelectorAll(".sidebar nav a")) {
  if (link.pathname === path) link.classList.add("active");
}

const controls = document.querySelector("#control-panel");
const output = document.querySelector("#output");
const outputTitle = document.querySelector("#output-title");
const latency = document.querySelector("#latency");

function control(title, intro) {
  controls.replaceChildren();
  const heading = document.createElement("div");
  heading.innerHTML = `<p class="eyebrow">ENGINE OPERATION</p><h2>${title}</h2>`;
  controls.append(heading);
  if (intro) {
    const note = document.createElement("p");
    note.className = "muted";
    note.textContent = intro;
    controls.append(note);
  }
}

function field(labelText, name, placeholder, value = "", tag = "input") {
  const label = document.createElement("label");
  label.htmlFor = name;
  label.textContent = labelText;
  const input = document.createElement(tag);
  input.id = name;
  input.name = name;
  input.placeholder = placeholder;
  input.value = value;
  controls.append(label, input);
  return input;
}

function selectField(labelText, name, options) {
  const label = document.createElement("label");
  label.htmlFor = name;
  label.textContent = labelText;
  const select = document.createElement("select");
  select.id = name;
  for (const [value, text] of options) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = text;
    select.append(option);
  }
  controls.append(label, select);
  return select;
}

function button(text, handler) {
  const submit = document.createElement("button");
  submit.className = "button";
  submit.type = "button";
  submit.textContent = text;
  submit.addEventListener("click", () => handler(submit));
  controls.append(submit);
  return submit;
}

async function request(url, options = {}) {
  const start = performance.now();
  const response = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) }
  });
  const data = await response.json();
  latency.textContent = `${Math.round(performance.now() - start)} ms`;
  if (!response.ok) {
    const providerError = data.error;
    const message = providerError?.message || data.detail || data.errors?.[0]?.message || `HTTP ${response.status}`;
    const error = new Error(message);
    if (providerError?.code) error.code = providerError.code;
    throw error;
  }
  return data;
}

function show(data, title = "Response received") {
  outputTitle.textContent = title;
  const notice = document.createElement("p");
  notice.className = "muted";
  notice.textContent = data.synthetic_data ? "SYNTHETIC DEMO DATA" : "Actual API response";
  output.replaceChildren(notice);
  if (typeof data.answer === "string") {
    const answer = document.createElement("section");
    const answerTitle = document.createElement("h3");
    answerTitle.textContent = "Generated response";
    const answerText = document.createElement("p");
    answerText.textContent = data.answer;
    answer.append(answerTitle, answerText);
    output.append(answer);

    const details = document.createElement("dl");
    for (const [label, value] of [
      ["Safety", data.safety_decision],
      ["Provider / model", `${data.provider || "unknown"} / ${data.model || "unknown"}`],
      ["Request ID", data.request_id],
      ["Grounding", data.grounding?.status || "not reported"],
      ["Model latency", data.model_latency_ms == null ? "not reported" : `${data.model_latency_ms} ms`],
      ["Token usage", data.token_usage ? JSON.stringify(data.token_usage) : "not reported"]
    ]) {
      if (value == null) continue;
      const term = document.createElement("dt");
      term.textContent = label;
      const description = document.createElement("dd");
      description.textContent = String(value);
      details.append(term, description);
    }
    output.append(details);

    for (const [label, items] of [
      ["Retrieved evidence", data.evidence],
      ["Retrieved context", data.retrieved_context],
      ["Agent trace", data.agent_trace],
      ["Warnings", data.warnings]
    ]) {
      if (!Array.isArray(items) || items.length === 0) continue;
      const section = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = `${label} (${items.length})`;
      const pre = document.createElement("pre");
      pre.textContent = JSON.stringify(items, null, 2);
      section.append(summary, pre);
      output.append(section);
    }
  }
  const raw = document.createElement("details");
  const rawSummary = document.createElement("summary");
  rawSummary.textContent = "Full response JSON";
  const pre = document.createElement("pre");
  pre.textContent = JSON.stringify(data, null, 2);
  raw.append(rawSummary, pre);
  output.append(raw);
  const id = data.request_id;
  if (id) sessionStorage.setItem("lastRequestId", id);
}

function failure(error) {
  outputTitle.textContent = "Request failed";
  const message = document.createElement("p");
  message.className = "bad";
  message.textContent = error.code ? `${error.code}: ${error.message}` : error.message;
  output.replaceChildren(message);
}

async function execute(submit, work) {
  submit.disabled = true;
  try {
    show(await work());
  } catch (error) {
    failure(error);
  } finally {
    submit.disabled = false;
  }
}

if (path === "/") {
  control("Engine overview", "Live status and model route details from this running service.");
  button("Load dashboard data", submit => execute(submit, async () => {
    const [health, version, models, providers] = await Promise.all([
      request("/health", { headers: { Accept: "application/json" } }),
      request("/version"),
      request("/v1/models"),
      request("/v1/providers")
    ]);
    return { health, version, models, providers };
  }));
  button("Discover configured models", submit => execute(submit, () =>
    request("/v1/models?discover=true")
  ));
  request("/health", { headers: { Accept: "application/json" } }).then(data => show(data, "Service health")).catch(failure);
} else if (path === "/knowledge" || path === "/evidence") {
  const knowledge = path === "/knowledge";
  control(
    knowledge ? "Search knowledge" : "Search evidence and sources",
    "Queries run against synthetic fixtures. Select a real configured SDK endpoint; results are not clinical evidence."
  );
  const operation = selectField(
    "Operation",
    "search-operation",
    knowledge
      ? [["knowledge", "Knowledge repository"], ["vector", "Vector index"]]
      : [["evidence", "Evidence retrieval"], ["research", "Research agent"], ["medications", "Medication source"], ["vector", "Vector index"]]
  );
  const query = field("Search query", "query", "e.g. synthetic medication");
  button("Run search", submit => execute(submit, async () => {
    const mode = operation.value;
    const endpoint = mode === "knowledge" ? "/v1/knowledge/search"
      : mode === "evidence" ? "/v1/evidence/search"
      : mode === "research" ? "/v1/research"
      : mode === "medications" ? "/v1/medications/search"
      : "/v1/vector/search";
    const payload = mode === "research"
      ? { query: query.value, task: "evidence_search" }
      : { query: query.value, limit: 10 };
    return request(endpoint, { method: "POST", body: JSON.stringify(payload) });
  }));
} else if (path === "/tools") {
  control("Execute a registered tool", "First load the live registry. Tool arguments must match each declared JSON schema.");
  const toolName = field("Tool name", "tool-name", "load registry to see options");
  const args = field("Arguments (JSON)", "tool-args", '{"query":"synthetic"}', '{"query":"synthetic"}', "textarea");
  button("Load registered tools", submit => execute(submit, async () => {
    const result = await request("/v1/tools");
    result.synthetic_data = true;
    const names = result.tools.map(item => item.name).join(", ");
    toolName.placeholder = names;
    const selected = result.tools.find(item => item.name === "search_knowledge") || result.tools[0];
    if (selected) {
      toolName.value = selected.name;
      const values = Object.fromEntries((selected.parameters.required || []).map(name => [
        name,
        name === "patient_id" ? "PATIENT-DEMO-001" :
          name === "medication_id" ? "MED-DEMO-001" : "synthetic evidence note"
      ]));
      args.value = JSON.stringify(values, null, 2);
    }
    show(result, "Registered tools");
    return result;
  }));
  button("Execute tool", submit => execute(submit, async () => {
    const data = await request("/v1/tools/execute", {
      method: "POST", body: JSON.stringify({ name: toolName.value, arguments: JSON.parse(args.value) })
    });
    data.synthetic_data = true;
    return data;
  }));
} else if (path === "/audit") {
  control("Find request audit", "Audit records are process-local and are lost when the server restarts. Last local request ID is prefilled when available.");
  const id = field("Request ID", "request-id", "paste a request ID", sessionStorage.getItem("lastRequestId") || "");
  button("Load audit events", submit => execute(submit, () => request(`/v1/audit/${encodeURIComponent(id.value)}`)));
} else if (path === "/health") {
  control("Service status", "Health and route metadata from the running FastAPI process.");
  button("Refresh status", submit => execute(submit, async () => {
    const [health, version, models, providers] = await Promise.all([
      request("/health", { headers: { Accept: "application/json" } }),
      request("/version"),
      request("/v1/models"),
      request("/v1/providers")
    ]);
    return { health, version, models, providers };
  }));
  request("/health", { headers: { Accept: "application/json" } }).then(data => show(data, "Service health")).catch(failure);
} else {
  control(path === "/agents" ? "Run an agent request" : "Ask the intelligence engine", "This sends a real same-origin HTTP request through FastAPI, the SDK orchestration layer, policy and safety checks, retrieval, tools, and the selected provider.");
  const query = field("Question", "query", "Ask for an informational summary of synthetic demo data", "Summarize the synthetic demo data.");
  const task = selectField("Task", "task", [
    ["general_information", "General information"],
    ["clinical_summary", "Clinical summary"],
    ["patient_context_summary", "Patient context summary"],
    ["medication_information", "Medication information"],
    ["evidence_search", "Evidence search"],
    ["documentation_assistance", "Documentation assistance"]
  ]);
  const structuredLabel = document.createElement("label");
  const structured = document.createElement("input");
  structured.type = "checkbox";
  structured.id = "structured-output";
  structuredLabel.append(structured, document.createTextNode(" Request structured JSON output"));
  controls.append(structuredLabel);
  const routeHint = document.createElement("p");
  routeHint.className = "muted";
  routeHint.textContent = "Loading configured provider route…";
  controls.append(routeHint);
  let modelRoutes = {};
  request("/v1/models").then(data => {
    modelRoutes = data.routes || {};
    const updateRoute = () => {
      const route = modelRoutes[task.value];
      routeHint.textContent = route
        ? `Configured route: ${route.provider} / ${route.model}${route.supports_structured_output ? " · structured output available" : ""}`
        : "No model route is configured for this task.";
    };
    task.addEventListener("change", updateRoute);
    updateRoute();
  }).catch(error => { routeHint.textContent = error.message; });
  button("Run request", submit => execute(submit, () => request(path === "/agents" ? "/v1/agents/run" : "/v1/intelligence/query", {
    method: "POST", body: JSON.stringify({
      query: query.value,
      task: task.value,
      structured_output: structured.checked
    })
  })));
}
