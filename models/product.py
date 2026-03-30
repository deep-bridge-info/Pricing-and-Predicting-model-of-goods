"""Product data model for the analysis pipeline."""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Product:
    """A normalized Alibaba product with extracted attributes."""
    title: str
    price_usd: float
    product_url: str
    specifications: Dict[str, str] = field(default_factory=dict)
    attributes: Dict[str, Any] = field(default_factory=dict)
    match_score: Optional[float] = None
