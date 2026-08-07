from types import SimpleNamespace

import pytest

import services.legal_knowledge as legal_knowledge
from services.legal_knowledge import (
    CATEGORY_SUBCATEGORIES,
    find_guide,
    guide_category_rows,
    guide_feedback_buttons,
    guide_message,
    guide_subcategory_rows,
    parse_guide_feedback_id,
    parse_guide_id,
)
from services.local_ai_service import local_ai_reply


@pytest.mark.parametrize(
    ("language", "expected_text"),
    [
        ("en", "What to do now"),
        ("hi", "Abhi kya karein"),
        ("mr", "आता काय करावे"),
    ],
)
def test_guides_are_complete_and_localised(language, expected_text):
    user = SimpleNamespace(language=language)

    for category, subcategories in CATEGORY_SUBCATEGORIES.items():
        for subcategory in subcategories:
            message = guide_message(user, category, subcategory)
            assert expected_text in message
            assert "legal-content-" in message
            assert len(message) <= 4096


def test_guide_tree_respects_whatsapp_row_contracts():
    user = SimpleNamespace(language="en")
    categories = guide_category_rows(user)

    assert len(categories) == len(CATEGORY_SUBCATEGORIES) <= 10
    assert len({row["id"] for row in categories}) == len(categories)
    assert all(len(row["title"]) <= 24 for row in categories)
    assert all(len(row["description"]) <= 72 for row in categories)

    for category in CATEGORY_SUBCATEGORIES:
        rows = guide_subcategory_rows(user, category)
        assert 1 <= len(rows) <= 10
        assert len({row["id"] for row in rows}) == len(rows)
        assert all(len(row["title"]) <= 24 for row in rows)
        assert all(len(row["description"]) <= 72 for row in rows)
        for row in rows:
            parsed_category, parsed_subcategory = parse_guide_id(row["id"])
            assert parsed_category == category
            assert parsed_subcategory in CATEGORY_SUBCATEGORIES[category]


@pytest.mark.parametrize(
    ("legacy_id", "expected"),
    [
        ("guide::unpaid_salary", ("Job", "Unpaid Salary")),
        ("guide::divorce_family", ("Family", "Divorce")),
        ("guide::consumer_refund", ("Consumer", "Refund Issue")),
        ("guide::cheque_bounce", ("Business", "Cheque Bounce")),
        ("guide::cyber_fraud", ("Criminal", "Cyber Crime")),
        ("guide::property_dispute", ("Property", "Property Dispute")),
        ("guide::police_case", ("Criminal", "Police Case")),
    ],
)
def test_legacy_guide_buttons_remain_valid(legacy_id, expected):
    assert parse_guide_id(legacy_id) == expected


def test_feedback_buttons_round_trip_without_free_text():
    user = SimpleNamespace(language="mr")
    buttons = guide_feedback_buttons(user, "Job", "Unpaid Salary")

    assert len(buttons) == 3
    assert all(len(button["title"]) <= 20 for button in buttons)
    assert parse_guide_feedback_id(buttons[0]["id"]) == (
        "yes",
        "Job",
        "Unpaid Salary",
    )
    assert parse_guide_feedback_id(buttons[1]["id"]) == (
        "no",
        "Job",
        "Unpaid Salary",
    )


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("My company has not paid my salary", ("Job", "Unpaid Salary")),
        ("Builder has delayed possession of my flat", ("Property", "Builder Issue")),
        (
            "Someone made an unauthorized UPI transaction",
            ("Banking", "Unauthorized Transaction"),
        ),
        ("A vehicle hit me and ran away", ("Accident", "Hit and Run")),
        ("मुझे कानूनी नोटिस मिला है", ("Other", "Legal Notice")),
        ("माझा पगार थकीत आहे", ("Job", "Unpaid Salary")),
        ("मेरे खाते से पैसे निकल गए", ("Banking", "Unauthorized Transaction")),
        (
            "My landlord will not return my security deposit",
            ("Property", "Rent or Tenancy"),
        ),
        (
            "Housing society sent me a notice",
            ("Property", "Housing Society Issue"),
        ),
        (
            "There is a dispute about my father's will",
            ("Property", "Inheritance or Will"),
        ),
        (
            "मकान मालिक किराया विवाद कर रहा है",
            ("Property", "Rent or Tenancy"),
        ),
        (
            "माझ्या वडिलांच्या मृत्युपत्राचा वाद आहे",
            ("Property", "Inheritance or Will"),
        ),
    ],
)
def test_free_text_routes_to_a_reviewable_guide(question, expected):
    assert find_guide(question) == expected


def test_every_configured_keyword_alias_routes_without_collision():
    for category, subcategory, phrases in legal_knowledge._KEYWORD_ROUTES:
        for phrase in phrases:
            assert find_guide(phrase) == (category, subcategory)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("I received a legal notice", ("Other", "Legal Notice")),
        (
            "The seller committed online shopping fraud",
            ("Consumer", "Online Fraud"),
        ),
        ("This is my first legal question", ("Other", "General Legal Query")),
        ("My parents are arguing", ("Other", "Not Sure")),
        ("मला विमा दावा करायचा आहे", ("Banking", "Insurance Claim")),
        ("A false FIR was filed", ("Criminal", "False FIR")),
        ("I face police harassment", ("Criminal", "Police Harassment")),
        ("There is a sale deed issue", ("Property", "Sale Deed Issue")),
        ("We have a partition dispute", ("Property", "Partition Dispute")),
        (
            "सड़क पर मेरे साथ मारपीट हुई",
            ("Criminal", "Theft or Assault"),
        ),
        (
            "यह घरेलू मारपीट का मामला है",
            ("Family", "Domestic Violence"),
        ),
        ("दहेज का मामला है", ("Family", "Dowry Case")),
        ("मुझे जमानत चाहिए", ("Criminal", "Bail Matter")),
        ("मेरा संपत्ति विवाद है", ("Property", "Property Dispute")),
        ("पुलिस ने मुझे नोटिस दिया", ("Criminal", "Police Case")),
        (
            "I experienced workplace harassment",
            ("Job", "Workplace Harassment"),
        ),
    ],
)
def test_router_prefers_specific_whole_phrases_and_localized_labels(
    question,
    expected,
):
    assert find_guide(question) == expected


@pytest.mark.parametrize(
    "question",
    [
        "I have an issue",
        "I have a case",
        "I have a dispute",
        "I have a claim",
        "I am facing harassment",
        "pareshani hai",
        "I was a victim of fraud",
    ],
)
def test_ambiguous_generic_terms_do_not_force_a_legal_category(question):
    assert find_guide(question) == ("Other", "Not Sure")


def test_every_visible_subcategory_label_round_trips():
    for category, subcategories in CATEGORY_SUBCATEGORIES.items():
        for subcategory in subcategories:
            if subcategory == "Not Sure":
                continue
            for language in ("en", "hi", "mr"):
                user = SimpleNamespace(language=language)
                label = next(
                    row["title"]
                    for row in guide_subcategory_rows(user, category)
                    if parse_guide_id(row["id"])
                    == (category, subcategory)
                )
                assert find_guide(label) == (category, subcategory)


def test_high_risk_issue_has_specific_safety_overlay():
    user = SimpleNamespace(language="en")

    message = guide_message(user, "Family", "Domestic Violence")

    assert "Prioritise immediate safety" in message
    assert "local emergency services" in message


@pytest.mark.parametrize(
    ("language", "privacy_text"),
    [
        ("en", "Do not send OTP, PIN, CVV"),
        ("hi", "Chat mein OTP, PIN, CVV"),
        ("mr", "चॅटमध्ये OTP, PIN, CVV"),
    ],
)
def test_every_guide_warns_users_not_to_share_sensitive_secrets(
    language,
    privacy_text,
):
    user = SimpleNamespace(language=language)

    for category, subcategories in CATEGORY_SUBCATEGORIES.items():
        for subcategory in subcategories:
            assert privacy_text in guide_message(user, category, subcategory)


def test_local_faq_answers_hinglish_without_external_ai(monkeypatch):
    monkeypatch.setenv("LOCAL_AI_PROVIDER", "")
    user = SimpleNamespace(language="hi")

    reply = local_ai_reply(
        "Meri company ne do mahine ki salary nahi di",
        user,
    )

    assert "Baki Tankhwa" in reply
    assert "Abhi kya karein" in reply
    assert "legal advice nahi" in reply
    assert "lawyer consultation" in reply
