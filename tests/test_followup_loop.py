from app.agents.followup_research import FollowupResearch
from app.agents.research_orchestrator import ResearchOrchestrator
from app.analysis.normalizer import normalize_value
from app.schemas import (
    Basis,
    Claim,
    ClaimType,
    CompanyEntity,
    Evidence,
    NormalizedValue,
    ResearchPlan,
    VerificationVerdict,
)


def _claim(metric, verdict, entity="Apple Inc.") -> Claim:
    magnitude, base_unit, note = normalize_value("85.8", "billion", "$85.8 billion")
    c = Claim(
        research_run_id="run_test", claim_type=ClaimType.NUMERIC, entity=entity, metric=metric,
        value="85.8", unit="billion", period="Q3 2024", basis=Basis.UNKNOWN,
        normalized=NormalizedValue(raw_value="85.8", magnitude=magnitude, base_unit=base_unit, scale_applied=note),
        source_id="src_1", evidence_span=Evidence(source_id="src_1", start_char=0, end_char=5, evidence_text="dummy"),
        statement=f"{metric} was 85.8 billion",
    )
    c.verification_status = verdict
    return c


def _plan():
    return ResearchPlan(raw_query="Analyze Apple Q3 2024", companies=[CompanyEntity(name="Apple Inc.", ticker="AAPL")], period="Q3 2024")


def test_sufficiency_true_when_all_core_metrics_supported():
    claims = [_claim("revenue", VerificationVerdict.SUPPORTED), _claim("operating_margin", VerificationVerdict.SUPPORTED)]
    sufficient, sub_queries, _reason = FollowupResearch(llm=None).assess(_plan(), claims)
    assert sufficient is True
    assert sub_queries == []


def test_sufficiency_false_when_core_metric_insufficient_and_proposes_followup():
    claims = [_claim("revenue", VerificationVerdict.INSUFFICIENT)]
    sufficient, sub_queries, reason = FollowupResearch(llm=None).assess(_plan(), claims)
    assert sufficient is False
    assert len(sub_queries) >= 1
    assert any(sq.purpose == "revenue" for sq in sub_queries)


def test_followup_loop_never_exceeds_configured_max_iterations(db_session, monkeypatch):
    """PRD risk 5.1.3: 'LLM cost control in agentic loops ... unbounded
    iterations' - the loop MUST terminate even if evidence never becomes
    sufficient."""
    orchestrator = ResearchOrchestrator(db_session)
    # get_settings() is process-wide lru_cached, so mutate via monkeypatch
    # (auto-reverted after the test) rather than direct assignment, which
    # would otherwise leak these overrides into every other test.
    monkeypatch.setattr(orchestrator.settings, "max_followup_iterations", 2)
    monkeypatch.setattr(orchestrator.settings, "max_research_queries", 100)  # high enough to not be the limiting factor here

    # Force "always insufficient" so the loop would run forever without the cap.
    def _always_insufficient(plan, claims):
        from app.schemas import SourceType, SubQuery
        return False, [SubQuery(text="Apple Inc. revenue", purpose="revenue", target_source_types=[SourceType.WEB_ARTICLE])], "forced insufficient"

    monkeypatch.setattr(orchestrator.followup_research, "assess", _always_insufficient)

    run = orchestrator.run("Analyze Apple Q3 2024")

    assert run.status.value == "complete"
    assert run.followup_iterations_used <= 2


def test_followup_loop_stops_at_research_query_budget(db_session, monkeypatch):
    orchestrator = ResearchOrchestrator(db_session)
    monkeypatch.setattr(orchestrator.settings, "max_followup_iterations", 10)
    monkeypatch.setattr(orchestrator.settings, "max_research_queries", 5)  # very tight budget

    def _always_insufficient(plan, claims):
        from app.schemas import SourceType, SubQuery
        return False, [SubQuery(text="Apple Inc. revenue", purpose="revenue", target_source_types=[SourceType.WEB_ARTICLE])], "forced insufficient"

    monkeypatch.setattr(orchestrator.followup_research, "assess", _always_insufficient)

    run = orchestrator.run("Analyze Apple Q3 2024")

    assert run.research_queries_used <= 5 + 1  # small slack: one batch may slightly exceed before the check
