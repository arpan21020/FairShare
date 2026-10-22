"""Domain types and errors. All money is integer paise (₹1 = 100 paise)."""

from dataclasses import dataclass, field

CATEGORIES = (
    "groceries",
    "rent",
    "utilities",
    "food",
    "household",
    "transport",
    "entertainment",
    "travel",
    "other",
)

# Guard against misheard amounts ("twenty four lakh" instead of "two thousand four hundred").
MAX_AMOUNT_PAISE = 10_00_000 * 100  # ₹10,00,000


class LedgerError(Exception):
    """Base error. Messages are written so an assistant can speak them to the user."""


class ValidationError(LedgerError):
    """The request is malformed or inconsistent."""


class NotFoundError(LedgerError):
    """A referenced member, expense, payment or action does not exist."""


@dataclass(frozen=True)
class Member:
    id: int
    name: str
    position: int


@dataclass
class Expense:
    id: int
    payer: str
    total_paise: int
    description: str
    category: str
    date: str
    shares: dict[str, int]
    split: dict
    created_by: str
    created_at: str
    replayed: bool = False  # True when an idempotent retry returned an existing expense


@dataclass
class Payment:
    id: int
    from_member: str
    to_member: str
    amount_paise: int
    date: str
    note: str
    created_by: str
    created_at: str
    replayed: bool = False


@dataclass(frozen=True)
class Transfer:
    from_member: str
    to_member: str
    amount_paise: int


@dataclass
class UndoResult:
    action: str
    entity: str
    entity_id: int
    summary: str


@dataclass
class MonthlySummary:
    month: str
    total_paise: int
    expense_count: int
    by_category: dict[str, int] = field(default_factory=dict)
    paid_by_member: dict[str, int] = field(default_factory=dict)
    share_by_member: dict[str, int] = field(default_factory=dict)
