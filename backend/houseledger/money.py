"""Conversions between rupees and integer paise, and Indian-style formatting."""

from decimal import Decimal, InvalidOperation

from .models import ValidationError


def rupees_to_paise(value: str | int | float) -> int:
    """Convert a rupee amount such as "2,400", 2400 or "99.50" to paise exactly."""
    text = str(value).replace(",", "").replace("₹", "").strip()
    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise ValidationError(f"I couldn't understand the amount '{value}'.") from None
    if not amount.is_finite():
        raise ValidationError(f"I couldn't understand the amount '{value}'.")
    if amount != amount.quantize(Decimal("0.01")):
        raise ValidationError("Amounts can have at most two decimal places.")
    return int(amount * 100)


def format_inr(paise: int) -> str:
    """Format paise as rupees with Indian digit grouping, e.g. 12345650 -> '₹1,23,456.50'."""
    sign = "-" if paise < 0 else ""
    rupees, rem = divmod(abs(paise), 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join([*groups, tail])
    text = f"{sign}₹{digits}"
    if rem:
        text += f".{rem:02d}"
    return text
