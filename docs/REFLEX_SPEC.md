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
| L6 TRACE domain | **fail** | **fail** | beats the keyword mock on is_event (0.97 vs 0.81), event type (0.98 vs 0.80), drug (0.90 vs 0.89), origin (0.91 vs 0.89), destination (0.82 vs 0.52); seizure size 0.95 vs 0.96 after moving quantities into code (`jev/quantity.py`) and applying the label definition "size is small for non-seizure events" (was 0.89). The remaining misses are seizures with no stated quantity |
| L7 jaggedness profile | documented | documented | P(q) + P(not q) sums 0.47 to 1.36 (Jev documents 1.19); counting and dates unreliable; ignores irrelevant filler; follows swapped criteria |
| L8 speed | pass | pass | about 50 ms per 7-question headline on a T4, about 0.4-0.8 s on the laptop CPU |

On 1,878 questions about Claude-written headlines it never saw, v0.2 scores 95.3% (v0.1: 89.2%) with calibration error 0.009. v0.2 is the shipped Live Wire model. Following TypeSafe's advice to keep numbers in code, stated weights and pill counts now set seizure size in code; that confirmed the model already read stated quantities correctly, and the remaining size gap is seizures with no stated quantity. Caveat: every domain test set above is synthetic; section 6 adds a real-news benchmark.

## 6. Real-news benchmark and grounding guardrails (2026-09-27)

Every earlier domain test used Claude-written headlines. `backend/trace_backend/jev/data/real_headlines_v1.jsonl` holds **92 real, published headlines** (77 with their first sentence), each with URL, publisher and date: 47 drug events from 5 continents (government releases from AFP, NZ Customs, CBP, DEA, DOJ, NCA, CBSA, RCMP, plus wire and national outlets), 6 drug-related non-events (reports, annual aggregates, destruction of an old haul), 23 near-miss negatives (pharma recalls and earnings, cannabis stock, overdose statistics, drug-war film and TV reviews, crop surveys, doping) and 16 unrelated items. Tricky cases are deliberate: pounds, tons and pill counts, "worth $23 million" with no weight, slang and chemical names (shabu, "Jihadi drug", carfentanil, nitazene, crystal methadone), ports and bridges without a country (Mundra, Pharr, Gioia Tauro), several countries in one sentence. Labels were written from the text only; each row also lists the countries and drugs the text supports (`support`), written by hand and independent of the gazetteer. Source list: `docs/DATA_SOURCES.md`.

**Hallucination** = a predicted origin/destination country or drug that is not in the row's hand-labelled support set. **False-event rate** = share of the 39 near-miss and unrelated items that would appear on the Live Wire. Full report: `backend/trace_backend/reflex/results/real_news_v1.json` (`python -m trace_backend.jev.benchmark`).

| | Reflex v0.2 | Reflex + grounding | Mock | Mock + grounding |
|---|---|---|---|---|
| is_event | 0.870 | **0.913** | 0.815 | 0.848 |
| event type | 0.880 | 0.880 | 0.739 | 0.739 |
| drug | 0.924 | **0.978** | 0.739 | 0.902 |
| origin | 0.924 | **0.957** | 0.891 | 0.891 |
| destination | 0.804 | **0.848** | 0.543 | 0.543 |
| size (28 seizures; "not stated" is a label) | 0.786 | **0.929** | 0.429 | 0.929 |
| correct extractions (origin / destination / drug) | 4/10, 30/38, 48/51 | **7/10, 36/38, 49/51** | 6/10, 5/38, 42/51 | same |
| hallucinated entities | 5 of 102 (all drugs) | **0 of 107** | 19 of 88 | **0 of 69** |
| false events on negatives | 12.8% (5/39) | 5.1% (2/39) | 15.4% | 7.7% |
| precision of events shown (type and drug right) | 0.774 | 0.840 | 0.536 | 0.769 |
| calibration: mean confidence shown vs precision | 0.846 vs 0.774 | 0.857 vs 0.840 (ECE 0.052) | 0.841 vs 0.536 | 0.880 vs 0.769 |

Reflex never invented a country on real news, even before the guardrails (its country options are already limited to places the text names); its hallucinations were drugs guessed from context: "other" for nitazene and extradition stories, cannabis for a thyroid-tablet recall, cocaine for a coca-leaf opinion piece. The mock hallucinated 19 times (a drug for every "drugs" headline).

**What the guardrails do** (`backend/trace_backend/jev/grounding.py`, applied inside `ReflexClassifier` and to every classifier on the shared Live Wire path):
1. Country evidence from the text: World Bank names and aliases, demonyms, upper-case acronyms (US, UK, UAE, PH), US/Mexican/Canadian/Australian states, a curated list of ports and border crossings, and Natural Earth cities of 150k+ (`seed/estimated_flows_cities.csv`; ambiguous names resolved to the far larger city, common-word names excluded). Names must be capitalised ("turkey", "tell us" never count); regions ("Latin American", "Golden Triangle", "New Mexico" for Mexico) are consumed without naming a country. These places are also Reflex's candidate options.
2. An origin, transit, destination or map location without textual support becomes null ("not stated").
3. A drug without a synonym match (cocaine: crack, coca paste; meth: shabu, yaba, ice; fentanyl: carfentanil, nitazenes; other: captagon, ketamine, xylazine...) is replaced by the most probable supported option, else "unclear".
4. Size only from a stated quantity or record wording (`quantity.py`); otherwise `size_stated: false`.
5. is_event needs drug-trade vocabulary, an event type other than "other", and P >= 0.7. The 0.7 threshold (with the existing 0.6 display cut) was chosen on the 295 synthetic validation headlines (recall 0.947, false events 3.0%); the real benchmark was never used for tuning.

**Limits.** One annotator (AI-assisted) wrote the labels; 92 rows give wide error bars (one headline moves a rate by 1-2.6 points). False events are 5.1%, just above the 5% target: the remaining leaks are reports that read like events. Zero hallucination is guaranteed by construction only for entities the gazetteer and synonym lists can see; a model can still pick the *wrong* supported country (for example the seizing country as origin), which counts as an accuracy error, not a hallucination. Calibration over all rows is unchanged (ECE 0.18 raw, 0.19 grounded) because suppressed non-events keep their original confidence. The Live Wire classifies GDELT titles only, without the first sentence the benchmark includes.

## Production deployment (two functions)

Reflex runs live in production as its own Vercel function, **https://trace-reflex.vercel.app** (`POST /api/classify`,
`GET /api/health`), built by `backend/scripts/build_vercel_reflex.py`: fastapi, numpy, onnxruntime and tokenizers,
the emb8 model stored as ONNX external data (a 31 MB graph plus 25 weight files, each under Vercel's 100 MB upload
limit; outputs bit-identical to `model.emb8.onnx`) and the country catalogue the guardrails read. About 147 MB.

The main API (`backend/scripts/build_vercel.py`) cannot also hold the model and onnxruntime under the 500 MB function
limit, so at build time it classifies the Live Wire backlog with the real ONNX model inside the package (first
request 17 s -> 0.06 s), then ships without the model and calls the service through
`jev.remote.RemoteReflexClassifier` (`TRACE_CLASSIFIER=reflex-remote`, `TRACE_REFLEX_URL`). `POST /api/livewire/classify`
classifies any headline live through the service (about 1.5 s warm, about 4.5 s on a cold start) and returns 503,
never a silent keyword answer, if the service is unreachable.

