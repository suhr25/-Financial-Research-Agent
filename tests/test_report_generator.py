from app.analysis.normalizer import normalize_value
from app.generation.report_generator import ReportGenerator
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


def _supported_claim(metric, value, unit, source_id="src_1") -> Claim:
    magnitude, base_unit, note = normalize_value(value, unit, f"{value} {unit}")
    claim = Claim(
        research_run_id="run_test", claim_type=ClaimType.NUMERIC, entity="Apple Inc.", metric=metric,
        value=value, unit=unit, period="Q3 2024", basis=Basis.UNKNOWN,
        normalized=NormalizedValue(raw_value=value, magnitude=magnitude, base_unit=base_unit, scale_applied=note),
        source_id=source_id,
        evidence_span=Evidence(source_id=source_id, start_char=0, end_char=5, evidence_text="dummy"),
        statement=f"{metric} was {value} {unit}",
        confidence=0.9,
    )
    claim.verification_status = VerificationVerdict.SUPPORTED
    claim.verification_reason = "matched"
    return claim


def _plan():
    return ResearchPlan(raw_query="Analyze Apple Q3 2024", companies=[CompanyEntity(name="Apple Inc.", ticker="AAPL")], period="Q3 2024")


def test_every_report_section_only_cites_real_claim_ids():
    claims = [_supported_claim("revenue", "85.8", "billion"), _supported_claim("net_income", "21.4", "billion")]
    valid_ids = {c.claim_id for c in claims}

    report = ReportGenerator(llm=None).generate("run_test", _plan(), claims, [], [])

    for section in (
        report.executive_overview, report.financial_performance, report.key_metrics,
        report.risks, report.important_findings, report.conflicting_information,
        report.claim_verification_summary,
    ):
        for cid in section.claim_ids:
            assert cid in valid_ids, f"section {section.title} cites unknown claim_id {cid}"


def test_report_counts_match_claim_verdicts():
    claims = [_supported_claim("revenue", "85.8", "billion")]
    contradicted = _supported_claim("net_income", "1", "billion")
    contradicted.verification_status = VerificationVerdict.CONTRADICTED
    contradicted.verification_reason = "mismatch"
    claims.append(contradicted)

    report = ReportGenerator(llm=None).generate("run_test", _plan(), claims, [], [])

    assert report.total_claims == 2
    assert report.supported_claims == 1
    assert report.contradicted_claims == 1


def test_empty_claims_produces_a_report_without_crashing():
    report = ReportGenerator(llm=None).generate("run_test", _plan(), [], [], [])
    assert report.total_claims == 0
    assert "No" in report.executive_overview.content or report.executive_overview.content
