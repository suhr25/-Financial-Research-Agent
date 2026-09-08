import pytest

from app.analysis.normalizer import infer_period_type, normalize_value
from app.schemas import PeriodType


@pytest.mark.parametrize(
    "value,unit,evidence,expected_magnitude,expected_unit",
    [
        ("1.2", "billion", "$1.2 billion", 1_200_000_000.0, "USD"),
        ("1,200", "million", "$1,200 million", 1_200_000_000.0, "USD"),
        ("100", "crore", "₹100 crore", 1_000_000_000.0, "INR"),
        ("85800000000", "USD", "revenue_ttm = 85800000000 USD", 85_800_000_000.0, "USD"),
        ("29.6", "%", "Operating margin was approximately 29.6%", 29.6, "%"),
    ],
)
def test_normalize_value_handles_scale_currency_and_percent(value, unit, evidence, expected_magnitude, expected_unit):
    magnitude, base_unit, _note = normalize_value(value, unit, evidence)
    assert magnitude == pytest.approx(expected_magnitude)
    assert base_unit == expected_unit


def test_billion_and_million_representations_are_numerically_equal():
    """PRD section 11: $1.2 billion and $1,200 million must normalize to the
    same magnitude even though their raw textual representations differ."""
    mag_a, unit_a, _ = normalize_value("1.2", "billion", "$1.2 billion")
    mag_b, unit_b, _ = normalize_value("1,200", "million", "$1,200 million")
    assert unit_a == unit_b
    assert mag_a == pytest.approx(mag_b)


def test_unparseable_value_returns_none_magnitude():
    magnitude, base_unit, _note = normalize_value("not-a-number", None, "some text")
    assert magnitude is None
    assert base_unit is None


@pytest.mark.parametrize(
    "period,expected",
    [
        ("Q3 2024", PeriodType.QUARTERLY),
        ("FY 2024", PeriodType.ANNUAL),
        ("FY2024", PeriodType.ANNUAL),
        ("TTM", PeriodType.TTM),
        (None, PeriodType.UNKNOWN),
        ("banana", PeriodType.UNKNOWN),
    ],
)
def test_infer_period_type(period, expected):
    assert infer_period_type(period) == expected
