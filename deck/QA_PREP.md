<!-- AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md. -->
# Q&A prep — 2 minutes, four people, no freezing

Rules of engagement: **whoever owns the section owns the question.** If a question lands in nobody's
lane, Adrian (S4) takes it. Answer in two sentences, then stop. A short confident answer beats a long
hedged one, and a judge who wants more will ask again.

If you genuinely do not know: *"We didn't test that. Here's what we did test, and here's how we'd test
that next."* Never invent a number on stage — every figure below is in the repo.

---

## The ten they are most likely to ask

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
IDs, paginated, nulls preserved, with provenance recorded per value.

**4. "Your spillover hypothesis failed. Doesn't that undercut the project?"** — *Adrian (S4)*
It's the finding, not a failure, and the literature lands in the same place. A 2026 panel of 95 countries
in the European Journal on Criminal Policy and Research finds the cocaine–homicide association shows up in
random effects but not fixed effects — the link is structural position on a trafficking corridor, not
within-country variation over time. Our national, level-based test was asking the question that study
says comes up null. The causal work that does find route effects — Dell's 2015 AER paper on Mexican
route diversion, Castillo, Mejía and Restrepo in REStat on Colombian supply shocks — identifies
*transitions and shocks*, sub-nationally, not steady-state exposure at country level. So: exposure alone
isn't destiny, exposure without protection is, and that's why the risk score has three columns. A team
that only reports the results that worked is a team you should trust less.

**5. "AUC 0.92 sounds high. Are you leaking future information?"** — *Markandeya (S3)*
Strict temporal split: trained through 2019, evaluated on 2020–2024, no target-derived features, and
lagged volume is last year's value only. The gravity baseline runs on the identical splits and gets
0.61, which is the sanity check — if we were leaking, the baseline would be inflated too. The Afghan
test is stronger evidence still: trained through 2021, shocked, and checked against data the model
never saw.

**6. "What does Jev actually add over a normal LLM?"** — *Markandeya (S3)*
Typed, calibrated decisions rather than text. For a newswire we need `event_type`, `drug`, `origin`,
`transit`, `destination`, `size` as structured fields with probabilities attached, at 70–500ms, across
a constant stream. We pin `jev-1.13.0`, discard anything under 0.6 confidence, and never let it touch
dates or arithmetic — those are known weaknesses, so dates come from GDELT metadata. The classifier
sits behind an interface with a mock implementation, so the real key drops in without touching
anything downstream.

**7. "676 corridors isn't very many. Is that the whole global drug trade?"** — *Adrian (S4)*
It's the set we can evidence. The public UNODC seizure release gives country of seizure but not
departure/transit/destination — those are restricted-tier fields. So rather than invent routes, we
built the corridor table from UNODC's own published route maps and reports with a citation key per
row, then estimated yearly volumes by seizure-anchored allocation over real node totals. The loader
for the full route-level release is already written: if we get access, it replaces the allocation for
observed years and the corridor count grows without a rewrite.

**8. "Who would actually use this, and how is it different from what UNODC already publishes?"** — *William (S1)*
UNODC's Drugs Monitoring Platform is real and it is good — but it is login-gated under a tiered access
policy, and its own methodological annex says its routes are built by counting reported
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

---

## Also plausible

**"Why a terminal interface? Isn't that a gimmick?"** — *Ismail (S2)*
Density and keyboard speed. The people who need this are comparing countries, years and drugs in
sequence, and a click-through dashboard makes that slow. It's also honest about what the tool is: an
instrument, not a consumer app.

**"What's your data licensing situation?"** — *Adrian (S4)*
World Bank Indicators API is open. UNODC, GI-TOC, Harm Reduction International and CEPII are public
publications, cited per source with links in `docs/DATA_SOURCES.md` and surfaced in the API's `meta`
responses. We don't redistribute raw third-party files — the pipeline downloads them.

**"How much of this did AI write?"** — *Adrian (S4)*
Substantial parts, and we cite it as the rules require: an AI-assisted header comment in every file it
touched plus a dated log in `docs/AI_USAGE.md`. We also cite the statistical methods — PPML from Santos
Silva and Tenreyro, LightGBM from Ke et al., SHAP from Lundberg and Lee.

**"What's not built yet?"** — *whoever is asked*
Answer plainly, then redirect to the demo. Check `README.md`'s status table the morning of judging so
the answer is current — and don't claim more than it says.

**"What happens if GDELT is down during the demo?"** — *Markandeya (S3)*
It has been, from our network — it returns 429s. The poller keeps GDELT's rate spacing and retries,
and while it's unavailable the Live Wire replays a labelled sample set, clearly marked in `/api/meta`
as fallback and never counted as news evidence on a corridor. Degrading visibly beats pretending.

**"How would you validate Jev's accuracy?"** — *Markandeya (S3)*
Hand-labelled evaluation set, per-field accuracy reported. That harness exists in the repo now and
runs against the mock; it runs against the real model the day the key arrives.
