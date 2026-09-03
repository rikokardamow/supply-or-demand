"""Curated energy-complex ticker universe for the Adanos sentiment overlay (Spec 17).

Every symbol below is confirmed live against the real Adanos API (`/compare`'s own
`company_name` field is the real existence signal -- see this package's own
CLAUDE.md: a completely fake ticker still returns HTTP 200 with zeroed metrics, so
"the call succeeded" is NOT evidence a ticker is real; only a non-null `company_name`
is). One real wrong guess caught this way: Seplat Energy's actual Adanos ticker is
`SEPLAT`, not the `SEPL` (its LSE ticker) initially assumed -- found via `/search`.

Organised by energy-complex segment and geography so the coverage reasoning is
auditable. Total: 57."""

from __future__ import annotations

# (ticker, company_name as confirmed live, geo)
TICKERS: dict[str, str] = {
    # US integrated majors / large independents
    "XOM": "US",
    "CVX": "US",
    "COP": "US",
    "OXY": "US",
    "FANG": "US",
    # US E&P
    "DVN": "US",
    "EOG": "US",
    # US refiners
    "VLO": "US",
    "MPC": "US",
    "PSX": "US",
    "PBF": "US",
    # US midstream / pipelines
    "KMI": "US",
    "WMB": "US",
    "OKE": "US",
    "ET": "US",
    "EPD": "US",
    # Oilfield services
    "SLB": "US",
    "HAL": "US",
    "BKR": "US",
    "NOV": "US",
    # Gas / LNG
    "LNG": "US",
    "AR": "US",
    "EQT": "US",
    # Coal
    "BTU": "US",
    # Uranium / nuclear fuel
    "CCJ": "CA",
    "UEC": "US",
    "UUUU": "US",
    # Renewables
    "NEE": "US",
    "FSLR": "US",
    "ENPH": "US",
    "BEP": "CA",
    # International majors / ADRs
    "SHEL": "GB",
    "BP": "GB",
    "TTE": "FR",
    "EQNR": "NO",
    "E": "IT",
    "PBR": "BR",
    "SU": "CA",
    "CNQ": "CA",
    "CVE": "CA",
    # Asia-Pacific
    "WDS": "AU",
    # Energy-complex ETFs (broad + thematic + regional)
    "XLE": "US",
    "VDE": "US",
    "IXC": "US",
    "USO": "US",
    "UNG": "US",
    "XOP": "US",
    "OIH": "US",
    "AMLP": "US",
    "TAN": "US",
    "ICLN": "US",
    "URA": "US",
    # OPEC / OPEC+ geographic exposure -- Libya/Nigeria/Iraq/Venezuela's own NOCs are
    # wholly state-owned with no publicly-traded shares at all; these are real,
    # currently-listed pure-plays giving genuine indirect exposure instead. Libya and
    # Venezuela have no standalone listed pure-play identified -- their exposure in
    # this basket stays indirect, through E/TTE (Libya JVs) and CVX (Venezuela JV)
    # above.
    "GENL": "GB",  # Genel Energy -- Iraq/Kurdistan pure-play, LSE
    "GKP": "GB",  # Gulf Keystone Petroleum -- Iraq/Kurdistan pure-play, LSE
    "SEPLAT": "NG",  # Seplat Energy -- Nigeria, dual LSE/NGX
    "OANDO": "NG",  # Oando -- Nigeria, NGX
    "ARADEL": "NG",  # Aradel Holdings -- Nigeria, NGX (2024 IPO)
}

PLATFORMS = ["reddit", "x", "news", "polymarket"]
COMPARE_BATCH_SIZE = 10
