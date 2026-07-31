# utils/i18n.py
import logging
from translations import TRANSLATIONS

logger = logging.getLogger("utils.i18n")

def t(user, key, **kwargs):
    """
    Translation helper with safe fallback
    """

    lang_map = {
        "English": "en",
        "Hinglish": "hi",
        "Hindi": "hi",
        "Marathi": "mr",
        "मराठी": "mr",
        "en": "en",
        "hi": "hi",
        "mr": "mr",
    }

    lang = lang_map.get(user.language, "en")
    translations = TRANSLATIONS.get(lang, {})

    if key not in translations:
        logger.warning("Missing translation: %s.%s", lang, key)

    text = translations.get(
        key,
        TRANSLATIONS["en"].get(key, key)
    )

    return text.format(**kwargs) if kwargs else text
