from app.agents.query_planner import QueryPlanner


def test_single_company_query_resolves_ticker_and_period():
    plan = QueryPlanner().plan("Analyze Apple Q3 2024")
    assert len(plan.companies) == 1
    assert plan.companies[0].ticker == "AAPL"
    assert plan.companies[0].resolved is True
    assert plan.period == "Q3 2024"
    assert not plan.is_comparison
    assert len(plan.sub_queries) > 0


def test_comparison_query_resolves_both_companies():
    plan = QueryPlanner().plan("Compare Apple and Microsoft")
    names = {c.name for c in plan.companies}
    assert "Apple Inc." in names
    assert "Microsoft Corporation" in names
    assert plan.is_comparison is True


def test_unresolvable_company_produces_empty_companies_list():
    plan = QueryPlanner().plan("Analyze Zzzznotarealcompany Q1 2024")
    assert plan.companies == []


def test_subqueries_are_tagged_with_owning_company_for_comparisons():
    plan = QueryPlanner().plan("Compare Apple and Microsoft")
    companies_seen = {sq.company for sq in plan.sub_queries if sq.company}
    assert "Apple Inc." in companies_seen
    assert "Microsoft Corporation" in companies_seen


def test_fy_period_is_normalized_with_a_space():
    plan = QueryPlanner().plan("Analyze Microsoft's revenue, profitability and major risks for FY2024")
    assert plan.period == "FY 2024"
    assert "revenue" in plan.requested_metrics
