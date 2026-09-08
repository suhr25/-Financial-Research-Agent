"""Hand-labelled evaluation set for the ConflictDetector (PRD section 18:
"conflict detection precision/recall"). Each case is a pair of numeric
claims about the same entity+metric with a ground-truth label for whether
they represent a genuine conflict, an explainable non-conflict (basis/
period/unit mismatch), or plain agreement (no conflict should be raised at
all).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConflictEvalCase:
    case_id: str
    entity: str
    metric: str
    value_a: str
    unit_a: str
    period_a: str
    basis_a: str
    value_b: str
    unit_b: str
    period_b: str
    basis_b: str
    expected_conflict_raised: bool  # should ConflictDetector emit a Conflict object at all?
    expected_is_genuine: bool | None  # if raised, should is_genuine_conflict be True?
    scenario: str


CASES = [
    ConflictEvalCase("cfl_001", "Apple Inc.", "revenue", "85.8", "billion", "Q3 2024", "unknown",
                      "90.0", "billion", "Q3 2024", "unknown", True, True, "genuine_disagreement"),
    ConflictEvalCase("cfl_002", "Apple Inc.", "revenue", "85.8", "billion", "Q3 2024", "unknown",
                      "85.81", "billion", "Q3 2024", "unknown", False, None, "within_tolerance_no_conflict"),
    ConflictEvalCase("cfl_003", "Apple Inc.", "ebitda", "10", "billion", "Q3 2024", "adjusted",
                      "8", "billion", "Q3 2024", "gaap", True, False, "basis_mismatch"),
    ConflictEvalCase("cfl_004", "Apple Inc.", "revenue", "85.8", "billion", "Q3 2024", "unknown",
                      "391.0", "billion", "FY 2024", "unknown", True, False, "period_mismatch"),
    ConflictEvalCase("cfl_005", "Reliance Industries", "revenue", "100", "crore", "FY 2024", "unknown",
                      "12", "million", "FY 2024", "unknown", True, False, "currency_mismatch"),
    ConflictEvalCase("cfl_006", "Microsoft Corporation", "net_income", "21.9", "billion", "Q3 2024", "unknown",
                      "22.0", "billion", "Q3 2024", "unknown", False, None, "within_tolerance_no_conflict"),
    ConflictEvalCase("cfl_007", "Microsoft Corporation", "operating_margin", "45.0", "%", "Q3 2024", "gaap",
                      "38.0", "%", "Q3 2024", "non_gaap", True, False, "basis_mismatch"),
    ConflictEvalCase("cfl_008", "Microsoft Corporation", "operating_margin", "45.0", "%", "Q3 2024", "unknown",
                      "30.0", "%", "Q3 2024", "unknown", True, True, "genuine_disagreement"),
    ConflictEvalCase("cfl_009", "Tesla, Inc.", "cash_and_equivalents", "29.1", "billion", "Q2 2024", "unknown",
                      "16.4", "billion", "FY 2024", "unknown", True, False, "period_mismatch"),
    ConflictEvalCase("cfl_010", "Tesla, Inc.", "revenue", "25.5", "billion", "Q2 2024", "unknown",
                      "25.5", "billion", "Q2 2024", "unknown", False, None, "identical_no_conflict"),
    ConflictEvalCase("cfl_011", "NVIDIA Corporation", "net_income", "16.6", "billion", "Q2 2024", "unknown",
                      "6.2", "billion", "Q2 2024", "unknown", True, True, "genuine_disagreement"),
    ConflictEvalCase("cfl_012", "NVIDIA Corporation", "ebitda", "20.0", "billion", "Q2 2024", "adjusted",
                      "20.05", "billion", "Q2 2024", "gaap", False, None, "within_tolerance_basis_irrelevant"),
    ConflictEvalCase("cfl_013", "Amazon.com, Inc.", "revenue", "1500", "million", "Q2 2024", "unknown",
                      "1.5", "billion", "Q2 2024", "unknown", False, None, "scale_equivalent_no_conflict"),
    ConflictEvalCase("cfl_014", "Amazon.com, Inc.", "total_debt", "58.0", "billion", "Q2 2024", "unknown",
                      "135.0", "billion", "Q2 2024", "unknown", True, True, "genuine_disagreement"),
    ConflictEvalCase("cfl_015", "Amazon.com, Inc.", "total_debt", "58.0", "billion", "TTM", "unknown",
                      "135.0", "billion", "Q2 2024", "unknown", True, False, "period_type_mismatch"),
]
