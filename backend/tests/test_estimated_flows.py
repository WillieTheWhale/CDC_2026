# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Estimated local flows follow money out of modeled entry cities and stay regional."""
from trace_backend.model.estimated_flows import MAX_KM, estimate

CITIES = [
    # Destination country B: a rich big city near the border, a poorer one far away.
    {"name": "Borderville", "iso3": "BBB", "pop": 2_000_000, "lon": 1.0, "lat": 0.0},
    {"name": "Farpoint", "iso3": "BBB", "pop": 300_000, "lon": 9.0, "lat": 0.0},
    # Neighbour C has no modeled routes: one rich city, one poor city at the same distance.
    {"name": "Richtown", "iso3": "CCC", "pop": 1_000_000, "lon": 1.0, "lat": 3.0},
    {"name": "Poortown", "iso3": "DDD", "pop": 1_000_000, "lon": 1.0, "lat": -3.0},
    {"name": "Overseas", "iso3": "EEE", "pop": 9_000_000, "lon": 60.0, "lat": 0.0},
]
GDP = {"BBB": {2020: 30_000.0}, "CCC": {2020: 50_000.0}, "DDD": {2020: 2_000.0}, "EEE": {2020: 60_000.0}}
EDGES = [{"from": "AAA", "to": "BBB", "drug": "cocaine", "volume_norm": 1.0, "confidence": 80.0}]
ANCHORS = {"AAA": (-2.0, 0.0), "BBB": (5.0, 0.0)}


def _layer():
    return estimate(EDGES, CITIES, GDP, ANCHORS, 2021)


def _flows(layer):
    cities = layer["cities"]
    return [{"from": cities[f[3]][0], "to": cities[f[4]][0], "strength": f[2], "km": f[5]} for f in layer["flows"]]


def test_entry_city_faces_the_route_and_is_the_darkest():
    layer = _layer()
    assert layer["cities"][0][0] == "Borderville"  # sorted by intensity, 1.0 first
    assert layer["cities"][0][4] == 1.0


def test_arrows_follow_money_and_stay_regional():
    flows = _flows(_layer())
    targets = {f["to"]: f for f in flows}
    assert "Overseas" not in targets  # beyond MAX_KM: estimates never invent long-haul routes
    assert all(0 < f["km"] <= MAX_KM for f in flows)
    assert targets["Richtown"]["strength"] > targets["Poortown"]["strength"]  # same distance, more money
    assert all(f["from"] == "Borderville" for f in flows if f["to"] in {"Richtown", "Poortown"})


def test_no_modeled_edges_means_no_estimates():
    assert estimate([], CITIES, GDP, ANCHORS, 2021)["flows"] == []
