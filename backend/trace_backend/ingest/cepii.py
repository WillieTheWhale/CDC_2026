# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""CEPII GeoDist bilateral distances and contiguity (Mayer and Zignago 2011).

Codes are from 2004; remapped to current World Bank ISO3. Pairs missing from GeoDist (e.g. South Sudan,
Kosovo, Montenegro, Curacao) get great-circle distance between World Bank capital coordinates and a
small documented contiguity list.
"""
from __future__ import annotations

import io
import zipfile

import numpy as np
import pandas as pd

from .. import config
from .http import fetch
from .names import CODE_FIX

URL = "https://www.cepii.fr/distance/dist_cepii.zip"
PATH = config.RAW / "cepii" / "dist_cepii.zip"
# land borders for states that post-date GeoDist (2004)
EXTRA_CONTIG = [("SSD", x) for x in ["SDN", "ETH", "KEN", "UGA", "COD", "CAF"]] + \
    [("MNE", x) for x in ["SRB", "XKX", "ALB", "BIH", "HRV"]] + [("XKX", x) for x in ["SRB", "ALB", "MKD"]] + \
    [("SXM", "MAF")]


def download(refresh: bool = False) -> str:
    return fetch(URL, PATH, refresh=refresh)


def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def load(countries: pd.DataFrame) -> pd.DataFrame:
    z = zipfile.ZipFile(PATH)
    name = [n for n in z.namelist() if n.lower().endswith((".xls", ".xlsx", ".dta"))][0]
    raw = z.read(name)
    d = pd.read_stata(io.BytesIO(raw)) if name.endswith(".dta") else pd.read_excel(io.BytesIO(raw), engine="calamine")
    d = d.rename(columns={"iso_o": "from_iso3", "iso_d": "to_iso3"})
    for c in ("from_iso3", "to_iso3"):
        d[c] = d[c].astype(str).str.upper().replace(CODE_FIX)
    d = d[["from_iso3", "to_iso3", "dist", "contig", "comlang_off", "colony"]]
    d = d.groupby(["from_iso3", "to_iso3"], as_index=False).first()

    codes = sorted(countries["iso3"])
    full = pd.MultiIndex.from_product([codes, codes], names=["from_iso3", "to_iso3"]).to_frame(index=False)
    full = full[full["from_iso3"] != full["to_iso3"]]
    out = full.merge(d, on=["from_iso3", "to_iso3"], how="left")
    ll = countries.set_index("iso3")[["lat", "lon"]]
    miss = out["dist"].isna()
    a, b = ll.reindex(out.loc[miss, "from_iso3"]).values, ll.reindex(out.loc[miss, "to_iso3"]).values
    out.loc[miss, "dist"] = haversine(a[:, 0], a[:, 1], b[:, 0], b[:, 1])
    out["dist_imputed"] = miss
    out[["contig", "comlang_off", "colony"]] = out[["contig", "comlang_off", "colony"]].fillna(0).astype(int)
    extra = {(x, y) for x, y in EXTRA_CONTIG} | {(y, x) for x, y in EXTRA_CONTIG}
    out.loc[out[["from_iso3", "to_iso3"]].apply(tuple, axis=1).isin(extra), "contig"] = 1
    return out.dropna(subset=["dist"]).reset_index(drop=True)
