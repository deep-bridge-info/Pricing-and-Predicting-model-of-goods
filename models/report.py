"""Report data models for the sensitivity analysis."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TierStats:
    """Statistics for a single attribute value tier."""
    value: str
    n: int
    median: float
    p25: float
    p75: float
    qcd: float  # Quartile Coefficient of Dispersion: (p75-p25)/(p75+p25)

    @property
    def confidence(self) -> str:
        if self.n >= 5 and self.qcd < 0.3:
            return "reliable"
        if self.n >= 3 and self.qcd < 0.15:
            return "reliable"
        if self.n >= 3:
            return "indicative"
        return "insufficient"


@dataclass
class AttributeDelta:
    """Price delta between current and downgrade tier."""
    attr_name: str
    current_value: str
    downgrade_value: str
    current_tier: TierStats
    downgrade_tier: TierStats
    controlled: bool = True  # False if fell back to uncontrolled comparison

    @property
    def delta(self) -> float:
        return round(self.downgrade_tier.median - self.current_tier.median, 2)

    @property
    def confidence(self) -> str:
        levels = {"reliable": 2, "indicative": 1, "insufficient": 0}
        base = min(
            [self.current_tier.confidence, self.downgrade_tier.confidence],
            key=lambda c: levels[c],
        )
        # Downgrade confidence if uncontrolled (confounded)
        if not self.controlled and base == "reliable":
            return "indicative"
        return base


@dataclass
class SensitivityReport:
    """Full sensitivity analysis report."""
    category: str
    fixed_attrs: Dict[str, str]
    flex_attrs: Dict[str, str]
    baseline: TierStats
    deltas: List[AttributeDelta]
    total_products: int
    matched_products: int
    baseline_is_fallback: bool = False
    combo_estimates: Optional[List[Dict[str, Any]]] = None
