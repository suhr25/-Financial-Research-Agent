from app.extraction.claim_extractor import ClaimExtractor
from app.schemas import ClaimType, CompanyEntity, ResearchPlan, Source, SourceTier, SourceType


def _mock_source(text: str, title="Test Filing") -> Source:
    return Source(
        title=title,
        url=None,
        source_type=SourceType.MOCK,
        source_tier=SourceTier.MOCK,
        publisher="Test",
        document_text=text,
    )


def _plan(company_name="Apple Inc.", period="Q3 2024") -> ResearchPlan:
    return ResearchPlan(
        raw_query="test",
        companies=[CompanyEntity(name=company_name, ticker="AAPL", resolved=True)],
        period=period,
    )


def test_extracted_claims_have_evidence_that_matches_source_text_exactly():
    """PRD: 'Do not let the LLM invent evidence' / 'Evidence must originate
    from stored source text' - every claim's evidence_text must exactly
    equal source.document_text[start_char:end_char]."""
    text = "Revenue was $85.8 billion for Q3 2024. Operating margin was approximately 29.6%."
    source = _mock_source(text)
    plan = _plan()

    claims = ClaimExtractor(llm=None).extract("run_test", [source], plan)

    assert len(claims) > 0
    for claim in claims:
        assert claim.evidence_span.source_id == source.source_id
        sliced = source.document_text[claim.evidence_span.start_char:claim.evidence_span.end_char]
        assert sliced == claim.evidence_span.evidence_text


def test_extracted_claim_schema_is_canonical():
    text = "Net income was $21.4 billion for Q3 2024."
    source = _mock_source(text)
    claims = ClaimExtractor(llm=None).extract("run_test", [source], _plan())

    numeric_claims = [c for c in claims if c.claim_type == ClaimType.NUMERIC]
    assert numeric_claims, "expected at least one numeric claim"
    claim = numeric_claims[0]
    assert claim.entity == "Apple Inc."
    assert claim.metric == "net_income"
    assert claim.source_id == source.source_id
    assert claim.claim_id.startswith("clm_")


def test_qualitative_risk_sentence_is_extracted_with_correct_span():
    text = "The company faces substantial competition in all markets it operates in."
    source = _mock_source(text)
    claims = ClaimExtractor(llm=None).extract("run_test", [source], _plan())

    qualitative = [c for c in claims if c.claim_type == ClaimType.QUALITATIVE]
    assert len(qualitative) == 1
    c = qualitative[0]
    assert source.document_text[c.evidence_span.start_char:c.evidence_span.end_char] == c.evidence_span.evidence_text
    assert "competition" in c.value.lower()


def test_no_claims_extracted_from_irrelevant_text():
    text = "The weather today is sunny with a chance of rain in the afternoon."
    source = _mock_source(text)
    claims = ClaimExtractor(llm=None).extract("run_test", [source], _plan())
    assert claims == []
