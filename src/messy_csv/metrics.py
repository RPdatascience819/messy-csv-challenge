"""Comparacao before/after entre dois ProfileResult."""

from __future__ import annotations

from dataclasses import dataclass

from messy_csv.profile import DIMENSION_LABELS, ProfileResult


@dataclass(frozen=True)
class DimensionDelta:
    key: str
    label: str
    before: float
    after: float

    @property
    def delta(self) -> float:
        return self.after - self.before


@dataclass(frozen=True)
class Comparison:
    before: ProfileResult
    after: ProfileResult
    rows_quarantined: int

    @property
    def dimensions(self) -> list[DimensionDelta]:
        antes = self.before.dimensions
        depois = self.after.dimensions
        return [
            DimensionDelta(chave, rotulo, antes[chave], depois[chave])
            for chave, rotulo in DIMENSION_LABELS.items()
        ]

    @property
    def score_delta(self) -> float:
        return round(self.after.score - self.before.score, 1)

    @property
    def rows_kept(self) -> int:
        return self.after.rows

    @property
    def quarantine_rate(self) -> float:
        return self.rows_quarantined / self.before.rows


def compare(before: ProfileResult, after: ProfileResult, rows_quarantined: int) -> Comparison:
    return Comparison(before=before, after=after, rows_quarantined=rows_quarantined)
