"""End-to-end test using the FastAPI app with mocked external providers
(DEMO_MODE, forced by conftest.py) - no live API dependency, per PRD
section 21: 'at least one end-to-end test using mocked external providers'.
"""
from fastapi.testclient import TestClient

from app.main import app


def test_full_research_pipeline_via_api():
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["demo_mode"] is True

        resp = client.post("/api/research", json={"query": "Analyze Apple Q3 2024"})
        assert resp.status_code == 200
        run = resp.json()
        assert run["status"] == "complete"
        run_id = run["research_run_id"]

        claims_resp = client.get(f"/api/research/{run_id}/claims")
        assert claims_resp.status_code == 200
        claims = claims_resp.json()
        assert len(claims) > 0
        # 100% citation verification coverage: every claim has a verdict.
        assert all(c["verification_status"] is not None for c in claims)
        # No fabricated citations: every claim's evidence_span source_id must
        # match a source that was actually retrieved and stored.
        sources_resp = client.get(f"/api/research/{run_id}/sources")
        assert sources_resp.status_code == 200
        sources = sources_resp.json()
        source_ids = {s["source_id"] for s in sources}
        for c in claims:
            assert c["evidence_span"]["source_id"] in source_ids

        report_resp = client.get(f"/api/research/{run_id}/report")
        assert report_resp.status_code == 200
        report = report_resp.json()
        assert report["total_claims"] == len(claims)

        conflicts_resp = client.get(f"/api/research/{run_id}/conflicts")
        assert conflicts_resp.status_code == 200


def test_unresolvable_company_fails_gracefully_not_with_a_server_error():
    with TestClient(app) as client:
        resp = client.post("/api/research", json={"query": "Analyze Zzzznotarealcompany Q1 2024"})
        assert resp.status_code == 200
        run = resp.json()
        assert run["status"] == "failed"
        assert run["error"]


def test_unknown_research_id_returns_404():
    with TestClient(app) as client:
        resp = client.get("/api/research/run_does_not_exist")
        assert resp.status_code == 404
