<!-- AI-assisted: written with Claude Code (Anthropic) and maintained with Codex (OpenAI). See docs/AI_USAGE.md. -->
# Q&A prep — 2 minutes, four people, no freezing

**Two minutes admits three, maybe four questions.** A 60-second first answer eats the panel's remaining
questions and denies the other three of you any chance to show what you contributed. Target **25-30 seconds**:
answer, one piece of evidence, stop. Pause two to three seconds before answering — it reads as considered,
not slow, and it stops you starting a sentence you can't finish.

If you don't know: move *toward* the questioner, hold eye contact, and say **"I don't know — I'll find out
and let you know."** Never bluff. A bluff that a judge catches costs more than the question was worth.

Rules of engagement: **whoever owns the section owns the question.** If a question lands in nobody's
lane, Adrian (S4) takes it. Answer in two sentences, then stop. A short confident answer beats a long
hedged one, and a judge who wants more will ask again.

If you genuinely do not know: *"We didn't test that. Here's what we did test, and here's how we'd test
that next."* Never invent a number on stage — every figure below is in the repo.

---

## The questions they are most likely to ask

**1. "Seizures measure enforcement, not trafficking. Isn't your whole network just a map of who has good customs?"** — *Markandeya (S3)*
Correct, and it's the first limitation in our spec. Three defences: no corridor rests on seizures
alone — each one carries a 0–100 confidence score from six independent signals (seizures, price
gradient direction, OC Index market scores at both ends, live news hits, cultivation upstream); we
explicitly control for detection capability with World Bank rule-of-law and customs-efficiency
indicators; and low-confidence corridors are drawn faint rather than hidden, so the uncertainty is on
screen instead of in a footnote. And it cuts the other way on our own null result — if exposure is partly
a map of enforcement capacity, and capacity correlates with state strength, that alone could produce the
negative coefficient we found. We'd rather name that than let a judge find it.

**2. "Couldn't traffickers use this?"** — *William (S1)*
Every input is public UN data that trafficking organisations already know better than we do. And the
tool is built the other way round on purpose: it shows where harm is heading, never where enforcement
is weak. No least-watched-route feature, no lowest-risk-corridor ranking, no "safest path" query. That
boundary is written into our engineering rules file and was committed before the first line of model
code.

**3. "Is the World Bank data actually doing work, or is it decoration for the track requirement?"** — *Markandeya (S3)*
Five distinct roles: market mass in the gravity model (GDP, GDP per capita PPP, population); route
friction (governance, customs efficiency, port TEU, air traffic, trade openness); vulnerability (youth
unemployment, NEET, poverty, Gini, health spend); validation targets (homicide, HIV incidence, refugee
flows); and detection-bias control. Remove it and there are no market sizes, no friction terms and no
vulnerability layer — the model stops existing. We call the API programmatically with explicit source
IDs, paginated, nulls preserved, with provenance recorded per value. The resulting 1960–2025 history is
read from a checksum-verified SQLite v2 archive; derived model tables live separately so the source archive
stays unchanged.

**4. "Your spillover hypothesis failed. Doesn't that undercut the project?"** — *Adrian (S4)*
It's the finding, not a failure, and the literature lands in the same place. A 2026 panel of 95 countries
in the European Journal on Criminal Policy and Research finds the cocaine–homicide association shows up in
random effects but not fixed effects — the link is structural position on a trafficking corridor, not
within-country variation over time. Our national, level-based test was asking the question that study
says comes up null. That can coexist with our cross-sectional result: surveyed route countries show
3.5× the cocaine-use prevalence of off-route countries and 2.5× the homicide rate of destination-only
countries; that tells us where the burden sits, not that route arrival caused it. The causal work that
does find route effects — Dell's 2015 AER paper on Mexican
route diversion, Castillo, Mejía and Restrepo in REStat on Colombian supply shocks — identifies
*transitions and shocks*, sub-nationally, not steady-state exposure at country level. So: exposure alone
isn't destiny, exposure without protection is, and that's why the risk score has three columns. A team
that only reports the results that worked is a team you should trust less.

**5. "AUC 0.88 sounds high. Are you leaking future information?"** — *Markandeya (S3)*
Strict temporal split: trained through 2019, evaluated on 2020–2024, no target-derived features, and
lagged volume is last year's value only. The gravity baseline runs on the identical splits and gets
0.58, which is the sanity check — if we were leaking, the baseline would be inflated too. The Afghan
test is stronger evidence still: trained through 2021, shocked, and checked against data the model
never saw.

**6. "What does Reflex add over a normal LLM?"** — *Markandeya (S3)*
Control and predictable economics. Reflex is our own 70M-parameter per-option cross-encoder, so it runs
locally without an API key, emits only the supplied choices, and can score every option in one batch. We
fine-tune it with log-loss and fit one temperature per primitive on held-out data. It sits behind the same
classifier interface as Jev and the keyword fallback, so Live Wire degrades visibly instead of stopping.

**6b. "You said calibrated confidence. Is it calibrated?"** — *Markandeya (S3)*
On the published benchmark, yes; in the field, not yet. Reflex v0.2 has ECE 0.020 in distribution and 0.062
zero-shot; on 1,878 questions about separately written, blind-verified synthetic headlines it reaches 0.009.
The weights and full reports are published, but every TRACE-domain test set is synthetic, so we still treat
confidence as a routing signal rather than a real-world probability: a 0.6 gate suppresses weak events and
the anomaly flag escalates surprises. Say "benchmarked calibration," not "calibrated on real news."

**6c. "Why build Reflex instead of using Jev or a frontier LLM?"** — *Markandeya (S3)*
The taxonomy is dynamic — especially country options — but the task is classification, not generation.
Reflex starts from an open NLI encoder and scores each supplied option against the article, which preserves
that flexibility without paying for a frontier-model call on every story. Jev remains supported behind the
same interface, so the parity scale can compare the approaches instead of relying on marketing claims.

**7. "676 corridors isn't very many. Is that the whole global drug trade?"** — *Adrian (S4)*
It's the set we can evidence. The public UNODC seizure release gives country of seizure but not
departure/transit/destination — those are restricted-tier fields. So rather than invent routes, we
built the corridor table from UNODC's own published route maps and reports with a citation key per
row, then estimated yearly volumes by seizure-anchored allocation over real node totals. The route-evidence
API now separates 51 pairs stated directly in publications from 234 interpreted corridors and four narrative
claims; every edge exposes its evidence IDs and labels kilograms as allocated seizure scale, not an observed
pair-level volume. In the demo, click a corridor to open the UNODC or EUDA publication behind it. If richer
route-level data becomes available, it can replace the allocation for observed years without a rewrite.

**8. "Who would actually use this, and how is it different from what UNODC already publishes?"** — *William (S1)*
UNODC's Drugs Monitoring Platform is real and it is good. It operates under a tiered access policy,
and its own methodological annex says its routes are built by counting reported
departure/transit/destination fields and are "broadly indicative" only. It is a record, not a model: it
estimates no unobserved flow and forecasts nothing. We publish a forecast about next year, open, with the
vulnerability and harm-reduction layers joined on. The users are harm reduction organisations deciding
where naloxone and needle exchange go next, health ministries that would otherwise wait for surveillance
data, and journalists who currently reconstruct this by hand from annexes.

**9. "There's a paper from three weeks ago doing network modelling of cocaine trafficking and displacement. How is this different?"** — *Markandeya (S3)*
You mean Peters, Oetker, Roks, Lindelauf, Fokkink and Wang, arXiv 2609.26864, submitted 22 September. Yes —
they model cocaine flows over a transport network with an interception-risk metric and they reproduce the
waterbed effect under interdiction. That's genuinely close to our corridor layer and our shock simulator,
and we'd be foolish to claim otherwise. What they don't do is forecast forward in time, touch health
outcomes, or score countries. Our contribution isn't the network — it's joining the network to
development indicators and harm-reduction coverage to say where the *harm* lands.

**10. "How is this different from GI-TOC's Global Organized Crime Index?"** — *Adrian (S4)*
The OC Index is one of our inputs — we use its market scores in our corridor confidence. It's
expert-assessed, contemporaneous, and it scores how present a criminal market *is* today across 193
countries. We forecast the risk of a market a country doesn't have yet, from the corridor moving toward
it, and our third column is health-service coverage rather than governance resilience. Different
question, different time direction.

**11. "Your opening number is wrong — Afghanistan wasn't 95% of world supply."** — *William (S1)*
Agreed, and that's why we don't say it. The 95% is the fall in Afghan *production* between 2022 and 2023,
6,200 tonnes to 333. Afghanistan was about 80% of world illicit opium before the ban, so the global
production effect is roughly three quarters — and the effect on *supply* was smaller still and slower,
because an estimated 12,000 tonnes of stockpiled opium kept moving. UNODC expects those stocks to last to
around end-2026; David Mansfield disputes that. That gap between a production shock and a supply shock is
one of the things a route model is for.

**12. "Where did the opium actually go? Isn't the Southeast Asia story overstated?"** — *Markandeya (S3)*
Fair challenge, and worth separating. Myanmar is the world's leading producer again (1,010 t in 2025), but
UNODC attributes that mainly to internal conflict, not Afghan displacement — Myanmar's increase offsets
under 4% of Afghanistan's loss. UNODC treats a Southeast Asian route shift as an expectation, not a
measurement. The model predicted a 14% Southeast Asian share; our later-data corridor allocation is 13%,
not a UN figure, and we say so on the slide. The more
striking relocation is next door: over 9,000 hectares appeared in Pakistan's Balochistan in 2025, in a
place UNODC does not survey at all. That is precisely the blind spot we built this to see.

**13. "Is Afghanistan rebounding?"** — *Markandeya (S3)*
Not in the UN data. 2025 was 10,200 hectares and 296 tonnes, down again, which UNODC credits to sustained
enforcement *and* drought — so it isn't a clean policy contrast. The composition flipped completely: the
north-east now out-grows the south-west, which was 169,791 hectares in 2022. For the 2026 season the only
figures are Alcis and Mansfield, not UNODC, whose surveys publish in November, and they show Helmand
roughly doubling. If a judge raises 2026, say the UN data isn't out yet.

**14. "Is there any evidence that targeting harm reduction actually works better than not targeting it?"** — *Adrian (S4)*
This is the hardest question you can ask us, and the honest answer is no — not yet, on a mortality endpoint.
The HEALing Communities Study, 67 communities, the largest addiction prevention trial ever run, found no
statistically significant reduction in overdose deaths from a data-driven community-targeted intervention.
There is rich modelling support — Irvine in Lancet Public Health found no US state reaches naloxone
saturation, with need varying from zero to 1,270 kits per 100,000 depending on the epidemic — and there is
an RCT of predictive targeting, PROVIDENT in Rhode Island, whose results we have not read. So we do not
claim predictive placement is proven. What we claim is narrower and still true: cost per HIV infection
averted varies more than fivefold across settings, only five countries have high coverage of both core
services, and the decision about where the next service goes is currently made without any forecast at all.
Blind placement is not a validated alternative — it is just the status quo.

**15. "In the places that need this most, the constraint is legal, not informational. What good is a map?"** — *William (S1)*
Correct, and it's the sharpest objection to the whole product. Opioid agonist therapy is banned in Russia,
which has around 1.3 million people who inject drugs. Queensland banned drug checking in 2025. A US
executive order in July 2025 threatened penalties against harm reduction services. A forecast does not move
any of that. Two honest responses: first, the tool is most useful precisely where services are legal but
scarce, which is most of the world; second, evidence of where harm is heading is an input to the legal
argument, not a substitute for it. We would rather be the thing an advocate cites than pretend we are the
thing that changes the law.

**16. "Your README claims the model called 9 of 13 corridors, but your own Experiment screen says the Afghan data does not establish a route shift. Which is it?"** — *Markandeya (S3)*
Both, and the distinction is the point. The 9 of 13 is model output from a held-out shock test: train through
2021, inject the cultivation collapse, see which corridors the model moves and in which direction. The
Experiment screen is reporting *observations*, and published cultivation figures on their own cannot establish
that heroin physically rerouted between two countries — so the product refuses to say they do. We would
rather have a UI that under-claims than a slide that over-claims. If you want the forecast evidence, it is the
backtest: 0.88 AUC against 0.58 for the standard gravity baseline, on held-out years.

---

## Also plausible

**"Why a terminal interface? Isn't that a gimmick?"** — *Ismail (S2)*
Density and keyboard speed. The people who need this are comparing countries, years and drugs in
sequence, and a click-through dashboard makes that slow. It's also honest about what the tool is: an
instrument, not a consumer app.

**"Why does a harm-reduction product have a People tab — isn't that an enforcement tool?"** — *William (S1)*
It is a source-bounded research appendix, not operational intelligence and not an input to any forecast or
risk score. Every person, event and connection is a claim from a linked public source; allegations, charges,
convictions and sanctions remain distinct. Geography stops at documented country associations. There are no
live positions, private addresses, travel patterns, local routes or rankings of who to target. We included it
so users can audit the public context behind organizations named in reports. If that boundary cannot be kept
in a deployment, the People view should be removed rather than repurposed for enforcement.

<!-- people:auto -->
Know the mix before you answer the follow-up. As of the 2026-09-27 build it is **3,099 people across 229 organizations — 2,031 convicted, 456 charged, 536 sanctioned** (an official designation, usually OFAC) **and 76 carried only as reported**. Two things to say in that order. First, about 98% rest on an official action: a court, an indictment or a Treasury listing. Second, the honest concession before a judge finds it — most entries are convicted, but a large minority are only charged, and the 76 reported rest on journalism rather than any official determination. Each carries its source and its status is shown on the record rather than flattened into "trafficker".

These figures regenerate on every `python3 deck/build.py`; the dataset has grown fast, so rebuild before judging rather than trusting a number typed by hand.
<!-- /people:auto -->

The production People API now refreshes from GitHub `main` every ten minutes and reports its origin and
fetch time in `meta.people_snapshot`; the frontend-served API can still lag behind it. Before judging,
compare both live totals with the repository manifest. Treat the manifest as authoritative until the
surfaces converge, and do not quote a stale deployed total as the complete atlas.

**"Are the small city-scale arrows observed trafficking routes?"** — *Ismail (S2)*
No. They are a clearly labelled, map-only density layer derived from modeled corridor entry countries,
Natural Earth cities, population, World Bank GDP per capita PPP and great-circle distance. They use no
enforcement variables, stop at 1,500 km, and are not evidence, route endpoints, forecast inputs or risk-score
inputs. If a judge reads them as observed local movement, turn the layer off and show the cited country-level
corridors instead.

**"Prices are still five times pre-ban, right?"** — *Adrian (S4)*
That was true as of UNODC's November 2025 figure — US$570/kg dry opium against a pre-ban average under
US$100. Say "as of 2025"; Alcis reported prices falling back toward 2023 levels during 2026.

**"What's your data licensing situation?"** — *Adrian (S4)*
World Bank Indicators API is open. UNODC, GI-TOC, Harm Reduction International and CEPII are public
publications, cited per source with links in `docs/DATA_SOURCES.md` and surfaced in the API's `meta`
responses. We don't redistribute raw third-party files — the pipeline downloads them.

**"How much of this did AI write?"** — *Adrian (S4)*
Substantial parts, and we cite it as the rules require: an AI-assisted header comment in every file it
touched plus a dated log in `docs/AI_USAGE.md`. We also cite the statistical methods — PPML from Santos
Silva and Tenreyro, LightGBM from Ke et al., SHAP from Lundberg and Lee.

**"What's not built yet?"** — *whoever is asked*
The core product is built and live: the map, country and risk views, simulator, Live Wire, Markets, Health,
People and source drilldowns all ship. What remains is validation and deployment work, not a hidden missing
screen: team-label real headlines and run external Reflex validation; add the fentanyl and ACLED feeds;
then test service placement with a harm-reduction partner. Verify the hosted frontend against current `main`
before judging because a deployment can lag the repo even when the feature is complete.

**"What happens if GDELT is down during the demo?"** — *Markandeya (S3)*
It has been, from our network — it returns 429s. The poller keeps GDELT's rate spacing and retries,
and while it's unavailable the Live Wire replays a labelled sample set, clearly marked in `/api/meta`
as fallback and never counted as news evidence on a corridor. Degrading visibly beats pretending.

**"How would you validate Reflex's accuracy?"** — *Markandeya (S3)*
The eight-level Reflex Parity Scale checks the interface and output contract, held-out competence,
zero-shot generalisation, calibration, structured inputs, Live Wire field accuracy, known failure modes,
and CPU speed. The v0.1 and v0.2 reports are checked in and the v0.2 release bundles its evaluation; the
results are deliberately mixed rather than flattened into one score. Reflex passes interface, competence,
calibration, structure, jaggedness documentation and speed, but fails the zero-shot and full TRACE-domain
parity thresholds. The bundled 100-headline set is synthetic with provisional labels, so before deployment
we will hand-label real GDELT stories and report each field separately, especially origin and destination.
