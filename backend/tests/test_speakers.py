import pytest

from orchestrator.speakers import identify_speaker

MEMBERS = ["Aarav", "Priya", "Sam"]


@pytest.mark.parametrize(
    ("utterance", "speaker"),
    [
        ("This is Priya. I paid Aarav back ₹500.", "Priya"),
        ("Alexa, this is sam, who owes what?", "Sam"),
        ("Hey Alexa, it's Aarav. Split the pizza.", "Aarav"),
        ("I'm Priya and I bought milk for ₹60", "Priya"),
        ("I am Sam", "Sam"),
        ("My name is Aarav", "Aarav"),
        ("Priya here, settle up please", "Priya"),
        ("Sam.", "Sam"),  # answering "Who's speaking?"
        (" priya ", "Priya"),
    ],
)
def test_identifies_self_introductions(utterance, speaker):
    assert identify_speaker(utterance, MEMBERS) == speaker


@pytest.mark.parametrize(
    "utterance",
    [
        "It's ₹900, just me and Sam.",  # mentions Sam, but Sam isn't introducing themselves
        "This is the pizza bill",
        "I'm paying Priya back",
        "Split it with Priya and Sam",
        "This is Raj",  # not a household member
        "Who owes what?",
    ],
)
def test_ignores_everything_else(utterance):
    assert identify_speaker(utterance, MEMBERS) is None
