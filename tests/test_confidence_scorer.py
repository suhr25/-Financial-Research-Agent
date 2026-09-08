from app.analysis.confidence_scorer import ConfidenceScorer
from app.analysis.normalizer import normalize_value
from app.schemas import (
    Basis,
    Claim,
    ClaimType,
    EntailmentResult,
    Evidence,
    NormalizedValue,
    NumericMatchResult,
    Source,
    SourceTier,
    SourceType,
    VerificationResult,
    VerificationVerdict,
)


def _make_claim_and_verification(source_tier: SourceTier, exact_match: bool, entailment_confidence: float):
    value, unit = "85.8", "billion"
    magnitude, base_unit, note = normalize_value(value, unit, f"${value} {unit}")
    source = Source(
        title="Test source", source_type=SourceType.MOCK, source_tier=source_tier,
        publisher="Test", document_text=f"Revenue was ${value} {unit}.",
    )
    claim = Claim(
        research_run_id="run_test", claim_type=ClaimType.NUMERIC, entity="Apple Inc.", metric="revenue",
        value=value, unit=unit, period="Q3 2024", basis=Basis.UNKNOWN,
        normalized=NormalizedValue(raw_value=value, magnitude=magnitude, base_unit=base_unit, scale_applied=note),
        source_id=source.source_id,
        evidence_span=Evidence(source_id=source.source_id, start_char=0, end_char=10, evidence_text="Revenue wa"),
        statement="Revenue was $85.8 billion",
    )
    verification = VerificationResult(
        claim_id=claim.claim_id,
        numeric_result=NumericMatchResult(applicable=True, exact_match=exact_match, normalized_match=exact_match),
        entailment_result=EntailmentResult(verdict=VerificationVerdict.SUPPORTED, reason="test", confidence=entailment_confidence),
        final_verdict=VerificationVerdict.SUPPORTED,
        combined_reason="test",
    )
    return claim, verification, source


def test_confidence_breakdown_components_are_all_present_and_bounded():
    claim, verification, source = _make_claim_and_verification(SourceTier.PRIMARY_FILING, True, 0.92)
    ConfidenceScorer().score_all([claim], {claim.claim_id: verification}, {source.source_id: source})
    assert claim.confidence is not None
    assert 0.0 <= claim.confidence <= 1.0
    breakdown = claim.confidence_breakdown
    for key in ("source_quality", "evidence_match", "corroboration", "entailment", "final_confidence"):
        assert key in breakdown
        assert 0.0 <= breakdown[key] <= 1.0


def test_primary_filing_source_scores_higher_than_aggregator_source():
    claim_primary, ver_primary, src_primary = _make_claim_and_verification(SourceTier.PRIMARY_FILING, True, 0.9)
    claim_agg, ver_agg, src_agg = _make_claim_and_verification(SourceTier.AGGREGATOR, True, 0.9)

    scorer = ConfidenceScorer()
    scorer.score_all([claim_primary], {claim_primary.claim_id: ver_primary}, {src_primary.source_id: src_primary})
    scorer.score_all([claim_agg], {claim_agg.claim_id: ver_agg}, {src_agg.source_id: src_agg})

    assert claim_primary.confidence > claim_agg.confidence


def test_corroboration_increases_confidence():
    claim_a, ver_a, src_a = _make_claim_and_verification(SourceTier.PRESS, True, 0.9)
    claim_b, ver_b, src_b = _make_claim_and_verification(SourceTier.PRESS, True, 0.9)
    claim_b.source_id = "src_other"  # different source, same entity/metric/value -> corroborates claim_a

    scorer = ConfidenceScorer()
    all_claims = [claim_a, claim_b]
    verifications = {claim_a.claim_id: ver_a, claim_b.claim_id: ver_b}
    sources = {src_a.source_id: src_a, "src_other": src_a}
    scorer.score_all(all_claims, verifications, sources)

    solo_claim, solo_ver, solo_src = _make_claim_and_verification(SourceTier.PRESS, True, 0.9)
    scorer.score_all([solo_claim], {solo_claim.claim_id: solo_ver}, {solo_src.source_id: solo_src})

    assert claim_a.confidence >= solo_claim.confidence
