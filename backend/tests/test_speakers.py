import pytest

from orchestrator.speakers import identify_speaker

MEMBERS = ["Rahul", "Priya", "Neha"]


@pytest.mark.parametrize(
    ("utterance", "speaker"),
    [
        ("This is Priya. I paid Rahul back ₹500.", "Priya"),
        ("Alexa, this is neha, who owes what?", "Neha"),
        ("Hey Alexa, it's Rahul. Split the pizza.", "Rahul"),
        ("I'm Priya and I bought milk for ₹60", "Priya"),
        ("I am Neha", "Neha"),
        ("My name is Rahul", "Rahul"),
        ("Priya here, settle up please", "Priya"),
        ("Neha.", "Neha"),  # answering "Who's speaking?"
        (" priya ", "Priya"),
    ],
)
def test_identifies_self_introductions(utterance, speaker):
    assert identify_speaker(utterance, MEMBERS) == speaker


@pytest.mark.parametrize(
    "utterance",
    [
        "It's ₹900, just me and Neha.",  # mentions Neha, but Neha isn't introducing themselves
        "This is the pizza bill",
        "I'm paying Priya back",
        "Split it with Priya and Neha",
        "This is Raj",  # not a household member
        "Who owes what?",
    ],
)
def test_ignores_everything_else(utterance):
    assert identify_speaker(utterance, MEMBERS) is None
