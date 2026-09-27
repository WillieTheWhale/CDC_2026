<!-- AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md. -->
# Reflex: TRACE's own System One model

**Reflex** (`reflex-0.1.0`) is an open, locally trained decision model built to the published specification of TypeSafe's Jev. Jev is a "System One" model, named after Kahneman's fast, intuitive thinking; a reflex is the fastest decision a nervous system makes. Reflex answers typed questions (Choice, Score, Noul) about a state with probabilities and confidence, runs on a laptop CPU, and costs nothing per call.

Reflex is **not** Jev and does not copy TypeSafe code or weights (neither is public). It re-implements the documented *behaviour* (interface, output contract, calibration objective) on an open pretrained encoder, and is measured against that behaviour with the Reflex Parity Scale below.

## 1. What TypeSafe's documentation specifies (processed 2026-09-26)

All 59 pages of https://docs.typesafe.ai (index `llms.txt`, JavaScript SDK reference excluded) were downloaded and read. The requirements Reflex is built to, with the page each comes from:

| # | Requirement | Source page |
|---|---|---|
| R1 | One call = one `state` + a map of typed questions; question IDs are never sent to the model; every question sees the same state and is answered independently | Primitives, State |
| R2 | Three primitives. **Choice**: pick one option from a map `{name: description}`, up to 255 options. **Score**: ordered list of 2 to 10 level descriptions. **Noul**: yes/no with optional `criteria.true` / `criteria.false` | Choice, Score, Noul, API |
| R3 | The model never generates text; every answer is constrained to the supplied options or levels | System One, Primitives |
| R4 | Choice returns `choice` (argmax), `probabilities` over all options (sum 1), `confidence`. Choice is **relative**: it settles which option | Choice, Jaggedness #8 |
| R5 | Score returns `probabilities` over levels, `score` = sum(level x probability), `legend`, `confidence`. **Each level is judged on its own; the model does not see a level's number or its neighbours** | Score |
| R6 | Noul returns one probability of yes; no separate confidence. Noul is **absolute**; P(q) and 1 - P(not q) need not agree | Noul, Jaggedness #8 |
| R7 | `confidence = (K * p_max - 1) / (K - 1)` for K options or levels (checked against every documented example: 0.35, 0.42, 0.20, 0.84) | Confidence (embedded formula) |
| R8 | Probabilities are **calibrated**: across many answers, 0.8 should be right about 80% of the time. Trained with RLCD (reinforcement learning for calibrated decisions) on a pretrained language model, not RLHF | AI primer, System One |
| R9 | `instructions`, option descriptions, level descriptions and Noul criteria each accept a string, JSON object, array or null; the model is "trained to understand structure"; option names and descriptions are both sent | Advanced: structure, Choice |
| R10 | State is text or JSON; the model reads it once and evaluates all questions against it | State, Models |
| R11 | Descriptive levels beat numeric levels; examples inside a level help when they resemble the input | Score |
| R12 | Known weak spots (jaggedness): literal reading, arithmetic and counting, date comparison, indirection, large irrelevant state, adversarial content, contradictory instructions and criteria, structural invariants, generation | Jev 1.13 jaggedness |
| R13 | Jev 1.13: 64k-token context, text only, English best, 70-500 ms per call | Models, CONTEXT_LOG |
| R14 | Jev is not fine-tuned per customer; customisation is through state, instructions and criteria, plus downstream models trained on its probabilities. With no labels, generate them with stronger reasoning models | Models, How to build, AutoResearch cookbook |

## 2. Reflex design (how each requirement is met)

| Requirement | Reflex implementation |
|---|---|
| R1, R10 | `Reflex.system_one(state, questions)` with the same request shape and Jev-compatible answer objects. The state is serialised once and paired with each option |
| R2, R3, R4, R5 | **Per-option cross-encoding.** For every option or level, the encoder reads `[state] [SEP] [question + that option's name and description]` and outputs one scalar. Choice and Score probabilities are a softmax over those scalars, so answers can never fall outside the supplied options, and each Score level is judged without seeing its number or neighbours, exactly as R5 says |
| R6 | Noul is scored as two hypotheses (yes + `criteria.true`, no + `criteria.false`) and normalised. It is a separate head from Choice, so absolute/relative behaviour is learned, not forced |
| R7 | Confidence uses the published formula verbatim |
| R8 | RLCD itself is unpublished. Reflex uses the standard calibrated-probability recipe: train on log-loss (a strictly proper scoring rule, minimised only by honest probabilities), then fit one temperature per primitive on held-out data. Calibration is *measured* (ECE, Brier); TypeSafe publishes no calibration numbers |
| R9 | JSON states and structured criteria are serialised deterministically (`key: value` lines, arrays as bullets). Training mixes string and structured forms |
| R11 | Training uses descriptive levels and options; some examples carry `examples` inside criteria |
| R13 | Backbone `cross-encoder/nli-deberta-v3-xsmall` (22M backbone params, 70M with embeddings, English NLI-pretrained), 320-token pairs. Chosen to train and run on this machine's CPU. Context is far shorter than Jev's 64k |
| R14 | Reflex is ours, so it *can* be fine-tuned. Labels come from free, openly licensed datasets plus TRACE-domain examples generated from real UNODC seizure records. Labelling real headlines with a stronger LLM (the docs' own advice) is the next step and needs a budget decision |

Pretrained starting point: an NLI cross-encoder already scores "does this text support this statement", which is the core of all three primitives. Reflex initialises its per-option score as `entailment logit - contradiction logit` and fine-tunes the whole network on the System One objective.

## 3. The Reflex Parity Scale

How close Reflex gets to the documented Jev, in eight levels. Each level has a pass test that is run and reported in `backend/data/reflex/eval.json` (summary in section 5).

| Level | Name | Pass criterion |
|---|---|---|
| **L0** | Interface parity | Accepts the documented request shape (string/JSON state, Choice/Score/Noul, structured criteria, up to 255 options and 10 levels) and returns the documented answer fields. Unit tests |
| **L1** | Output contract | Probabilities sum to 1; `choice` = argmax; `score` = expected level; confidence matches R7 on the documented examples; answers never leave the option set. Unit tests |
| **L2** | Trained competence | On held-out splits of the training tasks, beats the untuned NLI backbone and a majority-class baseline for all three primitives |
| **L3** | Zero-shot generalisation | On tasks **never seen in training** (new questions and option sets), beats chance and the untuned backbone |
| **L4** | Calibration | Expected calibration error (15 bins) <= 0.05 in distribution after temperature scaling; out-of-distribution ECE reported. For reference, independent testing puts Jev at about 0.02-0.03 in distribution and about 4x worse outside it (see `deck/QA_PREP.md`) |
| **L5** | Structure | Structured JSON state and criteria give answers at least as accurate as the same content flattened to a string |
| **L6** | Domain (TRACE Live Wire) | On the 100-headline evaluation set, per-field accuracy at least matches the keyword mock for event type, drug, origin, destination, size and is_event |
| **L7** | Jaggedness profile | Probes for R12's failure modes (negation, counting, dates, irrelevant state, contradictory criteria) are run and reported. Documenting where Reflex fails is the pass condition, not avoiding every failure |
| **L8** | Speed | Median CPU latency per question reported. Jev's 70-500 ms includes a network round trip; Reflex runs locally |

## 4. Training data (all free; licences in `docs/DATA_SOURCES.md`)

Every example is converted into a System One request with its instructions and criteria worded in several styles, options shuffled, sometimes structured, and sometimes with an `other`/`none of the above` option.

| Primitive | Training tasks | Held out entirely (zero-shot, L3) |
|---|---|---|
| Noul | BoolQ (passage + yes/no question); MultiNLI (premise + statement judged true or not) | RTE (textual entailment) |
| Choice | AG News (topic), DBpedia-14 (entity type), TREC (question type) | Emotion (6 emotions) |
| Score | Yelp reviews (1-5 stars, descriptive levels) | SST-5 (5-level sentiment) |
| TRACE domain | Headlines generated from real UNODC IDS seizure records in the SQLite archive (country, city, drug, quantity, place, transport mode), with non-event and policy/arrest/lab/violence/corruption variants. Labels are exact by construction | The 100-headline Live Wire eval set (written separately, different wording) |

## 5. Results (2026-09-26, trained on a Colab T4 GPU via the Colab CLI)

Full reports: `backend/trace_backend/reflex/results/eval_v0.1.json` and `eval_v0.2.json`.

- **v0.1** (`reflex-0.1.0`): the NLI backbone fine-tuned on 10,777 examples (open datasets plus headlines generated from real UNODC seizure records).
- **v0.2** (`reflex-0.2.0`): v0.1 continued on 2,351 Claude-written, blind-verified headlines, plus 4,000 replayed v0.1 examples.

| Parity level | v0.1 | v0.2 | Evidence (v0.2) |
|---|---|---|---|
| L0/L1 interface and output contract | pass | pass | all checks, including the confidence formula on TypeSafe's documented examples |
| L2 trained competence | pass | pass | held-out accuracy 90.2% vs 48.1% for the untuned backbone; beats majority baseline on every task |
| L3 zero-shot | **fail** | **fail** | RTE 80% (backbone 63%), SST-5 43% (25%), but Emotion 50.5% < backbone 57% |
| L4 calibration | pass | pass | ECE 0.020 in distribution (backbone 0.206), 0.062 zero-shot; independent tests put Jev at about 0.02-0.03 |
| L5 structure | pass | pass | structured JSON state at least as accurate as flattened text |
| L6 TRACE domain | **fail** | **fail** | beats the keyword mock on is_event (0.97 vs 0.81), event type (0.98 vs 0.80), drug (0.90 vs 0.89), origin (0.91 vs 0.89), destination (0.82 vs 0.52); **loses on seizure size (0.89 vs 0.96)** |
| L7 jaggedness profile | documented | documented | P(q) + P(not q) sums 0.47 to 1.36 (Jev documents 1.19); counting and dates unreliable; ignores irrelevant filler; follows swapped criteria |
| L8 speed | pass | pass | about 50 ms per 7-question headline on a T4, about 0.4-0.8 s on the laptop CPU |

On 1,878 questions about Claude-written headlines it never saw, v0.2 scores 95.3% (v0.1: 89.2%) with calibration error 0.009. v0.2 is the shipped Live Wire model. Following TypeSafe's own advice to keep numbers in code, the next step is to compute seizure size from stated quantities, which would clear L6. Caveat: every domain test set is synthetic; team-labelled real headlines are the honest next benchmark.
