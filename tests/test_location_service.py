from location_service import detect_district_and_state


def test_single_character_does_not_guess_a_district():
    assert detect_district_and_state("X") == (None, None, "LOW")


def test_unambiguous_three_character_prefix_can_match_a_district():
    assert detect_district_and_state("Pun") == (
        "Pune",
        "Maharashtra",
        "HIGH",
    )
