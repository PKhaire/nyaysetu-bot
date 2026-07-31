"""User-facing home, self-service, and consultation-preparation helpers.

The functions in this module deliberately return WhatsApp-ready data instead of
sending messages.  Keeping formatting separate from transport makes the flows
easy to test and lets the webhook decide when state changes are committed.
"""

from __future__ import annotations

from typing import Iterable, Optional

from config import PRIVACY_POLICY_URL, SUPPORT_EMAIL, SUPPORT_PHONE
from models import Booking, BookingStatus
from services.booking_service import SLOT_MAP
from services.legal_knowledge import (
    guide_category_rows,
    guide_message,
    guide_subcategory_rows,
)
from utils.date_utils import format_date_readable
from utils.i18n import t


HOME_BUTTON_IDS = {
    "ask_ai": "home_ai",
    "book": "home_book",
    "more": "home_more",
}

MORE_MENU_IDS = {
    "status": "tools_status",
    "prepare": "tools_prepare",
    "guides": "tools_guides",
    "support": "tools_support",
    "privacy": "tools_privacy",
    "language": "tools_language",
}


_STATUS_TRANSLATION_KEYS = {
    BookingStatus.PENDING: "booking_status_pending",
    BookingStatus.PAID: "booking_status_paid",
    BookingStatus.EXPIRED: "booking_status_expired",
    BookingStatus.CANCELLED: "booking_status_cancelled",
    BookingStatus.COMPLETED: "booking_status_completed",
}


_GENERIC_PREP = {
    "en": [
        "A one-page timeline with the most important dates",
        "Notices, orders, agreements, messages, emails, and payment proof",
        "Names and roles of the people or organisations involved",
        "The outcome you want and the three questions you most want answered",
        "Only copies—keep original documents safely with you",
    ],
    "hi": [
        "Important dates ki ek-page timeline",
        "Notices, orders, agreements, messages, emails aur payment proof",
        "Matter mein involved logon/organisations ke naam aur role",
        "Aap kya outcome chahte hain aur lawyer se poochne ke top 3 sawaal",
        "Sirf copies laayein—original documents apne paas safe rakhein",
    ],
    "mr": [
        "महत्त्वाच्या तारखांची एका पानाची कालरेषा",
        "नोटिसा, आदेश, करार, संदेश, ईमेल आणि पेमेंटचे पुरावे",
        "प्रकरणातील व्यक्ती किंवा संस्थांची नावे व भूमिका",
        "आपल्याला अपेक्षित निकाल आणि वकिलांना विचारायचे तीन मुख्य प्रश्न",
        "फक्त प्रती आणा—मूळ कागदपत्रे सुरक्षित ठेवा",
    ],
}


_CATEGORY_PREP = {
    "family": {
        "en": "Marriage/relationship proof, income details, child records, and relevant communication",
        "hi": "Marriage/relationship proof, income details, child records aur relevant communication",
        "mr": "विवाह/नातेसंबंधाचा पुरावा, उत्पन्न तपशील, मुलांची कागदपत्रे आणि संबंधित संवाद",
    },
    "criminal": {
        "en": "FIR/complaint, police or court notices, bail papers, and safely preserved evidence",
        "hi": "FIR/complaint, police ya court notices, bail papers aur safely preserved evidence",
        "mr": "एफआयआर/तक्रार, पोलीस किंवा न्यायालयीन नोटिसा, जामीन कागदपत्रे आणि सुरक्षित पुरावे",
    },
    "accident": {
        "en": "Police report, medical records/bills, vehicle papers, photographs, and insurance communication",
        "hi": "Police report, medical records/bills, vehicle papers, photos aur insurance communication",
        "mr": "पोलीस अहवाल, वैद्यकीय नोंदी/बिले, वाहन कागदपत्रे, छायाचित्रे आणि विमा संवाद",
    },
    "property": {
        "en": "Title/sale documents, agreements, tax records, payment proof, possession records, and notices",
        "hi": "Title/sale documents, agreements, tax records, payment proof, possession records aur notices",
        "mr": "मालकी/विक्री कागदपत्रे, करार, कर नोंदी, पेमेंट पुरावे, ताबा नोंदी आणि नोटिसा",
    },
    "business": {
        "en": "Contracts, invoices, account statements, delivery proof, correspondence, and company records",
        "hi": "Contracts, invoices, account statements, delivery proof, correspondence aur company records",
        "mr": "करार, चलने, खाते विवरण, वितरण पुरावे, पत्रव्यवहार आणि कंपनी नोंदी",
    },
    "job": {
        "en": "Appointment letter, salary slips, attendance, bank entries, HR emails, and termination/resignation papers",
        "hi": "Appointment letter, salary slips, attendance, bank entries, HR emails aur termination/resignation papers",
        "mr": "नियुक्तीपत्र, पगार पावत्या, उपस्थिती, बँक नोंदी, एचआर ईमेल आणि सेवासमाप्ती/राजीनामा कागदपत्रे",
    },
    "consumer": {
        "en": "Invoice/order details, warranty, payment proof, photos, complaint tickets, and seller responses",
        "hi": "Invoice/order details, warranty, payment proof, photos, complaint tickets aur seller responses",
        "mr": "बिल/ऑर्डर तपशील, वॉरंटी, पेमेंट पुरावा, छायाचित्रे, तक्रार क्रमांक आणि विक्रेत्याची उत्तरे",
    },
    "banking": {
        "en": "Statements, transaction IDs, loan/card terms, complaint numbers, notices, and bank responses",
        "hi": "Statements, transaction IDs, loan/card terms, complaint numbers, notices aur bank responses",
        "mr": "खाते विवरण, व्यवहार क्रमांक, कर्ज/कार्ड अटी, तक्रार क्रमांक, नोटिसा आणि बँकेची उत्तरे",
    },
    "other": {
        "en": "Every document that explains the issue, what was agreed, what happened, and what you have already tried",
        "hi": "Issue, agreement, kya hua aur aapne ab tak kya try kiya—yeh dikhane wale documents",
        "mr": "समस्या, ठरलेली बाब, काय घडले आणि आपण आतापर्यंत केलेले प्रयत्न दाखवणारी कागदपत्रे",
    },
}


def language_code(user) -> str:
    value = (getattr(user, "language", None) or "en").lower()
    if value in {"hi", "hindi", "hinglish"}:
        return "hi"
    if value in {"mr", "marathi", "मराठी"}:
        return "mr"
    return "en"


def home_buttons(user) -> list[dict[str, str]]:
    """Return the three WhatsApp reply buttons used by the persistent home."""

    return [
        {"id": HOME_BUTTON_IDS["ask_ai"], "title": t(user, "ask_ai")},
        {"id": HOME_BUTTON_IDS["book"], "title": t(user, "book_consult")},
        {"id": HOME_BUTTON_IDS["more"], "title": t(user, "more_options")},
    ]


def more_menu_rows(user) -> list[dict[str, str]]:
    """Return the self-service menu (kept below WhatsApp's ten-row limit)."""

    return [
        {
            "id": MORE_MENU_IDS["status"],
            "title": t(user, "my_appointment"),
            "description": t(user, "my_appointment_desc"),
        },
        {
            "id": MORE_MENU_IDS["prepare"],
            "title": t(user, "prepare_consultation"),
            "description": t(user, "prepare_consultation_desc"),
        },
        {
            "id": MORE_MENU_IDS["guides"],
            "title": t(user, "legal_guides"),
            "description": t(user, "legal_guides_desc"),
        },
        {
            "id": MORE_MENU_IDS["support"],
            "title": t(user, "talk_to_support"),
            "description": t(user, "talk_to_support_desc"),
        },
        {
            "id": MORE_MENU_IDS["privacy"],
            "title": t(user, "privacy_and_data"),
            "description": t(user, "privacy_and_data_desc"),
        },
        {
            "id": MORE_MENU_IDS["language"],
            "title": t(user, "change_language"),
            "description": t(user, "change_language_desc"),
        },
    ]


def latest_booking(db, whatsapp_id: str) -> Optional[Booking]:
    return (
        db.query(Booking)
        .filter(Booking.whatsapp_id == whatsapp_id)
        .order_by(Booking.id.desc())
        .first()
    )


def latest_booking_with_statuses(
    db,
    whatsapp_id: str,
    statuses: Iterable[BookingStatus],
) -> Optional[Booking]:
    return (
        db.query(Booking)
        .filter(
            Booking.whatsapp_id == whatsapp_id,
            Booking.status.in_(tuple(statuses)),
        )
        .order_by(Booking.id.desc())
        .first()
    )


def booking_status_message(user, booking: Optional[Booking]) -> str:
    if not booking:
        return t(user, "no_appointment_found")

    status = booking.status
    if isinstance(status, str):
        try:
            status = BookingStatus(status)
        except ValueError:
            status = None

    status_key = _STATUS_TRANSLATION_KEYS.get(
        status,
        "booking_status_unknown",
    )
    if (
        status == BookingStatus.CANCELLED
        and booking.payment_processed
        and booking.razorpay_payment_id
    ):
        # A paid booking moved to CANCELLED by the refund workflow retains its
        # payment evidence but must be described accurately to the user.
        status_key = "booking_status_refunded"
    status_text = t(
        user,
        status_key,
    )
    date_text = format_date_readable(booking.date)
    slot_text = SLOT_MAP.get(booking.slot_code, booking.slot_readable or "N/A")

    return t(
        user,
        "booking_status_summary",
        booking_id=booking.id,
        status=status_text,
        date=date_text,
        slot=slot_text,
        category=(booking.category or "N/A").replace("_", " ").title(),
        amount=booking.amount,
    )


def preparation_message(user, booking: Optional[Booking]) -> str:
    lang = language_code(user)
    category = (
        (getattr(booking, "category", None) or getattr(user, "category", None) or "other")
        .lower()
        .replace(" ", "_")
    )
    category_tip = _CATEGORY_PREP.get(category, _CATEGORY_PREP["other"]).get(
        lang,
        _CATEGORY_PREP["other"]["en"],
    )
    generic = _GENERIC_PREP.get(lang, _GENERIC_PREP["en"])
    checklist = [category_tip, *generic]
    bullets = "\n".join(f"{index}. {item}" for index, item in enumerate(checklist, 1))

    return t(
        user,
        "preparation_checklist_message",
        category=category.replace("_", " ").title(),
        checklist=bullets,
    )


def legal_guide_rows(user) -> list[dict[str, str]]:
    """Return the first level of the legal-guide decision tree."""

    return guide_category_rows(user)


def legal_guide_subcategory_rows(
    user,
    category: str,
) -> list[dict[str, str]]:
    """Return the issue choices for one legal-guide category."""

    return guide_subcategory_rows(user, category)


def legal_guide_message(
    user,
    category: str,
    subcategory: str,
) -> str:
    return guide_message(
        user,
        category,
        subcategory,
        include_feedback_prompt=False,
    )


def privacy_message(user) -> str:
    link = ""
    if PRIVACY_POLICY_URL:
        link = f"\n\n{t(user, 'privacy_notice_link')}: {PRIVACY_POLICY_URL}"
    return f"{t(user, 'privacy_notice_short')}{link}"


def support_contact_message(user) -> str:
    contacts = []
    if SUPPORT_PHONE:
        contacts.append(f"{t(user, 'support_phone')}: {SUPPORT_PHONE}")
    if SUPPORT_EMAIL:
        contacts.append(f"{t(user, 'support_email')}: {SUPPORT_EMAIL}")

    configured_contacts = "\n".join(contacts)
    if configured_contacts:
        configured_contacts = f"\n\n{configured_contacts}"

    return f"{t(user, 'support_prompt')}{configured_contacts}"
