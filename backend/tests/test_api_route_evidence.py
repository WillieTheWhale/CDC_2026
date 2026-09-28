# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Route evidence API: filters, bbox, keyset paging, 404s, provenance, and /api/routes edge linkage."""
import json
import re

from trace_backend import config
from trace_backend.api.route_evidence import dataset

TS = config.REPO / "frontend" / "lib" / "route-evidence.ts"


def _all(client, **params) -> list[dict]:
    out, cursor = [], None
    while True:
        body = client.get("/api/route-evidence", params={**params, **({"cursor": cursor} if cursor else {})}).json()
        out += body["data"]
        cursor = body["meta"]["next_cursor"]
        if not cursor:
            assert len(out) == body["meta"]["total"]
            return out


def test_list_shape_and_sources(client):
    body = client.get("/api/route-evidence").json()
    assert body["meta"]["total"] == len(dataset()["records"]) and len(body["data"]) == 100
    assert body["meta"]["sources"] and body["meta"]["notes"]
    for r in dataset()["records"]:
        assert re.match(r"^https?://", r["source"]["url"]), r["id"]
        assert r["pair_type"] in ("direct_reported_pair", "interpreted_corridor", "narrative_context")
        assert r["drug"] in ("cocaine", "heroin", "meth", "cannabis")
        assert r["period"] is None or (len(r["period"]) == 2 and r["period"][0] <= r["period"][1])
        assert {"id", "drug", "from", "to", "basis", "source", "source_locator", "geometry_precision", "caveat",
                "supports_edge_ids"} <= r.keys()


def test_direct_pairs_match_frontend():
    direct = [r for r in dataset()["records"] if r["pair_type"] == "direct_reported_pair"]
    if TS.exists():
        rows = re.findall(r'^\s*\["(\w+)", "([A-Z]{3})", "([A-Z]{3})", "([^"]+)"', TS.read_text(encoding="utf-8"), re.M)
        assert {r["id"] for r in direct} == {f"{d}:{a}:{b}:{s}" for d, a, b, s in rows}
        assert len(direct) == len(rows)
    assert len(direct) == 51
    assert all(r["geometry_precision"] == "country pair" for r in direct)


def test_paging_complete_and_stable(client):
    a = _all(client, limit=37)
    assert [r["id"] for r in a] == [r["id"] for r in _all(client, limit=250)]
    assert len({r["id"] for r in a}) == len(a) == len(dataset()["records"])


def test_filters(client):
    for p in ("direct_reported_pair", "interpreted_corridor", "narrative_context"):
        rows = _all(client, pair_type=p)
        assert rows and all(r["pair_type"] == p for r in rows)
    rows = _all(client, drug="heroin", iso3="tur")
    assert rows and all(r["drug"] == "heroin" and "TUR" in (r["from"], r["to"]) for r in rows)
    rows = _all(client, **{"from": "COL", "to": "ECU"})
    assert {r["pair_type"] for r in rows} == {"direct_reported_pair", "interpreted_corridor"}
    rows = _all(client, basis="reported seizure origin/destination")
    assert rows and all(r["basis"] == "reported seizure origin/destination" for r in rows)
    assert client.get("/api/route-evidence", params={"drug": "lsd"}).status_code == 422
    assert client.get("/api/route-evidence", params={"limit": 251}).status_code == 422


def test_bbox(client):
    coords = {c["iso3"]: (c["lon"], c["lat"]) for c in client.get("/api/countries").json()["data"]}
    europe = _all(client, bbox="-12,35,30,60")
    assert europe and all(any(-12 <= coords[i][0] <= 30 and 35 <= coords[i][1] <= 60 for i in (r["from"], r["to"])
                                  if i in coords) for r in europe)
    assert not any(r["pair_type"] == "narrative_context" for r in europe)
    wrap = _all(client, bbox="170,-60,300,40")  # antimeridian: Pacific plus the Americas
    assert any("COL" in (r["from"], r["to"]) for r in wrap)
    assert client.get("/api/route-evidence", params={"bbox": "1,2,3"}).status_code == 400


def test_cursor_mismatch(client):
    cur = client.get("/api/route-evidence", params={"limit": 5}).json()["meta"]["next_cursor"]
    assert client.get("/api/route-evidence", params={"limit": 5, "drug": "meth", "cursor": cur}).status_code == 400
    assert client.get("/api/route-evidence", params={"cursor": "garbage"}).status_code == 400


def test_item_and_404(client):
    rid = "cocaine:COL:ECU:unodc-cocaine-2023"
    r = client.get(f"/api/route-evidence/{rid}").json()["data"]
    assert r["id"] == rid and r["period"] == [2019, 2020] and r["supports_edge_ids"] == ["cocaine:COL:ECU"]
    resp = client.get("/api/route-evidence/nope:XXX:YYY:none")
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "unknown_evidence"


def test_sources(client):
    srcs = client.get("/api/route-evidence/sources").json()["data"]
    ids = {s["id"] for s in srcs}
    assert {r["source"]["id"] for r in dataset()["records"]} == ids
    assert all(re.match(r"^https?://", s["url"]) for s in srcs)


def test_routes_linkage(client):
    ids = set(dataset()["by_id"])
    for mode in ("observed", "predicted"):
        body = client.get("/api/routes", params={"mode": mode}).json()
        edges = body["data"]["edges"]
        assert edges and all(e["kg_basis"] == "allocated_seizure_scale" for e in edges)
        assert all(set(e["evidence_ids"]) <= ids for e in edges)
        assert any(e["evidence_ids"] for e in edges)
        assert any("pair-level" in n for n in body["meta"]["notes"])
    e = next(e for e in client.get("/api/routes", params={"drug": "cocaine"}).json()["data"]["edges"]
             if e["id"] == "cocaine:COL:ECU")
    kinds = [dataset()["by_id"][i]["pair_type"] for i in e["evidence_ids"]]
    assert kinds[0] == "direct_reported_pair" and "interpreted_corridor" in kinds


def test_country_linkage(client):
    d = client.get("/api/country/COL").json()["data"]["routes"]
    edges = d["inbound"] + d["outbound"]
    assert edges and all(e["kg_basis"] == "allocated_seizure_scale" and isinstance(e["evidence_ids"], list)
                         for e in edges)


def test_every_corridor_citation_has_a_url():
    from trace_backend.api.route_evidence import CITATIONS
    assert all(url and url.startswith("https://") for *_, url in CITATIONS.values())


MOJIBAKE = ("â€", "â\u0080", "Ã")  # UTF-8 dashes/quotes/accents decoded as cp1252 or latin-1


def _text_fields(r: dict) -> list[str]:
    s = r.get("source") or {}
    return [v for v in (r.get("title"), s.get("title"), r.get("source_locator"), r.get("caveat"), r.get("basis"),
                        r.get("original_excerpt"), s.get("publisher"), r.get("publisher")) if isinstance(v, str)]


def test_no_mojibake_in_titles_locators_caveats(client):
    records = _all(client, limit=250)
    sources = client.get("/api/route-evidence/sources").json()["data"]
    fields = [t for r in records + sources for t in _text_fields(r)]
    assert any("–" in t or "—" in t for t in fields)  # the dashes that used to garble are present
    assert not [t for t in fields if any(m in t for m in MOJIBAKE)]


def test_route_evidence_decodes_under_any_client_charset(client):
    """Titles carry en/em dashes; the body is ASCII-escaped with an explicit charset, so a client that falls back
    to latin-1 or cp1252 without a charset (e.g. Windows PowerShell 5.1) reads the same text as a UTF-8 one."""
    for path in ("/api/route-evidence/sources", "/api/route-evidence?limit=250",
                 "/api/route-evidence/cocaine:COL:ECU:unodc-cocaine-2023"):
        r = client.get(path)
        assert r.status_code == 200 and r.headers["content-type"] == "application/json; charset=utf-8"
        assert r.content.isascii()
        assert json.loads(r.content.decode("cp1252")) == json.loads(r.content.decode("utf-8")) == r.json()
