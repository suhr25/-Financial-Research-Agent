const API = "/api";

const el = (id) => document.getElementById(id);
const queryInput = el("query-input");
const runBtn = el("run-btn");
const statusPanel = el("status-panel");
const statusText = el("status-text");
const errorPanel = el("error-panel");
const resultsPanel = el("results");
const demoBanner = el("demo-banner");

let currentClaims = [];
let currentSources = [];
let currentClaimFilter = "all";

document.addEventListener("DOMContentLoaded", init);

async function init() {
  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      queryInput.value = chip.dataset.query;
      runResearch();
    });
  });
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });
  document.querySelectorAll(".filter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".filter-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentClaimFilter = btn.dataset.filter;
      renderClaims();
    });
  });
  runBtn.addEventListener("click", () => runResearch());
  queryInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") runResearch();
  });

  try {
    const health = await fetchJSON(`${API}/health`);
    demoBanner.classList.remove("hidden");
    if (health.demo_mode) {
      demoBanner.textContent =
        "DEMO MODE: no live API keys configured. All sources below are clearly-labelled mock/synthetic data, not real filings or web results.";
      demoBanner.classList.remove("mock-off");
    } else {
      demoBanner.textContent = `Live mode: LLM provider = ${health.llm_provider}, search provider = ${health.search_provider}.`;
      demoBanner.classList.add("mock-off");
    }
  } catch (e) {
    // health check failing shouldn't block the UI
  }
}

function switchTab(tab) {
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tab}`));
}

async function fetchJSON(url, options) {
  const resp = await fetch(url, options);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.detail || `Request to ${url} failed (${resp.status})`);
  }
  return data;
}

async function runResearch() {
  const query = queryInput.value.trim();
  if (!query) return;

  runBtn.disabled = true;
  errorPanel.classList.add("hidden");
  resultsPanel.classList.add("hidden");
  statusPanel.classList.remove("hidden");
  statusText.textContent = "Planning, retrieving, extracting, and verifying claims… this can take a few seconds.";

  try {
    const run = await fetchJSON(`${API}/research`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });

    if (run.status === "failed") {
      throw new Error(run.error || "Research run failed.");
    }

    const [claims, sources, conflicts, report] = await Promise.all([
      fetchJSON(`${API}/research/${run.research_run_id}/claims`),
      fetchJSON(`${API}/research/${run.research_run_id}/sources`),
      fetchJSON(`${API}/research/${run.research_run_id}/conflicts`),
      fetchJSON(`${API}/research/${run.research_run_id}/report`),
    ]);

    currentClaims = claims;
    currentSources = sources;
    renderAll(run, claims, sources, conflicts, report);
    resultsPanel.classList.remove("hidden");
  } catch (err) {
    errorPanel.textContent = err.message || String(err);
    errorPanel.classList.remove("hidden");
  } finally {
    statusPanel.classList.add("hidden");
    runBtn.disabled = false;
  }
}

function renderAll(run, claims, sources, conflicts, report) {
  renderOverviewCard(run, claims, sources, report);
  el("overview-text").textContent = report.executive_overview.content;
  el("verification-summary-text").textContent = report.claim_verification_summary.content;
  renderComparisonTables(report.comparison_tables);

  renderProseSection("financial-content", report.financial_performance.content);
  renderProseSection("key-metrics-content", report.key_metrics.content);
  renderProseSection("risks-content", report.risks.content);
  renderProseSection("findings-content", report.important_findings.content);

  renderClaims();
  renderConflicts(conflicts);
  renderSources(sources);
  switchTab("overview");
}

function renderOverviewCard(run, claims, sources, report) {
  const plan = run.plan || {};
  const companyNames = (plan.companies || []).map((c) => (c.ticker ? `${c.name} (${c.ticker})` : c.name)).join(", ");
  el("ov-company").textContent = companyNames || plan.raw_query || "—";
  el("ov-period").textContent = plan.period || "Not specified";
  el("ov-status").textContent = run.status;
  el("ov-sources").textContent = sources.length;
  el("ov-claims").textContent = claims.length;
  el("ov-confidence").textContent =
    report.average_confidence != null ? `${(report.average_confidence * 100).toFixed(0)}%` : "—";

  const bar = el("verdict-bar");
  bar.innerHTML = "";
  const pills = [
    ["supported", `${report.supported_claims} Supported`],
    ["contradicted", `${report.contradicted_claims} Contradicted`],
    ["insufficient", `${report.insufficient_claims} Insufficient`],
  ];
  pills.forEach(([cls, label]) => {
    const span = document.createElement("span");
    span.className = `verdict-pill ${cls}`;
    span.textContent = label;
    bar.appendChild(span);
  });
}

function renderProseSection(containerId, content) {
  const container = el(containerId);
  if (!content || !content.trim()) {
    container.innerHTML = '<div class="empty-state">Nothing to show.</div>';
    return;
  }
  container.textContent = content;
}

function renderComparisonTables(tables) {
  const container = el("comparison-tables");
  container.innerHTML = "";
  if (!tables || tables.length === 0) return;
  tables.forEach((table) => {
    const h3 = document.createElement("h2");
    h3.textContent = table.title;
    container.appendChild(h3);
    container.appendChild(buildTable(table.columns, table.rows));
  });
}

function buildTable(columns, rows) {
  const table = document.createElement("table");
  table.className = "compare-table";
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  columns.forEach((c) => {
    const th = document.createElement("th");
    th.textContent = c;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    columns.forEach((c) => {
      const td = document.createElement("td");
      td.textContent = row[c] != null ? row[c] : "";
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  return table;
}

function sourceById(sourceId) {
  return currentSources.find((s) => s.source_id === sourceId);
}

function renderClaims() {
  const container = el("claims-list");
  container.innerHTML = "";
  const filtered =
    currentClaimFilter === "all" ? currentClaims : currentClaims.filter((c) => c.verification_status === currentClaimFilter);

  if (filtered.length === 0) {
    container.innerHTML = '<div class="empty-state">No claims match this filter.</div>';
    return;
  }

  filtered.forEach((claim, idx) => {
    container.appendChild(buildClaimCard(claim, idx));
  });
}

function buildClaimCard(claim, idx) {
  const card = document.createElement("div");
  card.className = "claim-card";

  const source = sourceById(claim.evidence_span.source_id);
  const confidencePct = claim.confidence != null ? Math.round(claim.confidence * 100) : null;

  card.innerHTML = `
    <div class="claim-head">
      <div class="claim-statement">${escapeHtml(claim.statement)}</div>
      <span class="badge ${claim.verification_status}">${claim.verification_status}</span>
    </div>
    <div class="claim-meta">
      ${escapeHtml(claim.entity)} · ${escapeHtml(claim.metric)}
      ${claim.period ? ` · ${escapeHtml(claim.period)}` : ""}
      ${claim.basis && claim.basis !== "unknown" ? ` · basis: ${escapeHtml(claim.basis)}` : ""}
    </div>
    ${
      confidencePct != null
        ? `<div class="confidence-bar-wrap">
            <div class="confidence-bar-track"><div class="confidence-bar-fill" style="width:${confidencePct}%"></div></div>
            <span class="confidence-label">${confidencePct}%</span>
          </div>`
        : ""
    }
    <div class="evidence-box">"${escapeHtml(claim.evidence_span.evidence_text)}"</div>
    <div class="claim-source-row">
      <span class="tier-badge ${source ? source.source_tier : "mock"}">${source ? source.source_tier.replace("_", " ") : "unknown"}</span>
      <span>${source ? escapeHtml(source.title) : "Unknown source"}</span>
    </div>
    <div class="claim-reason-row" style="margin-top:6px; font-size:12.5px; color:#64748b;">${escapeHtml(claim.verification_reason || "")}</div>
    ${
      claim.confidence_breakdown
        ? `<span class="breakdown-toggle" data-idx="${idx}">Show confidence breakdown ▾</span>
           <div class="breakdown-grid" id="breakdown-${idx}">
             ${Object.entries(claim.confidence_breakdown)
               .map(
                 ([k, v]) =>
                   `<div class="breakdown-item"><span class="k">${escapeHtml(k.replace(/_/g, " "))}</span><span class="v">${(v * 100).toFixed(0)}%</span></div>`
               )
               .join("")}
           </div>`
        : ""
    }
  `;

  const toggle = card.querySelector(".breakdown-toggle");
  if (toggle) {
    toggle.addEventListener("click", () => {
      const grid = card.querySelector(`#breakdown-${idx}`);
      grid.classList.toggle("show");
      toggle.textContent = grid.classList.contains("show") ? "Hide confidence breakdown ▴" : "Show confidence breakdown ▾";
    });
  }

  return card;
}

function renderConflicts(conflicts) {
  const container = el("conflicts-content");
  container.innerHTML = "";
  if (!conflicts || conflicts.length === 0) {
    container.innerHTML = '<div class="empty-state">No conflicts were detected between sources.</div>';
    return;
  }

  const rows = conflicts.map((c) => ({
    Metric: c.metric,
    "Source A": c.value_a,
    "Source B": c.value_b,
    Type: c.is_genuine_conflict ? "GENUINE" : `explained (${c.reason_type.replace("_", " ")})`,
    Reason: c.explanation,
  }));
  container.appendChild(buildTable(["Metric", "Source A", "Source B", "Type", "Reason"], rows));
}

function renderSources(sources) {
  const container = el("sources-list");
  container.innerHTML = "";
  if (!sources || sources.length === 0) {
    container.innerHTML = '<div class="empty-state">No sources were retrieved.</div>';
    return;
  }
  sources.forEach((s) => {
    const card = document.createElement("div");
    card.className = "source-card";
    card.innerHTML = `
      <div>
        <div class="source-title">${escapeHtml(s.title)}</div>
        <div class="source-meta">${escapeHtml(s.publisher)}${s.url ? ` · <a href="${escapeHtml(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.url)}</a>` : ""}</div>
        <div class="source-meta">Retrieved: ${new Date(s.retrieved_at).toLocaleString()}</div>
      </div>
      <span class="tier-badge ${s.source_tier}">${s.source_tier.replace("_", " ")}</span>
    `;
    container.appendChild(card);
  });
}

function escapeHtml(str) {
  if (str == null) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
