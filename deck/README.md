<!-- AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md. -->
# TRACE — pitch deck

The presentation for CDC 2026 judging. Not a slide file: a self-contained web deck that reads its
numbers back out of this repository every time it's built, so it can't drift from the project.

## Run it

```bash
open deck/index.html          # macOS   (or: start deck\index.html on Windows)
```

No build step, no server, no network required — it runs straight from the filesystem. Press `F` for
fullscreen. If you want it served instead: `python3 -m http.server -d deck 8080`.

## Controls

| Key | Does |
|---|---|
| `→` / `space` / click right | next |
| `←` / click left | back |
| `N` | speaker cues (presenter screen only — turn display mirroring **off**) |
| `T` | rehearsal timer + pace bar (green on pace, amber slipping, red over) |
| `G` | slide overview, click any slide to jump |
| `F` | fullscreen · `?` help · `Esc` close overlay |

## Format

**7:00 total — deck + live demo — then 2:00 Q&A.** The deck runs **4:45**, leaving ~2:00 for the live
demo that follows it. The last slide hands straight off: hit it and start the demo, no pause.

| Slot | Speaker | Section | Target |
|---|---|---|---|
| S1 | William Keffer | The Problem | 1:05 |
| S2 | Ismail Gasmi | The Idea | 1:00 |
| S3 | Markandeya Yalamanchi | How It Works | 1:10 |
| S4 | Adrian Hito | Proof, Impact & Handoff | 1:30 |

Reassign by editing `speakers` in `deck/content.json` and re-running the build — names propagate to the
deck, the status bar and the cue cards.

## Files

| File | What it is |
|---|---|
| `content.json` | **Source of truth.** Every slide, cue and timing. Edit this. |
| `build.py` | Reads the repo → writes `bundle.js`, `data.json`, `CUE_CARDS.md`, `PLACEHOLDERS.md` |
| `index.html` · `deck.css` · `deck.js` | The deck itself |
| `bundle.js` · `data.json` | Generated — do not edit |
| `CUE_CARDS.md` | Generated printable cue cards, one section per speaker |
| `PLACEHOLDERS.md` | Generated checklist of every screenshot still needed |
| `QA_PREP.md` | The hardest judge questions, with answers, assigned per speaker |
| `DEVPOST.md` | Submission copy, same narrative as the deck |
| `screenshots/` | Drop real captures here (see below) |

## Rebuild after the project changes

```bash
python3 deck/build.py
```

It re-reads the milestone table in `README.md`, the indicator table in `docs/DATA_SOURCES.md`, the
metrics and Afghan-ban series from `backend/data/processed/api/` (falling back to
`contracts/fixtures/`), and the current git SHA. Headline figures — AUC, the Afghan corridor hit rate,
corridor and indicator counts — are never typed into a slide; they are interpolated at build time with
`{{metrics.hurdle_auc}}`-style tokens. Change the model, re-export, rebuild, and the deck is current.

## Screenshots

Captures the frontend already commits are reused in place — `build.py` maps them in `SHOT_SOURCES`, so
`frontend/design/qa/atlas-desktop.jpg` and `experiment-desktop.jpg` are already on the slides and update
themselves when the frontend recaptures. The rest are labelled placeholders with a schematic wireframe
of the real screen. To add or override one:

1. Screenshot the screen fullscreen, no browser chrome, 2560×1440 or larger, dark terminal state, real
   data, year 2023 throughout so the captures read as one session.
2. Save it as `deck/screenshots/<id>.png` — the id is printed on the placeholder itself. A file here
   always beats the `SHOT_SOURCES` mapping.
3. `python3 deck/build.py`

The deck swaps it in automatically. `PLACEHOLDERS.md` tracks what's still outstanding and what has to
exist in the product before each capture is possible.

## Editing content

Slides are blocks. Available types: `kicker`, `lines`, `sub`, `source`, `rule`, `wordmark`, `swap`,
`lagrow`, `list`, `statgrid`, `commandline`, `pipeline`, `compare`, `chart`, `roadmap`, `shot`,
`shotgrid`. Each slide sets `theme` (`void` for the cinematic black act, `terminal` for the amber one),
`speaker`, `seconds` and `cues`. Timings drive the rehearsal timer and the cue cards, so keep them
honest — the total is checked on every build.

## Design notes

Act I is Apple-keynote black: enormous thin type, one idea per frame, deep negative space. The moment
TRACE is introduced the deck turns into the product's own world — the warm ivory editorial atlas,
vermilion and violet marks, from `frontend/design/qa/atlas-desktop.jpg`. The shift from black to ivory
is the argument: a cold human problem, then the instrument built to answer it, and real screenshots
land on slides that already look like them.

The deck followed the product here. It was black-and-amber terminal until the frontend's visual
direction was superseded (`frontend/design/pinterest-directions.md`); the palette tokens at the top of
`deck.css` are the only place that lives, so it can follow again.

Claims are aggressive but verifiable. Every number on screen traces to something in this repository or
a cited public source. Nothing on a slide can be falsified by a judge with a laptop, and the roadmap is
dated as a plan rather than stated as traction.
