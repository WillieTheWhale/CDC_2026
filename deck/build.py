#!/usr/bin/env python3
# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Rebuild the TRACE pitch deck from the repository.

The deck never hard-codes a number. Everything it shows is read back out of the
project on every build, in this order of preference:

  1. backend/data/processed/api/*.json   real pipeline export (gitignored, local only)
  2. contracts/fixtures/*.json           committed contract fixtures
  3. README.md / docs/*.md               headline results and milestone status
  4. defaults below                      last resort, so the deck always renders

Outputs (all committed):
  deck/bundle.js        content + data, as a plain script so the deck runs from file://
  deck/data.json        the same project data, for anything else that wants it
  deck/CUE_CARDS.md     printable speaker cue cards
  deck/PLACEHOLDERS.md  live checklist of every screenshot the deck still needs

Usage:  python3 deck/build.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DECK = Path(__file__).resolve().parent
REPO = DECK.parent
API = REPO / "backend" / "data" / "processed" / "api"
FIX = REPO / "contracts" / "fixtures"
SHOTS = DECK / "screenshots"

DEFAULTS = {
    "project": {
        "name": "TRACE",
        "one_liner": "A Bloomberg terminal for the global drug trade that predicts "
                     "where the next drug crisis will hit, before it arrives.",
        "tagline": "Early warning for the countries that never chose to be on the route.",
    },
    "counts": {
        "indicators": "24", "economies": "217", "ids_cases": "2.3M", "corridors": "676",
        "oc_index": "193", "hri": "193", "risk_countries": "217",
        "latest_year": "2024", "first_year": "2011", "sources": "9",
    },
    "metrics": {
        "hurdle_auc": "0.92", "gravity_auc": "0.61", "afghan_hit": "12/14",
        "sea_base": "5%", "sea_pred": "12%", "sea_actual": "14%",
        "train_through": "2019", "afghan_train_through": "2021",
    },
}

# Screenshot ids the deck can display, with what has to exist before they can be taken.
SHOT_SPECS = {
    "route-map":     ("Route Map (hero, full-bleed)", "Frontend shell + map"),
    "country-screen": ("Country Screen — Colombia", "Country Screen"),
    "risk-board":    ("Spillover Risk Board — RISK TOP 20", "Risk Board"),
    "simulator":     ("Shock Simulator mid-run", "Simulator UI"),
    "livewire":      ("Live Wire feed with one anomaly", "Live Wire panel"),
    "market-board":  ("Market Board price tickers", "Market Board"),
    "experiment":    ("Afghan ban predicted vs actual", "Experiment view"),
}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _json(*candidates: Path):
    for p in candidates:
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8")), p
            except (OSError, json.JSONDecodeError):
                continue
    return None, None


def _unwrap(obj):
    """Contract fixtures wrap payloads in {meta, data}; the live export does not."""
    if isinstance(obj, dict) and "data" in obj and "meta" in obj:
        return obj["data"]
    return obj


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True,
                              text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def read_status(readme: str) -> dict:
    """Parse the README milestone table into shipped / pending lists."""
    shipped, pending = [], []
    for line in readme.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3 or cells[0].lower() in {"milestone", "---"} or set(cells[0]) <= {"-", ":"}:
            continue
        milestone, owner, status = cells[0], cells[1], cells[2]
        if owner.lower() not in {"backend", "frontend", "planning session"}:
            continue
        label = re.sub(r"^T\d+\s+", "", milestone).strip()
        (shipped if status.lower().startswith("done") else pending).append(
            {"label": label, "owner": owner, "status": status})
    return {"shipped": shipped, "pending": pending}


def read_metrics(readme: str, data: dict) -> None:
    """Headline model numbers: live export first, then the README status table."""
    m, src = _json(API / "metrics.json", FIX / "metrics.json")
    if m:
        bt = (_unwrap(m) or {}).get("backtest", {})
        if bt.get("hurdle", {}).get("auc") is not None:
            data["metrics"]["hurdle_auc"] = f"{bt['hurdle']['auc']:.2f}"
        if bt.get("gravity_baseline", {}).get("auc") is not None:
            data["metrics"]["gravity_auc"] = f"{bt['gravity_baseline']['auc']:.2f}"
        if bt.get("train_through"):
            data["metrics"]["train_through"] = str(bt["train_through"])
        data["provenance"]["metrics"] = str(src.relative_to(REPO))

    # README carries the numbers from the real run, so it wins over fixtures.
    pat = [
        (r"hurdle AUC\s*([\d.]+)\s*vs\s*gravity\s*([\d.]+)", ("hurdle_auc", "gravity_auc")),
        (r"Afghan ban\s*(\d+/\d+)\s*corridors", ("afghan_hit",)),
    ]
    for rx, keys in pat:
        mm = re.search(rx, readme)
        if mm:
            for i, k in enumerate(keys):
                data["metrics"][k] = mm.group(i + 1)
            data["provenance"]["metrics"] = "README.md (live run)"
    mm = re.search(r"SEA share\s*(\d+)%\s*->\s*(\d+)%\s*pred vs\s*(\d+)%\s*actual", readme)
    if mm:
        data["metrics"]["sea_base"] = mm.group(1) + "%"
        data["metrics"]["sea_pred"] = mm.group(2) + "%"
        data["metrics"]["sea_actual"] = mm.group(3) + "%"


def read_counts(readme: str, sources_doc: str, data: dict) -> None:
    c = data["counts"]
    for rx, key, fmt in [
        (r"(\d+)\s+indicators", "indicators", str),
        (r"(\d+)\s+economies", "economies", str),
        (r"IDS\s+([\d.]+M)\s+cases", "ids_cases", str),
        (r"(\d+)\s+corridors", "corridors", str),
        (r"HRI\s+(\d+)\s+countries", "hri", str),
    ]:
        mm = re.search(rx, readme)
        if mm:
            c[key] = fmt(mm.group(1))
    mm = re.search(r"(\d+)\s+corridors\s*x\s*(\d{4})-(\d{4})", readme)
    if mm:
        c["first_year"], c["latest_year"] = mm.group(2), mm.group(3)
    mm = re.search(r"\((\d+)\s+countries\s*x\s*(\d{4})-(\d{4})", readme)
    if mm:
        c["risk_countries"] = mm.group(1)

    # Indicator table in DATA_SOURCES is the authoritative count if it parses.
    rows = re.findall(r"^\|\s*(Governance|Logistics|Gravity|Vulnerability|Outcome)\s*\|",
                      sources_doc, re.M)
    if rows:
        c["indicators"] = str(len(rows))
    ext = re.findall(r"^\|\s*(UNODC|Global Organized|Harm Reduction|US Customs|CDC|GDELT|CEPII|Natural Earth)",
                     sources_doc, re.M)
    if ext:
        c["sources"] = str(len(set(ext)))


def read_afghan(data: dict) -> None:
    obj, src = _json(API / "afghan_ban.json", FIX / "afghan_ban.json")
    if not obj:
        return
    d = _unwrap(obj) or {}
    series = {s.get("id"): s for s in d.get("series", [])}
    out = []
    for sid, label in [("afg_cultivation", "Afghanistan"), ("mmr_cultivation", "Myanmar")]:
        s = series.get(sid)
        if s:
            out.append({"id": sid, "label": label, "unit": s.get("unit", "ha"),
                        "points": [{"x": p["year"], "y": p["value"]} for p in s.get("points", [])]})
    if out:
        data["charts"]["afghan"] = {"series": out, "ban_year": d.get("ban_year", 2022),
                                    "title": d.get("title", "Afghanistan 2022 opium ban")}
        data["provenance"]["afghan"] = str(src.relative_to(REPO))


def read_screenshots(data: dict) -> None:
    found = {}
    if SHOTS.is_dir():
        for p in sorted(SHOTS.iterdir()):
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".avif"}:
                found[p.stem] = f"screenshots/{p.name}"
    data["screenshots"] = found
    data["placeholders"] = [
        {"sid": sid, "title": SHOT_SPECS[sid][0], "needs": SHOT_SPECS[sid][1]}
        for sid in SHOT_SPECS if sid not in found
    ]


def build() -> dict:
    readme = _read(REPO / "README.md")
    sources_doc = _read(REPO / "docs" / "DATA_SOURCES.md")

    data = json.loads(json.dumps(DEFAULTS))
    data["charts"] = {}
    data["provenance"] = {"built_from": "defaults"}

    read_counts(readme, sources_doc, data)
    read_metrics(readme, data)
    read_afghan(data)
    read_screenshots(data)

    st = read_status(readme)
    data["status"] = st
    done_backend = [s["label"] for s in st["shipped"] if s["owner"] == "backend"]
    data["status"]["shipped_short"] = (
        "Pipeline, models, backtests, API and Live Wire shipped; terminal in build"
        if done_backend else "In build")
    data["status"]["shipped_count"] = len(st["shipped"])
    data["status"]["pending_count"] = len(st["pending"])

    data["git"] = {
        "sha": _git("rev-parse", "--short", "HEAD"),
        "subject": _git("log", "-1", "--format=%s"),
        "when": _git("log", "-1", "--format=%cI"),
        "count": _git("rev-list", "--count", "HEAD"),
    }
    data["built_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return data


def write_cue_cards(content: dict, data: dict) -> None:
    by_slot = {s["slot"]: s for s in content["speakers"]}
    out = ["<!-- AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md. -->",
           "<!-- GENERATED by deck/build.py. Edit deck/content.json, not this file. -->",
           "# TRACE — Speaker Cue Cards", "",
           f"*Rebuilt {data['built_at']} from `{data['git'].get('sha', '?')}`.*", "",
           f"**{content['meta']['format_note']}**", "",
           "Deck runs **{}:{:02d}**. Demo follows immediately — no pause, no 'any questions'.".format(
               content["meta"]["runtime_target_seconds"] // 60,
               content["meta"]["runtime_target_seconds"] % 60), "",
           "| Slot | Speaker | Section | Target |", "|---|---|---|---|"]
    for s in content["speakers"]:
        out.append(f"| {s['slot']} | {s['name']} | {s['section']} | {s['seconds']//60}:{s['seconds']%60:02d} |")
    out.append("")

    cur = None
    running = 0
    for i, sl in enumerate(content["slides"], 1):
        if sl["speaker"] != cur:
            cur = sl["speaker"]
            sp = by_slot.get(cur, {"name": cur, "section": ""})
            out += ["", "---", "", f"## {sp['name']} — {sp['section']} (`{cur}`)", ""]
        head = _resolve(_slide_title(sl), data)
        out.append(f"**{i}. {head}** — {sl['seconds']}s · cumulative {running + sl['seconds']}s")
        running += sl["seconds"]
        out.append("")
        for c in sl.get("cues", []):
            out.append(f"- {_resolve(c, data)}")
        if sl.get("handoff"):
            out.append(f"- **Handoff line:** “{_resolve(sl['handoff'], data)}”")
        out.append("")
    (DECK / "CUE_CARDS.md").write_text("\n".join(out) + "\n", encoding="utf-8")


def write_placeholders(content: dict, data: dict) -> None:
    used = []
    for sl in content["slides"]:
        for b in sl["blocks"]:
            if b["type"] == "shot":
                used.append((sl["id"], b["sid"], b.get("spec", ""), b.get("caption", "")))
            if b["type"] == "shotgrid":
                for it in b["items"]:
                    used.append((sl["id"], it["sid"], it.get("spec", ""), it.get("title", "")))
    have = data["screenshots"]
    out = ["<!-- AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md. -->",
           "<!-- GENERATED by deck/build.py. Re-run it after dropping files into deck/screenshots/. -->",
           "# Deck placeholders — screenshot checklist", "",
           f"*Rebuilt {data['built_at']}.* "
           f"**{len(have)}/{len(used)} captured.**", "",
           "Drop a file named `<id>.png` into `deck/screenshots/` and re-run `python3 deck/build.py`. ",
           "The deck swaps the placeholder for the real capture automatically — no slide edits needed.", "",
           "| Status | id | Slide | What to capture | Blocked on |", "|---|---|---|---|---|"]
    for slide_id, sid, spec, caption in used:
        ok = sid in have
        needs = SHOT_SPECS.get(sid, ("", "?"))[1]
        mark = "✅ have" if ok else "⬜ needed"
        out.append(f"| {mark} | `{sid}` | `{slide_id}` | {spec or caption} | {needs} |")
    out += ["", "## Capture rules", "",
            "- 2560×1440 or larger, PNG, no browser chrome (fullscreen the app, then screenshot).",
            "- Dark terminal state only — amber on black. No light-mode captures.",
            "- Real data in every panel. An empty state on stage reads as a broken product.",
            "- Same year selected across captures (2023) so the deck feels like one session.",
            "- If a screen is not built by capture time, leave the placeholder: it is labelled, deliberate,",
            "  and reads far better than a blurry or empty screenshot."]
    (DECK / "PLACEHOLDERS.md").write_text("\n".join(out) + "\n", encoding="utf-8")


def _slide_title(sl: dict) -> str:
    for b in sl["blocks"]:
        if b["type"] == "kicker":
            return b["text"]
        if b["type"] == "lines":
            return " ".join(b["items"])[:70]
        if b["type"] == "swap":
            return b["to"]
        if b["type"] == "wordmark":
            return b["text"]
    return sl["id"]


def _resolve(text: str, data: dict) -> str:
    def sub(m):
        cur = data
        for part in m.group(1).split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return m.group(0)
        return str(cur)
    return re.sub(r"\{\{([a-z_.]+)\}\}", sub, text)


def main() -> int:
    content = json.loads((DECK / "content.json").read_text(encoding="utf-8"))
    data = build()

    (DECK / "data.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    bundle = "// AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.\n" \
             "// GENERATED by deck/build.py — do not edit. Source: deck/content.json + the repo.\n" \
             "window.TRACE_DECK = " + json.dumps({"content": content, "data": data},
                                                 ensure_ascii=False, separators=(",", ":")) + ";\n"
    (DECK / "bundle.js").write_text(bundle, encoding="utf-8")

    write_cue_cards(content, data)
    write_placeholders(content, data)

    total = sum(s["seconds"] for s in content["slides"])
    print(f"deck rebuilt  · {len(content['slides'])} slides · {total//60}:{total%60:02d} "
          f"· AUC {data['metrics']['hurdle_auc']} vs {data['metrics']['gravity_auc']} "
          f"· {len(data['screenshots'])} screenshots · {data['status']['shipped_count']} milestones done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
