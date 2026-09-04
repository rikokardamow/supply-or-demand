from __future__ import annotations

import pandas as pd
import pytest
from pipelines.ofac.client import fetch_sdn_csv

# Real rows copied verbatim from a live fetch of the actual SDN CSV (not a vcrpy
# cassette -- the real file is ~5.7 MB, recording it would bloat the repo for no
# benefit; same size-driven reasoning as other crafted-fixture tests in this
# project). Confirmed-real: MAR AZUL is a Cuba-flagged tug with a real IMO number in
# its remarks; MOA NICKEL SA is a genuine multi-program row (the "] [" delimiter).
_FAKE_CSV = (
    '4238,"MAR AZUL","vessel","CUBA] [CUBA-EO14404",-0- ,"CL2192","Tug",-0- ,"212",'
    '"Cuba","Samir de Navegacion S.A.",'
    '"Vessel Registration Identification IMO 7406784."\n'
    '3751,"MOA NICKEL SA",-0- ,"CUBA] [CUBA-EO14404",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,'
    '"Organization Established Date 1994; Organization Type: Mining of other '
    'non-ferrous metal ores."\n'
    '36,"AEROCARIBBEAN AIRLINES",-0- ,"CUBA",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- \n'
    "\n"  # the real trailing-blank-line artifact confirmed live at EOF
)


class _FakeResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        pass

    @property
    def text(self) -> str:
        return _FAKE_CSV


def test_fetch_sdn_csv_parses_real_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "pipelines.ofac.client.requests.get", lambda *args, **kwargs: _FakeResponse()
    )

    df = fetch_sdn_csv()

    assert len(df) == 3  # the trailing blank line is dropped
    assert list(df.columns) == [
        "sanction_id",
        "name",
        "entity_type",
        "programs",
        "call_sign",
        "vess_type",
        "vess_flag",
        "vess_owner",
        "remarks",
    ]


def test_fetch_sdn_csv_splits_multi_program_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "pipelines.ofac.client.requests.get", lambda *args, **kwargs: _FakeResponse()
    )

    df = fetch_sdn_csv()

    mar_azul = df[df["sanction_id"] == "4238"].iloc[0]
    assert mar_azul["programs"] == ["CUBA", "CUBA-EO14404"]

    airlines = df[df["sanction_id"] == "36"].iloc[0]
    assert airlines["programs"] == ["CUBA"]


def test_fetch_sdn_csv_maps_null_placeholder_and_entity_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pipelines.ofac.client.requests.get", lambda *args, **kwargs: _FakeResponse()
    )

    df = fetch_sdn_csv()

    airlines = df[df["sanction_id"] == "36"].iloc[0]
    assert airlines["entity_type"] == "entity"  # blank/-0- mapped to "entity"
    # -0- -> null, not the literal string. pandas represents a mapped None as a
    # float NaN in the resulting column (confirmed live), not Python's None
    # singleton -- pd.isna() is the correct check, matching pipelines/ofac/
    # tagging.py's own null-handling.
    assert pd.isna(airlines["remarks"])

    mar_azul = df[df["sanction_id"] == "4238"].iloc[0]
    assert mar_azul["entity_type"] == "vessel"
    assert mar_azul["vess_flag"] == "Cuba"
