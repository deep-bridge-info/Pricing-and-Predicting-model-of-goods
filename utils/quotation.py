_quotation_quantity = 3000


def set_quotation_quantity(quantity: int) -> int:
    global _quotation_quantity
    try:
        q = int(quantity)
    except (TypeError, ValueError):
        q = 3000
    if q <= 0:
        q = 3000
    _quotation_quantity = q
    return _quotation_quantity


def get_quotation_quantity() -> int:
    return _quotation_quantity
