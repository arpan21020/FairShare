import pytest

from houseledger.models import ValidationError
from houseledger.money import format_inr, rupees_to_paise


@pytest.mark.parametrize(
    ("value", "paise"),
    [("2,400", 240000), (2400, 240000), ("99.5", 9950), ("₹1,23,456.75", 12345675), (0.1, 10)],
)
def test_rupees_to_paise(value, paise):
    assert rupees_to_paise(value) == paise


@pytest.mark.parametrize("value", ["abc", "1.234", "NaN", "inf", ""])
def test_rupees_to_paise_rejects_bad_input(value):
    with pytest.raises(ValidationError):
        rupees_to_paise(value)


@pytest.mark.parametrize(
    ("paise", "text"),
    [(0, "₹0"), (96000, "₹960"), (3333, "₹33.33"), (12345650, "₹1,23,456.50"), (-48000, "-₹480"),
     (1000000000, "₹1,00,00,000")],
)
def test_format_inr(paise, text):
    assert format_inr(paise) == text
