"""Conflict Detector (PRD section 13).

Compares normalized numeric claims about the SAME entity+metric from
DIFFERENT sources. Per the PRD's explicit instruction, a conflict is never
reported just because two values differ - period, currency/unit, and basis
compatibility are checked first, and a mismatch there explains the
difference away as a normalization issue rather than a genuine
disagreement (e.g. "EBITDA = $10B adjusted" vs "EBITDA = $8B GAAP").
"""
from __future__ import annotations

from collections import defaultdict

from app.schemas import Basis, Claim, ClaimType, Conflict, ConflictReasonType, PeriodType

CONFLICT_TOLERANCE_PCT = 1.0  # values within this % are treated as agreeing, not conflicting


class ConflictDetector:
    def detect(self, claims: list[Claim]) -> list[Conflict]:
        groups: dict[tuple[str, str], list[Claim]] = defaultdict(list)
        for claim in claims:
            if claim.claim_type != ClaimType.NUMERIC or not claim.normalized or claim.normalized.magnitude is None:
                continue
            groups[(claim.entity.strip().lower(), claim.metric)].append(claim)

        conflicts: list[Conflict] = []
        for (_entity, _metric), group in groups.items():
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    a, b = group[i], group[j]
                    if a.source_id == b.source_id:
                        continue
                    conflict = self._compare(a, b)
                    if conflict is not None:
                        conflicts.append(conflict)
        return conflicts

    def _compare(self, a: Claim, b: Claim) -> Conflict | None:
        if not _periods_compatible(a, b):
            return _make_conflict(
                a, b, ConflictReasonType.PERIOD_MISMATCH,
                f"Claims refer to different reporting periods ({a.period or 'unspecified'} vs "
                f"{b.period or 'unspecified'}); values are not directly comparable.",
                is_genuine=False,
            )

        if a.normalized.base_unit != b.normalized.base_unit:
            return _make_conflict(
                a, b, ConflictReasonType.UNIT_CURRENCY_MISMATCH,
                f"Claims use different currencies/units ({a.normalized.base_unit} vs {b.normalized.base_unit}); "
                f"values are not directly comparable without an FX conversion this system does not perform.",
                is_genuine=False,
            )

        mag_a, mag_b = a.normalized.magnitude, b.normalized.magnitude
        if mag_a == 0 and mag_b == 0:
            pct_diff = 0.0
        elif mag_a == 0 or mag_b == 0:
            pct_diff = 100.0
        else:
            pct_diff = abs(mag_a - mag_b) / max(abs(mag_a), abs(mag_b)) * 100

        if pct_diff <= CONFLICT_TOLERANCE_PCT:
            return None  # values agree within tolerance - not a conflict

        if a.basis != b.basis and a.basis != Basis.UNKNOWN and b.basis != Basis.UNKNOWN:
            return _make_conflict(
                a, b, ConflictReasonType.BASIS_MISMATCH,
                f"{a.metric} differs between sources ({a.value} {a.unit or ''} vs {b.value} {b.unit or ''}, "
                f"{pct_diff:.1f}% apart), but the sources use different accounting bases "
                f"({a.basis.value} vs {b.basis.value}) - likely explains the difference rather than a genuine disagreement.",
                is_genuine=False,
            )

        return _make_conflict(
            a, b, ConflictReasonType.GENUINE_DISAGREEMENT,
            f"{a.metric} differs meaningfully between sources ({pct_diff:.1f}% apart) despite matching "
            f"period, currency/unit, and accounting basis.",
            is_genuine=True,
        )


def _periods_compatible(a: Claim, b: Claim) -> bool:
    pa, pb = a.normalized.period_type, b.normalized.period_type
    if pa != PeriodType.UNKNOWN and pb != PeriodType.UNKNOWN and pa != pb:
        return False
    la = (a.normalized.period_label or "").strip().lower()
    lb = (b.normalized.period_label or "").strip().lower()
    if la and lb and la != lb:
        return False
    return True


def _make_conflict(a: Claim, b: Claim, reason_type: ConflictReasonType, explanation: str, is_genuine: bool) -> Conflict:
    return Conflict(
        entity=a.entity,
        metric=a.metric,
        claim_id_a=a.claim_id,
        claim_id_b=b.claim_id,
        source_id_a=a.source_id,
        source_id_b=b.source_id,
        value_a=f"{a.value} {a.unit or ''}".strip(),
        value_b=f"{b.value} {b.unit or ''}".strip(),
        reason_type=reason_type,
        explanation=explanation,
        is_genuine_conflict=is_genuine,
    )
