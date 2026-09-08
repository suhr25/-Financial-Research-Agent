import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  FileText,
  Filter,
  Globe2,
  LayoutDashboard,
  LoaderCircle,
  Menu,
  PanelLeftClose,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { api, type Claim, type Conflict, type HealthResponse, type Report, type ResearchRun, type Source } from "./services/api";
import "./styles.css";

type Tab = "overview" | "financials" | "risks" | "findings" | "claims" | "conflicts" | "sources";
type ClaimFilter = "all" | "supported" | "contradicted" | "insufficient";

const examples = ["Analyze Apple Q3 2024", "Microsoft FY2024 revenue and risks", "Analyze NVIDIA revenue and profitability", "Compare Apple and Microsoft"];
const tabs: { id: Tab; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "financials", label: "Financials", icon: BarChart3 },
  { id: "risks", label: "Risks", icon: AlertTriangle },
  { id: "findings", label: "Key findings", icon: Sparkles },
  { id: "claims", label: "Claims", icon: ShieldCheck },
  { id: "conflicts", label: "Conflicts", icon: Filter },
  { id: "sources", label: "Sources", icon: BookOpen },
];

function StatusDot({ tone = "teal" }: { tone?: "teal" | "amber" | "red" }) {
  return <span className={`status-dot status-${tone}`} aria-hidden="true" />;
}

function Button({ children, onClick, variant = "secondary", disabled = false, className = "" }: { children: React.ReactNode; onClick?: () => void; variant?: "primary" | "secondary" | "ghost"; disabled?: boolean; className?: string }) {
  return <button type="button" className={`button button-${variant} ${className}`} onClick={onClick} disabled={disabled}>{children}</button>;
}

function Metric({ label, value, detail, tone = "neutral" }: { label: string; value: string; detail: string; tone?: "positive" | "negative" | "neutral" }) {
  return <div className="metric"><span className="eyebrow">{label}</span><strong>{value}</strong><span className={`metric-detail ${tone}`}>{tone === "positive" ? <ArrowUpRight size={12} /> : tone === "negative" ? <ArrowDownRight size={12} /> : null}{detail}</span></div>;
}

function App() {
  const [query, setQuery] = useState("");
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [claimFilter, setClaimFilter] = useState<ClaimFilter>("all");
  const [run, setRun] = useState<ResearchRun | null>(null);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => { api.health().then(setHealth).catch(() => undefined); }, []);

  const runResearch = async (nextQuery = query) => {
    const trimmed = nextQuery.trim();
    if (!trimmed || loading) return;
    setQuery(trimmed); setLoading(true); setError(""); setRun(null); setReport(null); setClaims([]); setSources([]); setConflicts([]);
    try {
      const nextRun = await api.startResearch(trimmed);
      setRun(nextRun);
      if (nextRun.status === "failed") throw new Error(nextRun.error || "Research run failed.");
      const [nextClaims, nextSources, nextConflicts, nextReport] = await Promise.all([
        api.claims(nextRun.research_run_id), api.sources(nextRun.research_run_id), api.conflicts(nextRun.research_run_id), api.report(nextRun.research_run_id),
      ]);
      setClaims(nextClaims); setSources(nextSources); setConflicts(nextConflicts); setReport(nextReport); setActiveTab("overview");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setLoading(false); }
  };

  const company = run?.plan?.companies?.map((item) => item.ticker ? `${item.name} (${item.ticker})` : item.name).join(", ") || run?.plan?.raw_query || "Awaiting research";
  const filteredClaims = useMemo(() => claimFilter === "all" ? claims : claims.filter((claim) => claim.verification_status === claimFilter), [claims, claimFilter]);
  const closeSidebar = () => setSidebarOpen(false);

  return <div className="research-app">
    <div className={`mobile-overlay ${sidebarOpen ? "show" : ""}`} onClick={closeSidebar} />
    <aside className={`sidebar ${collapsed ? "collapsed" : ""} ${sidebarOpen ? "mobile-open" : ""}`}>
      <div className="brand"><div className="logo-mark"><span /><span /><span /></div><div className="brand-copy"><strong>lattice<span>.</span></strong><small>research intelligence</small></div></div>
      <div className="workspace-switcher"><div className="workspace-avatar">F</div><div><strong>Financial Research</strong><small>Evidence workspace</small></div><ChevronDown size={15} /></div>
      <div className="sidebar-section"><span className="nav-label">Workspace</span><button className="nav-item active" type="button"><LayoutDashboard size={17} /><span>Research desk</span></button><button className="nav-item" type="button" onClick={() => setActiveTab("sources")}><BookOpen size={17} /><span>Source library</span></button><button className="nav-item" type="button" onClick={() => setActiveTab("claims")}><ShieldCheck size={17} /><span>Verified claims</span>{claims.length > 0 && <em>{claims.length}</em>}</button></div>
      <div className="sidebar-section sidebar-lower"><span className="nav-label">System</span><button className="nav-item" type="button" onClick={() => api.health().then(setHealth).catch(() => undefined)}><RefreshCw size={17} /><span>Provider status</span></button><button className="nav-item" type="button" onClick={() => setCollapsed(!collapsed)}><PanelLeftClose size={17} /><span>Collapse sidebar</span></button></div>
      <div className="sidebar-footer"><div className="footer-status"><StatusDot tone={health?.demo_mode ? "amber" : "teal"} /><span>{health?.demo_mode ? "Demo mode" : "Live providers"}</span></div><small>{health ? `${health.llm_provider} · ${health.search_provider}` : "Checking providers…"}</small></div>
    </aside>
    <main className={`main ${collapsed ? "expanded" : ""}`}>
      <header className="topbar"><button type="button" className="mobile-menu" aria-label="Open navigation" onClick={() => setSidebarOpen(true)}><Menu size={19} /></button><div className="breadcrumb"><span>Research workspace</span><ChevronRight size={14} /><strong>Desk</strong></div><div className="topbar-meta"><span><StatusDot tone={health?.demo_mode ? "amber" : "teal"} /> {health?.demo_mode ? "Demo data clearly labelled" : "Live provider mode"}</span><div className="top-avatar">FR</div></div></header>
      <div className="content-shell">
        <section className="hero"><div><div className="hero-kicker"><Sparkles size={14} /> VERIFIED FINANCIAL INTELLIGENCE</div><h1>Research desk</h1><p>Ask a question. Trace every answer back to evidence.</p></div><div className="hero-note"><ShieldCheck size={17} /><span>Every factual claim is independently verified against its source.</span></div></section>
        <section className="query-panel"><div className="query-label"><Search size={15} /><label htmlFor="research-query">Company or research query</label><kbd>ENTER</kbd></div><div className="query-row"><input id="research-query" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => event.key === "Enter" && runResearch()} placeholder="e.g. Analyze Apple Q3 2024" disabled={loading} /><Button variant="primary" onClick={() => runResearch()} disabled={loading}>{loading ? <><LoaderCircle size={15} className="spin" /> Running</> : <><Send size={15} /> Run research</>}</Button></div><div className="example-chips">{examples.map((example) => <button type="button" key={example} onClick={() => runResearch(example)} disabled={loading}>{example}</button>)}</div>{health && <div className={`mode-banner ${health.demo_mode ? "demo" : "live"}`}><StatusDot tone={health.demo_mode ? "amber" : "teal"} /><span>{health.demo_mode ? "Demo mode: sources are synthetic and explicitly labelled." : `Live mode: ${health.llm_provider} + ${health.search_provider} providers available.`}</span></div>}</section>
        {loading && <LoadingState />}
        {error && <div className="error-panel"><AlertTriangle size={18} /><div><strong>Research could not be completed</strong><span>{error}</span></div><button type="button" onClick={() => setError("")} aria-label="Dismiss error"><X size={16} /></button></div>}
        {run && report && <ResearchResults company={company} run={run} report={report} claims={claims} sources={sources} conflicts={conflicts} activeTab={activeTab} setActiveTab={setActiveTab} claimFilter={claimFilter} setClaimFilter={setClaimFilter} filteredClaims={filteredClaims} />}
        {!run && !loading && !error && <EmptyState onSelect={(example) => runResearch(example)} />}
      </div>
    </main>
  </div>;
}

function LoadingState() {
  return <section className="loading-state"><div className="loading-orbit"><LoaderCircle size={22} className="spin" /></div><div><strong>Building your verified research brief</strong><p>Planning queries, retrieving sources, extracting claims, and checking evidence.</p></div><div className="loading-steps"><span>Plan</span><span>Retrieve</span><span>Verify</span><span>Report</span></div></section>;
}

function EmptyState({ onSelect }: { onSelect: (query: string) => void }) {
  return <section className="empty-state large"><div className="empty-icon"><Globe2 size={24} /></div><span className="eyebrow">Start with a question</span><h2>Your next research brief begins here.</h2><p>Run a company or comparison query to generate a structured report with source provenance, claim-level verification, and conflict detection.</p><div className="empty-suggestions">{["Analyze NVIDIA revenue and profitability", "Compare Apple and Microsoft"].map((item) => <button type="button" key={item} onClick={() => onSelect(item)}>{item}<ChevronRight size={14} /></button>)}</div></section>;
}

function ResearchResults({ company, run, report, claims, sources, conflicts, activeTab, setActiveTab, claimFilter, setClaimFilter, filteredClaims }: { company: string; run: ResearchRun; report: Report; claims: Claim[]; sources: Source[]; conflicts: Conflict[]; activeTab: Tab; setActiveTab: (tab: Tab) => void; claimFilter: ClaimFilter; setClaimFilter: (filter: ClaimFilter) => void; filteredClaims: Claim[] }) {
  return <section className="results"><div className="results-heading"><div><div className="company-line"><span className="company-monogram">{company.slice(0, 1).toUpperCase()}</span><span>{company}</span><StatusDot /></div><h2>Verified research brief</h2><p>{run.plan?.period || "Period not specified"} · completed {new Date(run.updated_at).toLocaleString()}</p></div><div className="result-actions"><span className="complete-status"><Check size={14} /> {run.status}</span><span className="run-id"><Clock3 size={13} /> {run.research_run_id}</span></div></div><div className="metrics-strip"><Metric label="Sources" value={String(sources.length)} detail="documents retrieved" /><Metric label="Claims" value={String(report.total_claims)} detail="extracted and checked" /><Metric label="Avg. confidence" value={report.average_confidence != null ? `${Math.round(report.average_confidence * 100)}%` : "—"} detail="weighted verification" tone="positive" /><Metric label="Conflicts" value={String(conflicts.length)} detail={conflicts.length ? "review recommended" : "none detected"} tone={conflicts.length ? "negative" : "neutral"} /></div><nav className="tabs" aria-label="Research result sections">{tabs.map(({ id, label, icon: Icon }) => <button type="button" key={id} className={activeTab === id ? "active" : ""} onClick={() => setActiveTab(id)}><Icon size={15} />{label}{id === "claims" && claims.length > 0 && <em>{claims.length}</em>}{id === "conflicts" && conflicts.length > 0 && <em>{conflicts.length}</em>}</button>)}</nav><div className="result-panel">{activeTab === "overview" && <OverviewTab report={report} />}{activeTab === "financials" && <ReportText title="Financial performance" section={report.financial_performance} />}{activeTab === "risks" && <ReportText title="Risks" section={report.risks} />}{activeTab === "findings" && <ReportText title="Important findings" section={report.important_findings} />}{activeTab === "claims" && <ClaimsTab claims={filteredClaims} filter={claimFilter} setFilter={setClaimFilter} sources={sources} />}{activeTab === "conflicts" && <ConflictsTab conflicts={conflicts} />}{activeTab === "sources" && <SourcesTab sources={sources} />}</div></section>;
}

function OverviewTab({ report }: { report: Report }) { return <div className="overview-content"><ReportText title="Executive overview" section={report.executive_overview} /><div className="verification-callout"><ShieldCheck size={19} /><div><strong>Claim verification summary</strong><p>{report.claim_verification_summary.content}</p><div className="verdicts"><span className="supported">{report.supported_claims} supported</span><span className="contradicted">{report.contradicted_claims} contradicted</span><span className="insufficient">{report.insufficient_claims} insufficient</span></div></div></div>{report.comparison_tables?.map((table) => <div className="comparison-block" key={table.title}><div className="section-title"><span className="eyebrow">Comparison</span><h3>{table.title}</h3></div><DataTable columns={table.columns} rows={table.rows} /></div>)}</div>; }
function ReportText({ title, section }: { title: string; section: { title: string; content: string; claim_ids: string[] } }) { return <article className="report-text"><div className="section-title"><span className="eyebrow">Verified report section</span><h3>{title}</h3></div><p>{section.content || "Nothing to show."}</p>{section.claim_ids?.length > 0 && <span className="linked-claims"><ShieldCheck size={13} /> {section.claim_ids.length} linked verified claims</span>}</article>; }
function ClaimsTab({ claims, filter, setFilter, sources }: { claims: Claim[]; filter: ClaimFilter; setFilter: (filter: ClaimFilter) => void; sources: Source[] }) { return <div><div className="panel-heading"><div><span className="eyebrow">Evidence ledger</span><h3>Extracted and verified claims</h3></div><div className="claim-filters">{(["all", "supported", "contradicted", "insufficient"] as ClaimFilter[]).map((item) => <button type="button" key={item} className={filter === item ? "active" : ""} onClick={() => setFilter(item)}>{item}</button>)}</div></div>{claims.length ? claims.map((claim, index) => <ClaimCard claim={claim} key={claim.claim_id} index={index} sources={sources} />) : <div className="empty-inline"><Filter size={17} />No claims match this filter.</div>}</div>; }
function ClaimCard({ claim, index, sources }: { claim: Claim; index: number; sources: Source[] }) { const [open, setOpen] = useState(false); const source = sources.find((item) => item.source_id === claim.evidence_span.source_id); const confidence = claim.confidence == null ? null : Math.round(claim.confidence * 100); const breakdown = claim.confidence_breakdown ?? {}; return <article className="claim-card"><div className="claim-head"><div><strong>{claim.statement}</strong><span>{claim.entity} · {claim.metric}{claim.period ? ` · ${claim.period}` : ""}</span></div><span className={`verdict ${claim.verification_status || "insufficient"}`}>{claim.verification_status || "unverified"}</span></div>{confidence != null && <div className="confidence-row"><div><span style={{ width: `${confidence}%` }} /></div><b>{confidence}%</b></div>}<blockquote>“{claim.evidence_span.evidence_text}”</blockquote><div className="claim-source"><span>{source?.source_tier?.replaceAll("_", " ") || "unknown source"}</span><strong>{source?.title || "Unknown source"}</strong>{source?.publisher && <small>{source.publisher}</small>}</div><div className="claim-footer"><span>{claim.verification_reason || "Verification complete."}</span>{claim.confidence_breakdown && <button type="button" onClick={() => setOpen(!open)}>{open ? "Hide" : "Show"} confidence breakdown <ChevronDown size={13} /></button>}</div>{open && <div className="breakdown-grid">{Object.entries(breakdown).map(([key, value]) => <div key={key}><span>{key.replaceAll("_", " ")}</span><strong>{Math.round(value * 100)}%</strong></div>)}</div>}<span className="claim-index">#{index + 1}</span></article>; }
function ConflictsTab({ conflicts }: { conflicts: Conflict[] }) { return conflicts.length ? <div><div className="panel-heading"><div><span className="eyebrow">Basis-aware comparison</span><h3>Conflicting information</h3></div><AlertTriangle size={18} className="warning" /></div><DataTable columns={["Metric", "Source A", "Source B", "Type", "Reason"]} rows={conflicts.map((item) => ({ Metric: item.metric, "Source A": item.value_a, "Source B": item.value_b, Type: item.is_genuine_conflict ? "Genuine conflict" : `Explained · ${item.reason_type}`, Reason: item.explanation }))} /></div> : <div className="empty-inline"><ShieldCheck size={17} />No conflicts were detected between sources.</div>; }
function SourcesTab({ sources }: { sources: Source[] }) { return <div><div className="panel-heading"><div><span className="eyebrow">Provenance library</span><h3>Retrieved source documents</h3></div><span className="source-count">{sources.length} sources</span></div><div className="source-list">{sources.length ? sources.map((source) => <article className="source-card" key={source.source_id}><div className="source-icon"><FileText size={17} /></div><div className="source-main"><strong>{source.title}</strong><span>{source.publisher} · Retrieved {new Date(source.retrieved_at).toLocaleString()}</span>{source.url && <a href={source.url} target="_blank" rel="noreferrer">Open original source <ArrowUpRight size={13} /></a>}</div><span className="source-tier">{source.source_tier.replaceAll("_", " ")}</span></article>) : <div className="empty-inline">No sources were retrieved.</div>}</div></div>; }
function DataTable({ columns, rows }: { columns: string[]; rows: Record<string, unknown>[] }) { return <div className="table-wrap"><table><thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{String(row[column] ?? "")}</td>)}</tr>)}</tbody></table></div>; }

export default App;
