# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Resolve country names from UNODC, GI-TOC, HRI, and CEPII files to World Bank ISO3 codes."""
from __future__ import annotations

import difflib
import re
import unicodedata

import pandas as pd

ALIASES = {
    "bolivia": "BOL", "bolivia plurinational state of": "BOL", "plurinational state of bolivia": "BOL",
    "venezuela": "VEN", "venezuela bolivarian republic of": "VEN", "iran": "IRN", "iran islamic republic of": "IRN",
    "laos": "LAO", "lao pdr": "LAO", "lao peoples democratic republic": "LAO", "vietnam": "VNM", "viet nam": "VNM",
    "turkey": "TUR", "turkiye": "TUR", "south korea": "KOR", "korea republic of": "KOR", "republic of korea": "KOR",
    "korea rep": "KOR", "north korea": "PRK", "democratic peoples republic of korea": "PRK", "korea dem peoples rep": "PRK",
    "russia": "RUS", "russian federation": "RUS", "syria": "SYR", "syrian arab republic": "SYR",
    "tanzania": "TZA", "united republic of tanzania": "TZA", "ivory coast": "CIV", "cote divoire": "CIV",
    "dr congo": "COD", "drc": "COD", "democratic republic of the congo": "COD", "congo dem rep": "COD",
    "congo democratic republic of the": "COD", "democratic republic of congo": "COD", "zaire": "COD",
    "congo": "COG", "republic of the congo": "COG", "congo rep": "COG", "congo republic of": "COG",
    "czech republic": "CZE", "czechia": "CZE", "north macedonia": "MKD", "macedonia": "MKD",
    "the former yugoslav republic of macedonia": "MKD", "moldova": "MDA", "republic of moldova": "MDA",
    "united kingdom": "GBR", "uk": "GBR", "united kingdom of great britain and northern ireland": "GBR",
    "great britain": "GBR", "england and wales": "GBR", "scotland": "GBR", "northern ireland": "GBR",
    "united states": "USA", "united states of america": "USA", "usa": "USA", "us": "USA",
    "hong kong": "HKG", "china hong kong sar": "HKG", "hong kong sar china": "HKG", "hong kong china": "HKG",
    "macau": "MAC", "macao": "MAC", "china macao sar": "MAC", "macao sar china": "MAC",
    "kosovo": "XKX", "kosovo under unscr 1244": "XKX", "palestine": "PSE", "state of palestine": "PSE",
    "west bank and gaza": "PSE", "occupied palestinian territory": "PSE", "palestinian territories": "PSE",
    "eswatini": "SWZ", "swaziland": "SWZ", "kingdom of eswatini": "SWZ", "cabo verde": "CPV", "cape verde": "CPV",
    "gambia": "GMB", "the gambia": "GMB", "gambia the": "GMB", "bahamas": "BHS", "the bahamas": "BHS",
    "bahamas the": "BHS", "micronesia": "FSM", "micronesia federated states of": "FSM",
    "micronesia fed sts": "FSM", "saint kitts and nevis": "KNA", "st kitts and nevis": "KNA",
    "saint lucia": "LCA", "st lucia": "LCA", "saint vincent and the grenadines": "VCT",
    "st vincent and the grenadines": "VCT", "brunei": "BRN", "brunei darussalam": "BRN", "egypt": "EGY",
    "egypt arab rep": "EGY", "yemen": "YEM", "yemen rep": "YEM", "kyrgyzstan": "KGZ", "kyrgyz republic": "KGZ",
    "slovakia": "SVK", "slovak republic": "SVK", "timor leste": "TLS", "east timor": "TLS", "myanmar": "MMR",
    "burma": "MMR", "netherlands": "NLD", "netherlands kingdom of the": "NLD", "the netherlands": "NLD",
    "curacao": "CUW", "sint maarten": "SXM", "sint maarten dutch part": "SXM", "st martin french part": "MAF",
    "saint martin": "MAF", "turks and caicos": "TCA", "turks and caicos islands": "TCA",
    "british virgin islands": "VGB", "virgin islands british": "VGB", "us virgin islands": "VIR",
    "virgin islands us": "VIR", "united states virgin islands": "VIR", "somaliland": "SOM",
    "guinea bissau": "GNB", "sao tome and principe": "STP", "micronesia fed states": "FSM",
    "bosnia": "BIH", "bosnia and herzegovina": "BIH", "iraq": "IRQ", "libya": "LBY", "libyan arab jamahiriya": "LBY",
    "vatican": None, "holy see": None, "taiwan": None, "taiwan province of china": None, "china taiwan": None,
    "puerto rico": "PRI", "greenland": "GRL", "faroe islands": "FRO", "new caledonia": "NCL",
    "french polynesia": "PYF", "guam": "GUM", "bermuda": "BMU", "cayman islands": "CYM", "aruba": "ABW",
    "gibraltar": "GIB", "isle of man": "IMN", "channel islands": "CHI", "jersey": "CHI", "guernsey": "CHI",
    "south sudan": "SSD", "sudan": "SDN", "serbia": "SRB", "montenegro": "MNE", "serbia and montenegro": "SRB",
    "yugoslavia": "SRB", "romania": "ROU", "moldova republic of": "MDA", "tanzania united republic of": "TZA",
    "iran islamic rep": "IRN", "venezuela rb": "VEN", "korea": "KOR", "korea dpr": "PRK", "aotearoa new zealand": "NZL", "aotearoa new": "NZL", "federated states of micronesia": "FSM", "somalia": "SOM", "nauru": "NRU", "lao": "LAO", "macedonia fyr": "MKD",
    "st vincent": "VCT", "trinidad": "TTO", "trinidad and tobago": "TTO", "antigua": "ATG",
    "antigua and barbuda": "ATG", "cote d ivoire": "CIV", "united arab emirates": "ARE", "uae": "ARE",
}
# old CEPII (2004) codes -> current World Bank codes
CODE_FIX = {"ROM": "ROU", "ZAR": "COD", "TMP": "TLS", "PAL": "PSE", "YUG": "SRB", "ANT": "CUW"}

_STRIP = re.compile(r"\b(the|of)\b")


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " and ")
    s = re.sub(r"\(.*?\)", lambda m: " " + m.group(0)[1:-1] + " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"[*\d]+$", "", s.strip())
    return re.sub(r"\s+", " ", s).strip()


class CountryResolver:
    def __init__(self, countries: pd.DataFrame):
        self.codes = set(countries["iso3"])
        self.index: dict[str, str | None] = {}
        for _, r in countries.iterrows():
            self.index[norm(r["name"])] = r["iso3"]
            self.index[norm(r["iso3"])] = r["iso3"]
        for k, v in ALIASES.items():
            self.index[norm(k)] = v
        self._keys = list(self.index)
        self.unmatched: set[str] = set()

    def __call__(self, name) -> str | None:
        if name is None or (isinstance(name, float) and pd.isna(name)):
            return None
        raw = str(name).strip()
        if raw.upper() in self.codes:
            return raw.upper()
        if raw.upper() in CODE_FIX:
            return CODE_FIX[raw.upper()]
        n = norm(raw)
        if n in self.index:
            return self.index[n]
        n2 = _STRIP.sub(" ", n)
        n2 = re.sub(r"\s+", " ", n2).strip()
        if n2 in self.index:
            return self.index[n2]
        m = difflib.get_close_matches(n, self._keys, n=1, cutoff=0.88)
        if m:
            return self.index[m[0]]
        self.unmatched.add(raw)
        return None
