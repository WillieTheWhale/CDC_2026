<!-- AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md. -->
# Deck handoff — for a fresh agent (Codex or otherwise)

Paste the whole of this file as the opening prompt. It assumes no prior context and no
checkout.

---

You are taking over maintenance of the pitch deck for TRACE, a project for the 2026
Carolina Data Challenge (Graduate track, theme "AI for Social Good"). Work autonomously.

## Setup (do this first, you are not in the repo yet)

```
git clone https://github.com/WillieTheWhale/CDC_2026 && cd CDC_2026
```

Read, in this order: `CLAUDE.md`, `README.md`, `deck/README.md`, `docs/SYSTEM_DESIGN.md`,
`docs/CDC_RULES.md`. Then run `python3 deck/build.py` to confirm the deck builds.
Push straight to `main` in small commits — that is the repo's rule, not an accident.
`git pull --rebase origin main` before every push; two other agents commit to this repo in
parallel (a Python backend and a Next.js frontend).

## What the deck is

A self-contained web deck at `deck/` — open `deck/index.html` in a browser, no build step,
no server. Keys: arrows navigate, `F` fullscreen, `T` rehearsal timer with pace bar,
`N` speaker cues, `G` slide overview.

Architecture, which matters because it is unusual:

- `deck/content.json` is the **source of truth** for every slide, cue and timing. Edit this.
- `deck/build.py` reads the repo (README status table, `docs/DATA_SOURCES.md`, the metrics
  and Afghan series from `backend/data/processed/api/` falling back to
  `contracts/fixtures/`, git SHA) and regenerates `deck/bundle.js`, `deck/data.json`,
  `deck/CUE_CARDS.md` and `deck/PLACEHOLDERS.md`. **Never hand-edit those four.**
- Slides interpolate `{{metrics.hurdle_auc}}`-style tokens, so headline numbers are never
  typed into a slide. If a model result changes upstream, rebuilding updates the deck.
- Screenshots: `deck/screenshots/<id>.png` overrides the `SHOT_SOURCES` map in `build.py`.
  All seven slots are currently filled with real captures.

## Hard constraints — do not break these

1. **24 slides, total exactly 285 seconds (4:45).** If you add or cut a slide, rebalance the
   others so the total stays 285. `build.py` prints the total on every run; check it.
2. **Four speakers, S4 longest:** S1 William Keffer 65s (The Problem), S2 Ismail Gasmi 60s
   (The Idea), S3 Markandeya Yalamanchi 70s (How It Works), S4 Adrian Hito 90s (Proof,
   Impact & Handoff). Deck runs 4:45, then a ~2:00 live demo, inside a 7:00 slot with 2:00
   Q&A after.
3. **Two themes:** `void` (cinematic black, Act I only) and `atlas` (warm ivory/vermilion,
   matching the product's real UI). All palette values are tokens at the top of
   `deck/deck.css`. If the frontend's visual direction changes again, change those tokens.
4. **Never invent a number.** Every figure on a slide comes from this repo or a cited public
   source. Several claims were corrected after fact-checking — do not regress them.
5. **CDC rules require AI citation:** an `AI-assisted` header comment in every file you write
   or substantially edit, plus a dated line in `docs/AI_USAGE.md` per session. Missing
   citations risk disqualification.
6. **Design boundary from CLAUDE.md, non-negotiable:** TRACE shows where drug flows and harms
   are heading, never where enforcement is weakest. No least-watched-route feature, ranking
   or framing, in the product or the deck.

## Corrections already applied — do not undo

- The cold open is **not** "erased 95% of the world's opium supply". 95% is the fall in Afghan
  **production** (6,200 t 2022 → 333 t 2023); Afghanistan was ~80% of world illicit opium;
  and supply did not collapse because ~12,000 t of stockpile kept flowing. The slides say
  "Afghanistan grew four fifths of the world's illicit opium" → "In April 2022, one decree
  cut it by 95%."
- 296 t is the **2025** Afghan figure. 2024 was 433 t.
- The Southeast Asia reallocation is **our** corridor allocation, not a UNODC measurement.
  UNODC treats it as an expectation. Labelled as such on the slide.
- Jev's confidence is **not** described as "calibrated" — TypeSafe publishes no calibration
  metrics. The deck calls it a routing signal. "Typed not text" is not the differentiator
  (constrained decoding is table stakes); latency and cost per article at stream volume is.
- Harm-reduction counts come from HRI's **Nov 2025 update** (NSP 93, OAT 95, DCR 19,
  naloxone 35), not the 2024 report.
- The null result (route exposure does not predict later homicide/HIV once vulnerability is
  controlled) is disclosed on its own slide in **three beats** — what we tested, what we
  found, what we changed. Keep all three; a bare admission reads as failure.

## Your job each time you are invoked

1. `git fetch origin main`. If no new commits and no new files in `deck/screenshots/`, stop
   and say so in one line. Do nothing else.
2. If there are new commits: read them (`git log --oneline`, `git diff --stat`, and the full
   diff of `README.md`, `docs/*.md`, `contracts/fixtures/*.json`). Rebase, run
   `python3 deck/build.py`.
3. `build.py` handles numbers, counts, milestone status and the Afghan series automatically.
   What it **cannot** do is notice that a new capability deserves a slide, that a claim in
   `content.json` has become false or understated, or that a shipped feature should move out
   of the roadmap slide. Edit `content.json` where that is true.
4. Update `deck/QA_PREP.md` and `deck/DEVPOST.md` if a new result changes the right answer to
   a judge question or the submission copy.
5. Rebuild, verify slide count and total runtime, commit with a message saying what changed
   and why, push.
6. Report in 2–4 lines: what landed upstream, what you changed, what you deliberately left
   alone.

## Open items the user still has to decide

- **Timing risk:** deck 4:45 + demo ~2:00 = 6:45 of a 7:00 slot. Practitioner guidance says
  rehearse to ~89% of the slot. A 4:15 cut has been offered and not yet accepted — build it
  only if asked.
- `README.md` now reflects the live frontend, but its API deployment row still says the Live
  Wire uses the keyword classifier and backlog replay. Production now calls the separate
  torch-free ONNX Reflex service and ships a backlog pre-classified with that model.
  `CLAUDE.md` assigns `README.md` to the backend agent; flag the stale row, do not silently
  edit another agent's file. `backend/README.md` also retains an older redeploy paragraph
  above its newer two-function instructions.
- The backend uses a single global 0.6 Jev confidence threshold. Independent testing shows
  miscalibration direction flips by question type, so per-field thresholds are the right fix.
  Backend agent's call. `QA_PREP.md` names it as known-and-not-done.
- Homework only a human can close: read arXiv 2609.26864 (Peters et al., 22 Sept 2026 —
  cocaine network flow model with displacement simulation, the closest prior art) in full;
  read the UNODC DMP Access Policy before claiming it is gated; have someone sign up at
  console.typesafe.ai to settle whether a Jev waitlist still exists.

## Context that will not be obvious

A full research pass was run against the pitch: seven streams covering the Afghan facts,
prior art, the transit-spillover literature, harm-reduction evidence, data latency, Jev
verification, and pitch craft. Its findings are already folded into the deck, `QA_PREP.md`
and `DEVPOST.md`. The strongest asset it surfaced is **detection latency, not the corridor
forecast**: across the three best-documented outbreaks among people who inject drugs, 60–95%
of infections are attributed to detection-and-response delay. That is why Act I has a Scott
County slide.

An hourly scheduled routine was watching this repo and rebuilding the deck automatically. It
dies with the Claude session that created it, so from now on do step 1 manually whenever
invoked.
