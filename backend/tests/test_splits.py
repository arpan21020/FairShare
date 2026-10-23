import pytest

from houseledger.models import NotFoundError, ValidationError
from houseledger.splits import ExclusiveItem, SplitSpec

ALL = ["Rahul", "Priya", "Neha"]


def test_equal_split(ledger):
    assert ledger.preview_split(90000, SplitSpec(participants=ALL)) == {"Rahul": 30000, "Priya": 30000, "Neha": 30000}


def test_equal_split_rounding_gives_leftover_paise_to_earliest_members(ledger):
    # ₹100 / 3 = 3333.33… paise each; one leftover paisa goes to the first member.
    assert ledger.preview_split(10000, SplitSpec(participants=ALL)) == {"Rahul": 3334, "Priya": 3333, "Neha": 3333}
    # Two leftover paise go to the first two members, regardless of the order names were given in.
    assert ledger.preview_split(200, SplitSpec(participants=["Neha", "Priya", "Rahul"])) == {
        "Rahul": 67, "Priya": 67, "Neha": 66,
    }


def test_sam_away_half_the_week(ledger):
    # The demo example: ₹2,400 groceries, Neha counts as half a share.
    split = SplitSpec(method="weights", weights={"Rahul": 1, "Priya": 1, "Neha": 0.5})
    assert ledger.preview_split(240000, split) == {"Rahul": 96000, "Priya": 96000, "Neha": 48000}


def test_weights_rounding_uses_largest_remainder(ledger):
    # 1000 paise with weights 1:1:1.5 -> 285.71, 285.71, 428.57 -> floors 285, 285, 428, two paise left.
    # Largest remainders are Rahul and Priya (0.714…) ahead of Neha (0.571…).
    split = SplitSpec(method="weights", weights={"Rahul": 1, "Priya": 1, "Neha": 1.5})
    assert ledger.preview_split(1000, split) == {"Rahul": 286, "Priya": 286, "Neha": 428}


def test_percent_split(ledger):
    split = SplitSpec(method="percent", percent={"Rahul": 50, "Priya": 30, "Neha": 20})
    assert ledger.preview_split(100000, split) == {"Rahul": 50000, "Priya": 30000, "Neha": 20000}


def test_percent_with_decimals_is_exact(ledger):
    split = SplitSpec(method="percent", percent={"Rahul": 33.33, "Priya": 33.33, "Neha": 33.34})
    shares = ledger.preview_split(10000, split)
    assert sum(shares.values()) == 10000


def test_percent_must_total_100(ledger):
    with pytest.raises(ValidationError, match="add up to 90%"):
        ledger.preview_split(1000, SplitSpec(method="percent", percent={"Rahul": 50, "Priya": 40}))


def test_exact_split(ledger):
    split = SplitSpec(method="exact", exact_paise={"Rahul": 1000, "Neha": 500})
    assert ledger.preview_split(1500, split) == {"Rahul": 1000, "Neha": 500}


def test_exact_split_must_match_total(ledger):
    with pytest.raises(ValidationError, match="add up to ₹15"):
        ledger.preview_split(2000, SplitSpec(method="exact", exact_paise={"Rahul": 1000, "Neha": 500}))


def test_exclusive_item_then_equal(ledger):
    # ₹1,800 dinner; the ₹600 wine was only Rahul's; the remaining ₹1,200 is split three ways.
    split = SplitSpec(participants=ALL, exclusive_items=[ExclusiveItem(amount_paise=60000, members=["Rahul"])])
    assert ledger.preview_split(180000, split) == {"Rahul": 100000, "Priya": 40000, "Neha": 40000}


def test_exclusive_items_covering_whole_bill(ledger):
    split = SplitSpec(exclusive_items=[ExclusiveItem(amount_paise=500, members=["Priya", "Neha"])])
    assert ledger.preview_split(500, split) == {"Priya": 250, "Neha": 250}


def test_exclusive_items_larger_than_bill(ledger):
    split = SplitSpec(participants=ALL, exclusive_items=[ExclusiveItem(amount_paise=900, members=["Neha"])])
    with pytest.raises(ValidationError, match="more than the bill"):
        ledger.preview_split(500, split)


def test_names_are_case_insensitive(ledger):
    assert ledger.preview_split(200, SplitSpec(participants=["rahul", " NEHA "])) == {"Rahul": 100, "Neha": 100}


def test_unknown_member(ledger):
    with pytest.raises(NotFoundError, match="anyone called Raj.*Rahul, Priya and Neha"):
        ledger.preview_split(200, SplitSpec(participants=["Rahul", "Raj"]))


def test_duplicate_member(ledger):
    with pytest.raises(ValidationError, match="twice"):
        ledger.preview_split(200, SplitSpec(participants=["Rahul", "rahul"]))


def test_equal_split_needs_participants(ledger):
    with pytest.raises(ValidationError, match="Who should"):
        ledger.preview_split(200, SplitSpec())


def test_fields_must_match_method(ledger):
    with pytest.raises(ValidationError, match="can't be used"):
        ledger.preview_split(200, SplitSpec(method="equal", participants=ALL, weights={"Neha": 0.5}))


def test_negative_and_zero_weights(ledger):
    with pytest.raises(ValidationError, match="negative"):
        ledger.preview_split(200, SplitSpec(method="weights", weights={"Rahul": 1, "Neha": -1}))
    with pytest.raises(ValidationError, match="greater than zero"):
        ledger.preview_split(200, SplitSpec(method="weights", weights={"Rahul": 0, "Neha": 0}))


@pytest.mark.parametrize("total", [0, -100, 10_00_000 * 100 + 1])
def test_invalid_totals(ledger, total):
    with pytest.raises(ValidationError):
        ledger.preview_split(total, SplitSpec(participants=ALL))


@pytest.mark.parametrize("total", [1, 2, 7, 99, 10001, 123457])
@pytest.mark.parametrize("weights", [{"Rahul": 1, "Priya": 1, "Neha": 1}, {"Rahul": 3, "Priya": 0.7, "Neha": 2.2}])
def test_shares_always_sum_to_total(ledger, total, weights):
    assert sum(ledger.preview_split(total, SplitSpec(method="weights", weights=weights)).values()) == total
