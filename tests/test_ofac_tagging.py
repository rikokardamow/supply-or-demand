from __future__ import annotations

from pipelines.ofac.tagging import extract_imo, is_energy_related, resolve_geo


def test_extract_imo_matches_real_confirmed_pattern() -> None:
    remarks = "Vessel Registration Identification IMO 7406784; f.k.a. 'ANA I'."
    assert extract_imo(remarks) == "7406784"


def test_extract_imo_returns_none_when_absent() -> None:
    assert extract_imo("Organization Established Date 1994.") is None
    assert extract_imo(None) is None


def test_is_energy_related_true_for_any_vessel_regardless_of_keywords() -> None:
    assert is_energy_related("MAR AZUL", None, ["CUBA"], "vessel") is True


def test_is_energy_related_true_for_a_keyword_match() -> None:
    assert is_energy_related("Rosneft Trading SA", None, ["RUSSIA-EO14024"], "entity") is True


def test_is_energy_related_false_for_an_unrelated_individual() -> None:
    assert is_energy_related("John Smith", "DOB 1970", ["SDGT"], "individual") is False


def test_resolve_geo_prefers_vess_flag_when_present() -> None:
    assert resolve_geo(["CUBA", "CUBA-EO14404"], "Cuba") == "CU"


def test_resolve_geo_falls_back_to_first_matching_program_prefix() -> None:
    # A real multi-program row -- IRAN itself doesn't literally appear as a program
    # here, but the suffixed variant must still resolve via the prefix check.
    assert resolve_geo(["SDGT", "IRAN-EO13902"], None) == "IR"


def test_resolve_geo_returns_empty_string_for_a_thematic_only_program() -> None:
    assert resolve_geo(["SDGT", "NPWMD"], None) == ""
