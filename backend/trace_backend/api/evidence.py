# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Evidence drilldown API (data_collection/schema_v2.md): value -> formula -> exact input rows -> source.

Reads the v2 tables wherever they live: the canonical archive (attached as `archive`) locally, or the slim copies
that scripts/build_vercel.py puts in the derived DB for the deploy (derived wins, as in db.read_table).

Design boundary: these are published source observations and TRACE's small retrospective research layer. Nothing
here ranks enforcement or monitoring, and modelled health estimates are labelled as modelled, never as observed.
"""
from __future__ import annotations

import base64
import json
import re
import sqlite3

from fastapi import APIRouter, HTTPException, Query

from .. import db
from ..sources import SOURCES

router = APIRouter()

SUPPORT_BASIS = "Linked input rows (each aggregate plus its underlying source rows), not independent countries."
OVERDOSE_LABEL = ("12-month-ending provisional; periods overlap and must not be summed; drug classes overlap; "
                  "suppressed values are null")
NATURE = {"M": "Officially modelled estimate (UN SDG nature code M), not a country-reported observation",
          "C": "Country-reported data (UN SDG nature code C)"}
ESTIMATE = {"published_estimate": "Published estimate (government/UNODC estimate, may be adjusted); "
                                  "not a direct survey observation",
            "source_reported": "Source-reported national survey value"}
PRIMARY_ROLE = {"seizure_edition_revision_pct": "newest", "cocaine_seizure_next_homicide": "outcome"}
REVISION_LABEL = ("Source-edition revision: the same country, year and drug was published with a different value in a "
                  "later annex edition. This is a reporting revision, not a real-world change in flows.")
DRUG_ALIAS = {"meth": "methamphetamine"}


# ------------------------------------------------------------------ helpers
def _bad(message: str):
    raise HTTPException(status_code=400, detail={"code": "invalid_request", "message": message})


def _missing(code: str, message: str):
    raise HTTPException(status_code=404, detail={"code": code, "message": message})


def _rows(sql: str, params: tuple | list = ()) -> list[dict]:
    """Run `sql` with `{table}` placeholders resolved to whichever schema (derived first, then archive) holds it."""
    with db.connect(read_only=True) as con:
        con.row_factory = sqlite3.Row

        def resolve(m: re.Match) -> str:
            schema = db.schema_of(con, m.group(1))
            if schema is None:
                raise HTTPException(status_code=503, detail={
                    "code": "evidence_unavailable", "message": f"Evidence table {m.group(1)} is not available."})
            return f'{schema}."{m.group(1)}"'

        return [dict(r) for r in con.execute(re.sub(r"\{(\w+)\}", resolve, sql), tuple(params))]


def available() -> bool:
    return db.table_exists("research_values")


def _envelope(data, *source_ids: str, notes: list[str] | None = None, **extra) -> dict:
    from .app import envelope
    body = envelope(data, *source_ids, notes=notes)
    body["meta"].update(extra)
    return body


def _cursor_encode(fkey: str, last: list) -> str:
    return base64.urlsafe_b64encode(json.dumps([fkey, *last]).encode()).decode().rstrip("=")


def _cursor_decode(cursor: str | None, fkey: str, n: int) -> list | None:
    if not cursor:
        return None
    try:
        v = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode())
        assert isinstance(v, list) and len(v) == n + 1 and v[0] == fkey
    except Exception:
        _bad("cursor does not match these filters")
    return v[1:]


def _flags(s: str | None) -> list[str]:
    return [f for f in re.split(r"[;,|\s]+", s or "") if f]


def _file(url: str | None) -> str:
    return (url or "").rsplit("/", 1)[-1].split("?", 1)[0]


def _row_key(source_key: str) -> tuple[str, str, int]:
    """`unodc_seizure_observations:source_id|sheet|row_no` -> (source_id, sheet, row_no)."""
    sid, rest = source_key.split(":", 1)[1].split("|", 1)
    sheet, row = rest.rsplit("|", 1)
    return sid, sheet, int(row)


def _market_label(label: str | None, code: str, substance: str, form: str | None, level: str | None) -> str:
    out = f"{label or code}: {substance}"
    if form and form != "unspecified":
        out += f" ({form})"
    return out + (f", {level}" if level else "")


def _in(n: int) -> str:
    return ",".join("?" * n)


# ------------------------------------------------------------------ list
_LIST_SQL = """
SELECT * FROM (
  SELECT 'research' AS kind, v.metric_id AS id, v.metric_id AS sk, v.metric_key, d.label, v.iso3, v.drug, v.year,
         v.value, d.unit
  FROM {research_values} v JOIN {research_metric_definitions} d USING (metric_key)
  UNION ALL
  SELECT 'market', CAST(m.derived_id AS TEXT), printf('%012d', m.derived_id), m.metric_code,
         coalesce(md.label, m.metric_code) || ': ' || m.substance
           || CASE WHEN m.form IS NOT NULL AND m.form <> 'unspecified' THEN ' (' || m.form || ')' ELSE '' END
           || CASE WHEN m.market_level IS NOT NULL THEN ', ' || m.market_level ELSE '' END,
         m.iso3, m.substance, m.year, m.value, m.unit
  FROM {market_derived} m LEFT JOIN {market_metric_definitions} md ON md.metric_code = m.metric_code
) WHERE 1=1"""


@router.get("/api/evidence/values")
def list_values(iso3: str | None = Query(None, pattern="^[A-Za-z]{3}$"), drug: str | None = Query(None, max_length=60),
                year: int | None = None, kind: str | None = Query(None, pattern="^(research|market)$"),
                limit: int = Query(100, ge=1, le=500), cursor: str | None = Query(None, max_length=1024)):
    """Drillable values (research metric_ids and market derived_ids), ordered by kind then id."""
    where, params = "", []
    if iso3:
        where += " AND iso3 = ?"
        params.append(iso3.upper())
    if drug:
        d = drug.strip().lower()
        where += " AND ((kind = 'research' AND drug = ?) OR (kind = 'market' AND lower(drug) LIKE ?))"
        params += [d, f"%{DRUG_ALIAS.get(d, d)}%"]
    if year is not None:
        where += " AND year = ?"
        params.append(year)
    if kind:
        where += " AND kind = ?"
        params.append(kind)
    fkey = json.dumps([iso3 and iso3.upper(), drug and drug.strip().lower(), year, kind])
    total = _rows(f"SELECT count(*) AS n FROM ({_LIST_SQL}{where})", params)[0]["n"]
    last = _cursor_decode(cursor, fkey, 2)
    page_where = where + (" AND (kind, sk) > (?, ?)" if last else "")
    rows = _rows(f"{_LIST_SQL}{page_where} ORDER BY kind, sk LIMIT ?", [*params, *(last or []), limit + 1])
    nxt = _cursor_encode(fkey, [rows[limit - 1]["kind"], rows[limit - 1]["sk"]]) if len(rows) > limit else None
    items = [{k: r[k] for k in ("id", "kind", "metric_key", "label", "iso3", "drug", "year", "value", "unit")}
             for r in rows[:limit]]
    return _envelope({"values": items}, "trace_research_v2", "unodc_wdr_editions", "wb_wdi",
                     notes=["Research values are TRACE's retrospective derivations; market values are exact-product "
                            "UNODC price/purity derivations. Open /api/evidence/value/{id} for formula and inputs."],
                     total=total, next_cursor=nxt)


# ------------------------------------------------------------------ research drilldown
def _seizure_sources() -> dict[str, dict]:
    try:
        return {r["source_id"]: r for r in _rows("SELECT source_id, url, sha256, edition, citation FROM {unodc_sources}")}
    except HTTPException:
        return {}


def _enrich_research_inputs(inputs: list[dict]) -> None:
    annex = [i for i in inputs if i["source_table"] == "seizures_annex"]
    obs = [i for i in inputs if i["source_table"] == "unodc_seizure_observations"]
    wb = [i for i in inputs if i["source_table"] == "wb_indicators"]
    usrc = _seizure_sources()
    for i in annex + obs:
        s = usrc.get(i["source_id"])
        i["source_title"] = (f"UNODC World Drug Report {s['edition']} statistical annex: {_file(s['url'])}" if s
                             else f"UNODC World Drug Report statistical annex ({i['source_id']})")
        if s:
            i["source_checksum"] = s["sha256"]
    for i in annex:  # key: iso3|year|drug|edition
        iso3, year, drug, edition = i["source_key"].split(":", 1)[1].split("|")
        eds = _rows("SELECT edition, kg, source AS source_id FROM {seizures_annex} WHERE iso3 = ? AND year = ? "
                    "AND drug = ? ORDER BY edition", (iso3, int(year), drug))
        kgs = {round(e["kg"], 6) for e in eds if e["kg"] is not None}
        i["editions"] = eds
        i["edition"] = int(edition)
        i["revised_between_editions"] = len(kgs) > 1
        i["revision_label"] = REVISION_LABEL if len(kgs) > 1 else None
    if obs:  # key: source_id|sheet|row_no; original cells in unodc_cells
        keys = [_row_key(i["source_key"]) for i in obs]
        cond = " OR ".join(["(source_id = ? AND sheet = ? AND row_no = ?)"] * len(keys))
        flat = [x for k in keys for x in k]
        found = {(o["source_id"], o["sheet"], o["row_no"]): o for o in _rows(
            "SELECT source_id, sheet, row_no, iso3, country, year, drug_group, drug_raw, quantity, unit, drug, "
            f"kg_trace_equivalent, notes FROM {{unodc_seizure_observations}} WHERE {cond}", flat)}
        cells: dict[tuple, list] = {}
        for c in _rows("SELECT source_id, sheet, row_no, col_no, value_text, value_number, value_type, italic "
                       f"FROM {{unodc_cells}} WHERE {cond} ORDER BY source_id, sheet, row_no, col_no", flat):
            cells.setdefault((c["source_id"], c["sheet"], c["row_no"]), []).append(
                {k: c[k] for k in ("col_no", "value_text", "value_number", "value_type")} | {"italic": bool(c["italic"])})
        for i, k in zip(obs, keys, strict=True):
            o = found.get(k)
            if o and o.get("notes"):
                try:
                    o["notes"] = json.loads(o["notes"])
                except ValueError:
                    pass
            i["source_row"] = {"source_id": k[0], "sheet": k[1], "row_no": k[2], "observation": o,
                               "cells": cells.get(k, [])}
    for i in wb:  # key: iso3|year|code|source; source_id is the wb_downloads request_id
        iso3, year, code, src = i["source_key"].split(":", 1)[1].split("|")
        m = re.search(r"lastupdated=([0-9-]+)", i["transform"] or "")
        dl = _rows("SELECT request_id, url, retrieved_at, sha256, last_modified FROM {wb_downloads} "
                   "WHERE request_id = ?", (i["source_id"],))
        meta = _rows("SELECT name FROM {wb_indicator_meta} WHERE code = ?", (code,))
        i["source_title"] = (f"World Bank {'WDI' if src == '2' else 'WGI' if src == '3' else 'source ' + src}: "
                             f"{meta[0]['name'] if meta else code}")
        i["world_bank"] = {"indicator_code": code, "source_id": int(src), "iso3": iso3, "year": int(year),
                           "lastupdated": m.group(1) if m else None,
                           "lastupdated_note": "World Bank dataset lastupdated; not asserted as a publication year.",
                           "download_url": dl[0]["url"] if dl else i["source_url"],
                           "request_id": i["source_id"], "retrieved_at": dl[0]["retrieved_at"] if dl else None,
                           "sha256": dl[0]["sha256"] if dl else None}


def _research(metric_id: str) -> dict | None:
    v = _rows("SELECT v.*, d.version, d.label, d.unit, d.formula, d.selection_rule, d.interpretation "
              "FROM {research_values} v JOIN {research_metric_definitions} d USING (metric_key) WHERE v.metric_id = ?",
              (metric_id,))
    if not v:
        return None
    v = v[0]
    inputs = _rows("SELECT role, source_table, source_key, source_id, source_url, publication_year, observation_year, "
                   "input_value, input_unit, transform FROM {research_value_inputs} WHERE metric_id = ? "
                   "ORDER BY role, source_table, source_key", (metric_id,))
    _enrich_research_inputs(inputs)
    primary = next((i for i in inputs if i["role"] == PRIMARY_ROLE.get(v["metric_key"])), inputs[0] if inputs else {})
    flags = _flags(v["quality_flags"])
    revised = any(i.get("revised_between_editions") for i in inputs)
    if v["metric_key"] == "seizure_edition_revision_pct":
        flags.append("source_edition_revision")
    elif revised:
        flags.append("seizure_input_revised_between_editions")
    caveat = v["interpretation"]
    out = {
        "id": v["metric_id"], "kind": "research", "metric_key": v["metric_key"], "label": v["label"],
        "iso3": v["iso3"], "drug": v["drug"], "year": v["year"], "value": v["value"], "unit": v["unit"],
        "numerator": v["numerator"], "denominator": v["denominator"],
        "formula": {"expression": v["formula"], "version": v["version"], "selection_rule": v["selection_rule"],
                    "interpretation": v["interpretation"]},
        "support_count": v["support_count"], "support_count_basis": SUPPORT_BASIS,
        "observation_year": primary.get("observation_year", v["year"]),
        "source_publication_year": primary.get("publication_year"),
        "first_publication_year": v["first_publication_year"], "last_publication_year": v["last_publication_year"],
        "source_title": primary.get("source_title"), "source_url": primary.get("source_url"),
        "source_key": primary.get("source_key"), "quality_flags": flags, "caveat": caveat,
        "revision_label": REVISION_LABEL if v["metric_key"] == "seizure_edition_revision_pct" or revised else None,
        "inputs": inputs, "market": None, "regression_sample": None,
    }
    if v["metric_key"] == "cocaine_seizure_next_homicide":
        s = _rows("SELECT sample_id, seizure_year, outcome_year, log1p_seizure_kg, homicide_per_100k "
                  "FROM {research_regression_samples} WHERE metric_id = ?", (metric_id,))
        out["regression_sample"] = s[0] if s else None
    return out


# ------------------------------------------------------------------ market drilldown
def _market(derived_id: int) -> dict | None:
    d = _rows("SELECT m.*, md.label, md.eligibility, md.interpretation, md.cautions FROM {market_derived} m "
              "LEFT JOIN {market_metric_definitions} md ON md.metric_code = m.metric_code WHERE m.derived_id = ?",
              (derived_id,))
    if not d:
        return None
    d = d[0]
    raw = json.loads(d["inputs_json"] or "{}")
    roles = {k[:-len("_observation_id")]: int(v) for k, v in raw.items() if k.endswith("_observation_id")}
    obs = {o["observation_id"]: o for o in _rows(
        f"SELECT * FROM {{market_observations}} WHERE observation_id IN ({_in(len(roles))})", list(roles.values()))
    } if roles else {}
    srcs = {s["source_id"]: s for s in _rows("SELECT * FROM {market_sources}")}
    inputs = []
    for role, oid in roles.items():
        o = obs.get(oid) or {}
        s = srcs.get(o.get("source_id") or d["source_id"], {})
        num = next((v for k, v in raw.items() if k.startswith(role + "_") and k != f"{role}_observation_id"), None)
        unit = next((k[len(role) + 1:] for k in raw if k.startswith(role + "_") and k != f"{role}_observation_id"), None)
        cells = _rows("SELECT col_no, value_text, value_number, value_type, italic FROM {market_cells} "
                      "WHERE source_id = ? AND sheet = ? AND row_no = ? ORDER BY col_no",
                      (o.get("source_id"), o.get("sheet"), o.get("row_no"))) if o else []
        for c in cells:
            c["italic"] = bool(c["italic"])
        inputs.append({
            "role": role, "source_table": "market_observations",
            "source_key": f"market_observations:{oid}",
            "source_id": o.get("source_id"), "source_url": s.get("url"), "publication_year": s.get("edition"),
            "observation_year": o.get("year"), "input_value": num, "input_unit": unit,
            "transform": (f"{o.get('original_value')} {o.get('original_unit')} -> {o.get('normalized_value')} "
                          f"{o.get('normalized_unit')}") if o else None,
            "source_title": f"{s.get('citation')}, {s.get('edition')} edition: {_file(s.get('url'))}" if s else None,
            "source_checksum": s.get("sha256"),
            "source_row": {"source_id": o.get("source_id"), "sheet": o.get("sheet"), "row_no": o.get("row_no"),
                           "observation": ({**o, "publisher_estimate": bool(o.get("publisher_estimate"))} if o else None),
                           "cells": cells} if o else None,
        })
    s = srcs.get(d["source_id"], {})
    flags = [f"{i['role']}_publisher_estimate" for i in inputs
             if i["source_row"] and i["source_row"]["observation"]["publisher_estimate"]]
    if d["metric_code"] == "purity_adjusted_price_usd_per_pure_g":
        flags.append("price_and_purity_may_be_different_samples")
    caveat = " ".join(x for x in (d["interpretation"], d["cautions"]) if x)
    return {
        "id": str(d["derived_id"]), "kind": "market", "metric_key": d["metric_code"],
        "label": _market_label(d["label"], d["metric_code"], d["substance"], d["form"], d["market_level"]),
        "iso3": d["iso3"], "drug": d["substance"], "year": d["year"], "value": d["value"], "unit": d["unit"],
        "numerator": None, "denominator": None,
        "formula": {"expression": d["formula"], "version": None, "selection_rule": d["eligibility"],
                    "interpretation": d["interpretation"]},
        "support_count": len(inputs), "support_count_basis": SUPPORT_BASIS,
        "observation_year": d["year"], "source_publication_year": s.get("edition"),
        "first_publication_year": s.get("edition"), "last_publication_year": s.get("edition"),
        "source_title": f"{s.get('citation')}, {s.get('edition')} edition: {_file(s.get('url'))}" if s else None,
        "source_url": s.get("url"), "source_key": f"market_derived:{d['derived_id']}", "quality_flags": flags,
        "caveat": caveat, "revision_label": None, "inputs": inputs,
        "market": {"substance": d["substance"], "form": d["form"], "market_level": d["market_level"],
                   "source": {"source_id": d["source_id"], "url": s.get("url"), "edition": s.get("edition"),
                              "sha256": s.get("sha256"), "retrieved_at": s.get("retrieved_at"),
                              "citation": s.get("citation"), "license_note": s.get("license_note")}},
        "regression_sample": None,
    }


@router.get("/api/evidence/value/{value_id}")
def get_value(value_id: str):
    """Full drilldown for a research metric_id or a market derived_id."""
    if len(value_id) > 64 or not re.fullmatch(r"[A-Za-z0-9_-]+", value_id):
        _missing("unknown_value", f"{value_id!r} is not a research metric_id or market derived_id.")
    out = _research(value_id)
    if out is None and value_id.isdigit():
        out = _market(int(value_id))
    if out is None:
        _missing("unknown_value", f"{value_id!r} is not a research metric_id or market derived_id.")
    notes = [SUPPORT_BASIS, "source_publication_year is the source edition, never the TRACE collection date; "
             "null where the source does not state one."]
    if out["kind"] == "research":
        srcs = ("trace_research_v2", "unodc_wdr_editions") + (("wb_wdi",) if out["metric_key"] ==
                                                              "cocaine_seizure_next_homicide" else ())
        notes.append("National seizures show where a seizure was recorded, not an observed route.")
    else:
        srcs = ("unodc_wdr_editions",)
        notes.append("Market values are descriptive price contrasts, not margins, route gradients or corridor signals.")
    return _envelope(out, *srcs, notes=notes)


# ------------------------------------------------------------------ health
@router.get("/api/evidence/health/{iso3}")
def get_health(iso3: str, reference_period: str | None = Query(None, pattern="^(past_year|past_month|lifetime)$"),
               substance: str | None = Query(None, max_length=80), limit: int = Query(500, ge=1, le=5000)):
    """Drug-use prevalence (UNODC annex 1.2/1.4) and SDG 3.5.1 treatment coverage (modelled M vs country C)."""
    if not re.fullmatch(r"[A-Za-z]{3}", iso3):
        _missing("unknown_country", f"{iso3} is not an ISO3 code.")
    iso3 = iso3.upper()
    pw, pp = "p.iso3 = ?", [iso3]
    if reference_period:
        pw += " AND p.reference_period = ?"
        pp.append(reference_period)
    if substance:
        pw += " AND lower(p.substance) = ?"
        pp.append(substance.strip().lower())
    ptotal = _rows(f"SELECT count(*) AS n FROM {{health_prevalence}} p WHERE {pw}", pp)[0]["n"]
    prev = _rows("SELECT p.*, s.title, s.url, s.edition_year, s.publisher FROM {health_prevalence} p "
                 f"LEFT JOIN {{health_sources}} s USING (source_id) WHERE {pw} "
                 "ORDER BY p.year, p.substance, p.reference_period, p.age_group, p.sex, p.source_id, p.row_no, "
                 "p.cell_no LIMIT ?", [*pp, limit])
    cw, cp = "c.iso3 = ?", [iso3]
    if substance:
        cw += " AND lower(c.substance_group) = ?"
        cp.append(substance.strip().lower())
    ctotal = _rows(f"SELECT count(*) AS n FROM {{health_treatment_coverage}} c WHERE {cw}", cp)[0]["n"]
    cov = _rows("SELECT c.*, s.title, s.url, s.edition_year, s.publisher FROM {health_treatment_coverage} c "
                f"LEFT JOIN {{health_sources}} s USING (source_id) WHERE {cw} "
                "ORDER BY c.year, c.substance_group, c.sex, c.nature_code LIMIT ?", [*cp, limit])
    if not ptotal and not ctotal:
        _missing("no_health_evidence", f"No prevalence or treatment coverage rows for {iso3}.")

    def src(r):
        return {"source_id": r["source_id"], "title": r["title"], "publisher": r["publisher"], "url": r["url"],
                "edition_year": r["edition_year"]}

    prevalence = [{
        "substance": r["substance"], "substance_detail": r["substance_detail"] or None, "year": r["year"],
        "year_text": r["year_text"], "reference_period": r["reference_period"], "population": r["population"],
        "age_group": r["age_group"], "sex": r["sex"], "value_pct": r["value_pct"], "low_pct": r["low_pct"],
        "high_pct": r["high_pct"], "estimate_status": r["estimate_status"],
        "estimate_label": ESTIMATE.get(r["estimate_status"], r["estimate_status"]),
        "method": r["source_method"] or None, "attribution": r["source_attribution"] or None,
        "adjustment_note": r["adjustment_note"] or None, "notes": r["notes"] or None, "source": src(r),
        "source_row": {"sheet": r["sheet"], "row_no": r["row_no"], "cell_no": r["cell_no"]},
    } for r in prev]

    def footnotes(s):
        try:
            return [f for f in json.loads(s or "[]") if f]
        except ValueError:
            return [s] if s else []

    coverage = [{
        "year": r["year"], "substance_group": r["substance_group"], "sex": r["sex"], "value_pct": r["value_pct"],
        "lower_pct": r["lower_pct"], "upper_pct": r["upper_pct"], "nature_code": r["nature_code"],
        "nature_label": NATURE.get(r["nature_code"], r["nature_meaning"]), "modelled": r["nature_code"] == "M",
        "attribution": r["source_attribution"] or None, "footnotes": footnotes(r["footnotes_json"]),
        "source": src(r), "source_row_no": r["source_row_no"],
    } for r in cov]
    return _envelope({
        "iso3": iso3,
        "prevalence": {"total": ptotal, "rows": prevalence,
                       "label": "Source-native prevalence observations; populations, ages, methods and reference "
                                "periods differ and are not directly comparable. Not a complete country ranking."},
        "treatment_coverage": {"total": ctotal, "rows": coverage,
                               "label": "UN SDG 3.5.1 coverage of treatment for drug use disorders (%). "
                                        "nature_code M = officially modelled estimate; C = country-reported data.",
                               "nature_labels": NATURE},
    }, "unodc_wdr_health", "un_sdg_351",
        notes=["Modelled coverage (nature M) is an estimate, not an observed count.",
               "The 2024 adult prevalence data are sparse and are not a complete country ranking."])


# ------------------------------------------------------------------ overdose
@router.get("/api/evidence/overdose")
def get_overdose(state: str = Query("US", pattern="^[A-Za-z]{2}$"), indicator: str | None = Query(None, max_length=120),
                 from_year: int | None = None, to_year: int | None = None, limit: int = Query(500, ge=1, le=5000),
                 cursor: str | None = Query(None, max_length=1024)):
    """CDC provisional 12-month-ending overdose deaths for one jurisdiction; exact CDC indicator labels."""
    state = state.upper()
    inds = [r["indicator"] for r in _rows("SELECT DISTINCT indicator FROM {health_cdc_overdose} WHERE state = ? "
                                          "ORDER BY indicator", (state,))]
    if not inds:
        _missing("unknown_state", f"No CDC provisional series for jurisdiction {state}.")
    if indicator is not None and indicator not in inds:
        _missing("unknown_indicator", f"{indicator!r} is not a CDC indicator for {state}. Available: {inds}")
    w, p = "state = ?", [state]
    if indicator is not None:
        w += " AND indicator = ?"
        p.append(indicator)
    if from_year is not None:
        w += " AND end_year >= ?"
        p.append(from_year)
    if to_year is not None:
        w += " AND end_year <= ?"
        p.append(to_year)
    fkey = json.dumps([state, indicator, from_year, to_year])
    total = _rows(f"SELECT count(*) AS n FROM {{health_cdc_overdose}} WHERE {w}", p)[0]["n"]
    last = _cursor_decode(cursor, fkey, 3)
    pw = w + (" AND (end_year, end_month, indicator) > (?, ?, ?)" if last else "")
    rows = _rows("SELECT state, state_name, end_year, end_month, period, indicator, metric_kind, value_unit, "
                 "reported_value, predicted_value, percent_complete, percent_pending_investigation, footnote, "
                 f"footnote_symbol, suppressed_or_unavailable FROM {{health_cdc_overdose}} WHERE {pw} "
                 "ORDER BY end_year, end_month, indicator LIMIT ?", [*p, *(last or []), limit + 1])
    nxt = (_cursor_encode(fkey, [rows[limit - 1]["end_year"], rows[limit - 1]["end_month"], rows[limit - 1]["indicator"]])
           if len(rows) > limit else None)
    series = []
    for r in rows[:limit]:
        sup = bool(r["suppressed_or_unavailable"])
        series.append({
            "period_end": f"{r['end_year']:04d}-{r['end_month']:02d}", "end_year": r["end_year"],
            "end_month": r["end_month"], "period_kind": r["period"], "indicator": r["indicator"],
            "metric_kind": r["metric_kind"], "unit": r["value_unit"],
            "reported_value": None if sup else r["reported_value"],
            "predicted_value": None if sup else r["predicted_value"],
            "percent_complete": r["percent_complete"], "percent_pending_investigation": r["percent_pending_investigation"],
            "suppressed": sup, "status": "provisional", "footnote": r["footnote"] or None,
            "footnote_symbol": r["footnote_symbol"] or None,
        })
    src = SOURCES["cdc_vsrr_overdose"]
    return _envelope({"state": state, "state_name": rows[0]["state_name"] if rows else None, "label": OVERDOSE_LABEL,
                      "indicators": inds, "source_url": src["url"], "source_publication_year": None,
                      "rows": series}, "cdc_vsrr_overdose",
                     notes=[OVERDOSE_LABEL + ".", "Drug-class counts overlap (one death can involve several drugs); "
                            "never add classes into an all-overdose total. 'Synthetic opioids' (T40.4) is broader "
                            "than fentanyl alone.", "Reported and predicted (adjusted) values are distinct."],
                     total=total, next_cursor=nxt)


# ------------------------------------------------------------------ research model
@router.get("/api/evidence/research-model")
def get_research_model():
    """The one prespecified retrospective model (cocaine seizures vs next-year homicide)."""
    m = _rows("SELECT * FROM {research_model_results}")
    if not m:
        _missing("no_model", "No research model result available.")
    m = m[0]
    n = _rows("SELECT count(*) AS n FROM {research_regression_samples}")[0]["n"]
    return _envelope({**m, "metric_key": "cocaine_seizure_next_homicide", "sample_rows": n,
                      "interpretation": "Retrospective ecological association only: not route validation, not a "
                                        "causal estimate and not a prospective forecast test."},
                     "trace_research_v2", "unodc_wdr_editions", "wb_wdi",
                     notes=["Seizures reflect enforcement and reporting, not trade volume or route exposure; homicide "
                            "is general-population, not drug-attributed."])
