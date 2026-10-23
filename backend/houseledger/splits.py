"""How an expense total is divided between members.

A split has two parts:

1. Optional *exclusive items*: amounts that belong only to some members
   ("only I had the wine, ₹600"). Each item is divided equally among its members.
2. The *main split* of whatever remains, using one method:
   - equal:   divide equally among `participants`
   - weights: divide in proportion to `weights` (e.g. Neha = 0.5 for half a share)
   - percent: divide by `percent`, which must add up to exactly 100
   - exact:   fixed amounts in `exact_paise`, which must add up to the remainder

Rounding rule (largest remainder): each member first gets the floor of their exact
share in paise. The leftover paise are handed out one at a time to the members with
the largest fractional remainder; ties go to the member who joined the household
first. Shares therefore always add up exactly to the total, and the same input always
gives the same result.
"""

import math
from collections.abc import Callable
from fractions import Fraction
from typing import Literal

from pydantic import BaseModel, Field

from .models import Member, ValidationError
from .money import format_inr


class ExclusiveItem(BaseModel):
    amount_paise: int = Field(gt=0, description="Amount of this item in paise.")
    members: list[str] = Field(min_length=1, description="Who this item is for; it is split equally between them.")
    description: str = ""


class SplitSpec(BaseModel):
    method: Literal["equal", "weights", "percent", "exact"] = "equal"
    participants: list[str] = Field(default_factory=list, description="For 'equal': who shares the cost.")
    weights: dict[str, float] = Field(default_factory=dict, description="For 'weights': member -> relative share.")
    percent: dict[str, float] = Field(default_factory=dict, description="For 'percent': member -> percentage.")
    exact_paise: dict[str, int] = Field(default_factory=dict, description="For 'exact': member -> amount in paise.")
    exclusive_items: list[ExclusiveItem] = Field(default_factory=list)


Resolver = Callable[[str], Member]


def compute_shares(total_paise: int, spec: SplitSpec, resolve: Resolver) -> dict[Member, int]:
    """Return each member's share in paise, ordered by household position, zero shares omitted."""
    _check_unused_fields(spec)
    shares: dict[Member, int] = {}

    items_total = sum(item.amount_paise for item in spec.exclusive_items)
    if items_total > total_paise:
        raise ValidationError(
            f"The separate items add up to {format_inr(items_total)}, "
            f"which is more than the bill of {format_inr(total_paise)}."
        )
    for item in spec.exclusive_items:
        members = _resolve_unique(item.members, resolve)
        _add(shares, allocate(item.amount_paise, [(m, Fraction(1)) for m in members]))

    remainder = total_paise - items_total
    if remainder > 0:
        _add(shares, _main_split(remainder, spec, resolve))
    elif _has_main_split(spec):
        raise ValidationError("The separate items already cover the whole bill, so there is nothing left to split.")

    if sum(shares.values()) != total_paise:  # pragma: no cover - guarded by allocate()
        raise AssertionError("shares do not add up to the total")
    return {m: shares[m] for m in sorted(shares, key=lambda m: m.position) if shares[m] > 0}


def allocate(amount_paise: int, weighted: list[tuple[Member, Fraction]]) -> dict[Member, int]:
    """Divide `amount_paise` in proportion to the weights using the largest-remainder rule."""
    total_weight = sum(weight for _, weight in weighted)
    if total_weight <= 0:
        raise ValidationError("The split needs at least one person with a share greater than zero.")
    exact = [(member, amount_paise * weight / total_weight) for member, weight in weighted]
    result = {member: math.floor(value) for member, value in exact}
    leftover = amount_paise - sum(result.values())
    by_remainder = sorted(exact, key=lambda mv: (-(mv[1] - math.floor(mv[1])), mv[0].position))
    for member, _ in by_remainder[:leftover]:
        result[member] += 1
    return result


def _main_split(remainder: int, spec: SplitSpec, resolve: Resolver) -> dict[Member, int]:
    if spec.method == "equal":
        if not spec.participants:
            raise ValidationError("Who should this be split between?")
        members = _resolve_unique(spec.participants, resolve)
        return allocate(remainder, [(m, Fraction(1)) for m in members])

    if spec.method in ("weights", "percent"):
        raw = spec.weights if spec.method == "weights" else spec.percent
        if not raw:
            raise ValidationError(f"Please give the {spec.method} for each person.")
        members = _resolve_unique(list(raw), resolve)
        values = [_fraction(v) for v in raw.values()]
        if any(v < 0 for v in values):
            raise ValidationError("Shares can't be negative.")
        if spec.method == "percent" and sum(values) != 100:
            raise ValidationError(f"The percentages add up to {float(sum(values)):g}%, not 100%.")
        return allocate(remainder, list(zip(members, values)))

    # exact
    if not spec.exact_paise:
        raise ValidationError("Please give the amount for each person.")
    members = _resolve_unique(list(spec.exact_paise), resolve)
    amounts = list(spec.exact_paise.values())
    if any(a < 0 for a in amounts):
        raise ValidationError("Amounts can't be negative.")
    if sum(amounts) != remainder:
        raise ValidationError(
            f"The amounts add up to {format_inr(sum(amounts))}, but the amount to split is {format_inr(remainder)}."
        )
    return dict(zip(members, amounts))


def _resolve_unique(names: list[str], resolve: Resolver) -> list[Member]:
    members = [resolve(name) for name in names]
    if len({m.id for m in members}) != len(members):
        raise ValidationError("The same person is listed twice in the split.")
    return members


def _fraction(value: float) -> Fraction:
    if not math.isfinite(value):
        raise ValidationError("Shares must be ordinary numbers.")
    return Fraction(str(value))  # str() keeps decimal values like 33.33 exact


def _has_main_split(spec: SplitSpec) -> bool:
    return bool(spec.participants or spec.weights or spec.percent or spec.exact_paise)


def _check_unused_fields(spec: SplitSpec) -> None:
    used = {"equal": "participants", "weights": "weights", "percent": "percent", "exact": "exact_paise"}[spec.method]
    for name in ("participants", "weights", "percent", "exact_paise"):
        if name != used and getattr(spec, name):
            raise ValidationError(f"The '{name}' field can't be used with the '{spec.method}' split method.")


def _add(total: dict[Member, int], part: dict[Member, int]) -> None:
    for member, paise in part.items():
        total[member] = total.get(member, 0) + paise
