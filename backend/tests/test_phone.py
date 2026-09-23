from app.services import phone


def test_normalize_strips_country_code_and_spaces():
    assert phone.normalize("+91 98765 43210") == "9876543210"


def test_normalize_strips_dashes():
    assert phone.normalize("98765-43210") == "9876543210"


def test_normalize_strips_leading_trunk_zero():
    assert phone.normalize("09876543210") == "9876543210"


def test_normalize_handles_none_and_empty():
    assert phone.normalize(None) == ""
    assert phone.normalize("") == ""


def test_normalize_is_idempotent_for_bare_ten_digits():
    assert phone.normalize("9876543210") == "9876543210"


def test_two_representations_of_same_number_match():
    assert phone.normalize("+91-98765 43210") == phone.normalize("9876543210")
