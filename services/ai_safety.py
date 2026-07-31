"""Deterministic privacy and safety helpers for NyaySetu AI providers.

The helpers in this module intentionally do not call an AI model.  They form a
small, auditable gate in front of every local or third-party provider.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
import re
import secrets
from typing import Any, Optional


_PROCESS_SALT = secrets.token_bytes(32)


def language_code(user: Any) -> str:
    """Return the supported language code for a user-like object."""

    raw = str(getattr(user, "language", "en") or "en").strip().lower()
    if raw in {"hi", "hindi", "hinglish"}:
        return "hi"
    if raw in {"mr", "marathi", "मराठी"}:
        return "mr"
    return "en"


def _identifier_secret() -> bytes:
    configured = (
        os.getenv("AI_SAFETY_IDENTIFIER_SECRET")
        or os.getenv("AI_SAFETY_SALT")
        or ""
    )
    return configured.encode("utf-8") if configured else _PROCESS_SALT


def safety_identifier(subject: Any) -> str:
    """Create a non-reversible identifier suitable for provider abuse controls.

    A deployment-provided ``AI_SAFETY_IDENTIFIER_SECRET`` makes identifiers
    stable across processes.  Without one they remain private but are stable
    only for the life of this process.
    """

    if hasattr(subject, "whatsapp_id"):
        raw = getattr(subject, "whatsapp_id", None)
    else:
        raw = subject

    if not raw:
        raw = getattr(subject, "id", None) if subject is not None else None
    value = str(raw or "anonymous").encode("utf-8", errors="ignore")
    digest = hmac.new(_identifier_secret(), value, hashlib.sha256).hexdigest()
    return f"ns_{digest[:32]}"


_EMAIL_RE = re.compile(
    r"(?<![\w.+-])[\w.+-]+@(?:[\w-]+\.)+[A-Za-z]{2,}(?![\w-])",
    re.IGNORECASE,
)
_UPI_RE = re.compile(
    r"(?<![\w.-])[\w.-]{2,}@(upi|ybl|ibl|axl|okaxis|okhdfcbank|oksbi|paytm)(?![\w.-])",
    re.IGNORECASE,
)
_PAN_RE = re.compile(r"(?<![A-Z0-9])[A-Z]{5}[0-9]{4}[A-Z](?![A-Z0-9])", re.IGNORECASE)
_AADHAAR_RE = re.compile(r"(?<!\d)(?:\d[ -]?){11}\d(?!\d)")
_LONG_NUMBER_RE = re.compile(r"(?<!\d)(?:\d[ -]?){8,18}\d(?!\d)")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s.-]?)?[6-9]\d{9}(?!\d)")
_SECRET_RE = re.compile(
    r"\b(otp|one[- ]time password|password|passcode|pin|cvv)\b"
    r"(\s*(?:is|:|-)?\s*)[A-Za-z0-9@#$%^&*!_-]{4,32}",
    re.IGNORECASE,
)
_URL_WITH_QUERY_RE = re.compile(r"https?://[^\s?#]+[?#][^\s]+", re.IGNORECASE)


def scrub_pii(text: Any) -> str:
    """Remove common high-risk identifiers before an external provider call.

    This deliberately focuses on identifiers users should not need to disclose
    for general legal information.  It does not claim to be full data-loss
    prevention and must be paired with a user-facing privacy notice.
    """

    cleaned = str(text or "")
    cleaned = _URL_WITH_QUERY_RE.sub("[LINK WITH PRIVATE PARAMETERS REDACTED]", cleaned)
    cleaned = _EMAIL_RE.sub("[EMAIL REDACTED]", cleaned)
    cleaned = _UPI_RE.sub("[UPI ID REDACTED]", cleaned)
    cleaned = _PAN_RE.sub("[PAN REDACTED]", cleaned)
    cleaned = _PHONE_RE.sub("[PHONE REDACTED]", cleaned)
    cleaned = _AADHAAR_RE.sub("[ID NUMBER REDACTED]", cleaned)
    cleaned = _LONG_NUMBER_RE.sub("[LONG NUMBER REDACTED]", cleaned)
    cleaned = _SECRET_RE.sub(lambda match: f"{match.group(1)} [SECRET REDACTED]", cleaned)
    return cleaned.strip()


def pii_was_scrubbed(original: Any, scrubbed: str) -> bool:
    return str(original or "").strip() != scrubbed


@dataclass(frozen=True)
class SafetyDecision:
    category: str
    response: str


_URGENT_PATTERNS = (
    re.compile(
        r"\b(i am|i'm|we are|someone is|my child is)\s+"
        r"(in\s+)?(immediate\s+)?danger\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(attacking me now|beating me now|trying to kill me|"
        r"threatening to kill me|holding me hostage|kidnapped me)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:he|she|they|someone)\s+(?:is|are|'s)\s+"
        r"(?:attacking|beating|choking|threatening to kill)\s+"
        r"(?:me|us|my child)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(i (?:will|want to|am going to|might) (?:kill myself|end my life)|"
        r"about to commit suicide|suicide right now|i (?:feel|am) suicidal|"
        r"i want to die|i do not want to live|i don't want to live)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:i am|i'm)\s+(?:being\s+)?"
        r"(?:assaulted|attacked|beaten|choked|abused)(?:\s+right now)?\b|"
        r"\bmy child is (?:being )?(?:abused|assaulted|beaten|hurt)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bjaan (?:ko|ka) khatra\b|\babhi hamla\b|"
        r"\bmujhe maar rah(?:a|e|i)\b|"
        r"\bmera pati mujhe maar raha\b|"
        r"\bmeri jaan ko khatra\b|"
        r"\b(?:main|mujhe) (?:suicidal|khud ko maar|marna chaht|"
        r"jeena nahi chaht|suicide karn)",
        re.IGNORECASE,
    ),
    re.compile(
        r"मेरी जान को खतरा|"
        r"मुझे(?:\s+\S+){0,2}\s+मार(?:ा|ी|े)?(?:\s+जा)?\s+रह|"
        r"मेरा पति मुझे मार रह|"
        r"मेरे बच्चे को(?:\s+\S+){0,2}\s+"
        r"मार(?:ा|ी|े)?(?:\s+जा)?\s+रह|"
        r"मेरा बच्चा.*(?:खतरे|दुर्व्यवहार|अत्याचार)|"
        r"मैं.*(?:आत्महत्या|मरना चाह|जीना नहीं चाह)|"
        r"मुझे.*(?:आत्महत्या|मरना है)",
        re.IGNORECASE,
    ),
    re.compile(
        r"जीवाला धोका|माझ्या जीवाला धोका|आत्ता हल्ला|मला मारत|"
        r"माझा नवरा मला मारत|मुला(?:ला|वर).*(?:मारत|अत्याचार)|"
        r"आत्महत्या|मला मरायचे|मला जगायचे नाही",
        re.IGNORECASE,
    ),
)

_HARMFUL_PATTERNS = (
    re.compile(
        r"\b(?:how (?:do|can|should) (?:i|we)|how to|ways? to|"
        r"teach me|help me|best way to)\s+"
        r"(?:kill|hurt|attack|shoot|kidnap|poison|blackmail|stalk)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:i want to|i plan to|i am going to|i'm going to|we should)\s+"
        r"(?:kill|hurt|attack|shoot|kidnap|poison|blackmail|stalk)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:how (?:do|can|should) i|how to|ways? to|teach me|help me|best way to)\s+"
        r"(?:destroy|hide|plant|fabricate|forge|fake)\s+"
        r"(?:evidence|a body|documents?|records?|a signature|an alibi)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:how (?:do|can|should) i|how to|ways? to|help me|best way to)\s+"
        r"(?:evade|escape|avoid|bribe)\s+(?:arrest|police|court|a judge)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:hack (?:an? )?(?:account|phone|email)|make a fake fir|"
        r"forge a signature|bribe (?:the )?(?:police|judge)|revenge porn)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:saboot mita|jhootha saboot|police ko rishwat)\b", re.IGNORECASE),
    re.compile(r"पुरावा नष्ट|खोटा पुरावा|पोलिसांना लाच", re.IGNORECASE),
    re.compile(
        r"\bmain (?:kisi ko|use|usko) "
        r"(?:maarna|hurt karna|nuksan pahunchana|kidnap karna|"
        r"zehar dena|blackmail karna) chaht",
        re.IGNORECASE,
    ),
    re.compile(
        r"मैं (?:किसी को|उसे|उसको).*(?:मारना|नुकसान पहुंचाना|"
        r"अपहरण|ज़हर देना|जहर देना|ब्लैकमेल) चाह(?:ता|ती)|"
        r"मुझे (?:उसे|उसको|किसी को).*(?:मारना|नुकसान पहुंचाना|"
        r"अपहरण|ज़हर देना|जहर देना|ब्लैकमेल) है",
        re.IGNORECASE,
    ),
    re.compile(
        r"मला (?:त्याला|तिला|कोणाला).*(?:मारायचे|इजा करायची|"
        r"अपहरण करायचे|विष द्यायचे|ब्लॅकमेल करायचे)|"
        r"मी (?:त्याला|तिला|कोणाला).*(?:मारणार|इजा करणार|"
        r"अपहरण करणार|विष देणार|ब्लॅकमेल करणार)",
        re.IGNORECASE,
    ),
)


_URGENT_RESPONSES = {
    "en": (
        "🚨 If anyone is in immediate danger or needs urgent medical help, "
        "contact local emergency services now and move to a safer place if you "
        "can. This chat cannot dispatch emergency help. Preserve evidence only "
        "when it is safe to do so, and seek prompt help from a qualified lawyer "
        "or an appropriate local support service."
    ),
    "hi": (
        "🚨 Agar kisi ko turant khatra hai ya urgent medical help chahiye, local "
        "emergency services se abhi sampark karein aur mumkin ho to surakshit "
        "jagah par jayen. Yeh chat emergency help dispatch nahi kar sakti. Saboot "
        "sirf tab sambhalein jab aisa karna surakshit ho, aur jaldi qualified "
        "lawyer ya sahi local support service se madad lein."
    ),
    "mr": (
        "🚨 कोणाला तातडीचा धोका असल्यास किंवा तातडीची वैद्यकीय मदत हवी असल्यास, "
        "स्थानिक आपत्कालीन सेवांशी त्वरित संपर्क साधा आणि शक्य असल्यास सुरक्षित "
        "ठिकाणी जा. ही चॅट आपत्कालीन मदत पाठवू शकत नाही. सुरक्षित असेल तेव्हाच "
        "पुरावे जतन करा आणि पात्र वकील किंवा योग्य स्थानिक सहाय्य सेवेकडून त्वरित "
        "मदत घ्या."
    ),
}

_HARMFUL_RESPONSES = {
    "en": (
        "I can’t help plan harm, evade lawful authorities, destroy or fabricate "
        "evidence, forge documents, hack accounts, or bribe anyone. I can explain "
        "lawful options, how to preserve evidence, how to report a concern, or "
        "how to seek advice from a qualified lawyer."
    ),
    "hi": (
        "Main kisi ko nuksan pahunchane, kanooni authorities se bachne, saboot "
        "mitane ya jhoothe saboot banane, documents forge karne, account hack "
        "karne ya rishwat dene mein madad nahi kar sakta. Main lawful options, "
        "saboot surakshit rakhne, report karne ya qualified lawyer se salah lene "
        "ke tareeqe samjha sakta hoon."
    ),
    "mr": (
        "मी कोणाला इजा करण्याचे नियोजन, कायदेशीर अधिकाऱ्यांपासून पळ काढणे, पुरावे "
        "नष्ट किंवा खोटे तयार करणे, कागदपत्रे बनावट करणे, खाते हॅक करणे किंवा लाच "
        "देणे यासाठी मदत करू शकत नाही. मी कायदेशीर पर्याय, पुरावे सुरक्षित ठेवणे, "
        "तक्रार नोंदवणे किंवा पात्र वकिलाचा सल्ला घेणे समजावू शकतो."
    ),
}


def assess_message(message: Any, user: Any = None) -> Optional[SafetyDecision]:
    """Return a deterministic blocking/escalation decision when applicable."""

    text = str(message or "").strip()
    if not text:
        return None

    lang = language_code(user)
    if any(pattern.search(text) for pattern in _URGENT_PATTERNS):
        return SafetyDecision("urgent_risk", _URGENT_RESPONSES[lang])
    if any(pattern.search(text) for pattern in _HARMFUL_PATTERNS):
        return SafetyDecision("harmful_or_illegal_request", _HARMFUL_RESPONSES[lang])
    return None


def guardrail_response(message: Any, user: Any = None) -> Optional[str]:
    decision = assess_message(message, user)
    return decision.response if decision else None
