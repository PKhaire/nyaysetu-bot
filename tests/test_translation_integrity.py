"""Release guards for the user-visible translation catalogue."""

from string import Formatter

import pytest

from translations import TRANSLATIONS


SUPPORTED_LANGUAGES = {"en", "hi", "mr"}


def _format_contract(value: str) -> tuple[tuple[str, str, str | None], ...]:
    """Return the ordered placeholders a caller must supply."""

    return tuple(
        (field_name, format_spec, conversion)
        for _, field_name, format_spec, conversion in Formatter().parse(value)
        if field_name is not None
    )


def test_translation_catalogues_have_identical_keys():
    assert set(TRANSLATIONS) == SUPPORTED_LANGUAGES

    english_keys = set(TRANSLATIONS["en"])
    assert english_keys
    for language, catalogue in TRANSLATIONS.items():
        assert set(catalogue) == english_keys, (
            f"{language} translation keys differ from English"
        )

@pytest.mark.parametrize("language", sorted(SUPPORTED_LANGUAGES))
def test_translations_are_nonempty_and_keep_the_english_format_contract(language):
    english = TRANSLATIONS["en"]
    catalogue = TRANSLATIONS[language]

    for key, value in catalogue.items():
        assert isinstance(value, str), f"{language}.{key} must be text"
        assert value.strip(), f"{language}.{key} must not be blank"
        assert _format_contract(value) == _format_contract(english[key]), (
            f"{language}.{key} changed the placeholders expected by callers"
        )
