<!-- AI-assisted: written with Claude Code (Anthropic) for Ismail Gasmi. See docs/AI_USAGE.md. -->
# Pitch suggestions for Adrian (from Ismail)

Suggestions only. Nothing in `deck/content.json` was changed. Take what fits. Every number below has a script and a result file in `evidence/`, and caveats are listed next to each claim.

## 1. The story Ismail wants to tell (section S2, "The Idea")

> For decades, drugs have flowed in the same direction: from producers in the Andes and Asia toward the world's richest markets. The routes in between keep changing. Colombia's cocaine moved through Ecuador, and Afghanistan's ban shifted heroin to Myanmar. The countries at the end of the line are not where the violence is. The countries along the way are. They inherit the violence and a drug problem of their own: countries on cocaine routes now use more cocaine than the destination countries, and 3.5× more than countries off the routes. TRACE tracks these routes and predicts where they will move next, so prevention and treatment can reach those countries before the harm does.

It fits after the `reframe` slide ("Where does the harm land next?"), as one evidence slide. A drop-in version in the deck's block format is in `slides_suggested.json`; `preview_same-direction.png` shows it rendered by `deck/build.py` in a scratch copy (1600×900).

## 2. Numbers to update anywhere they appear (backend retrained on SQLite v2, commit 7f804a5)

| Old | Current | Source |
|---|---|---|
| Route model AUC 0.92 | **0.88** (gravity baseline 0.58) | `README.md`, `backend/README.md` |
| Afghan ban: 12 of 14 corridors | **9 of 13** corridors; Southeast Asia share **13.9% predicted vs 13.4% actual** | same |

Suggested line: *"After the Afghan ban, the model predicted Southeast Asia's share of the heroin trade to within half a percentage point."*

## 3. Claims that hold up (all countries unless noted)

| Claim | Evidence | Caveat |
|---|---|---|
| Route countries have far more cocaine use than off-route countries | Past-year adult use, median **1.52%** on cocaine routes vs **0.43%** off-route (**3.5×**); still significant after income adjustment, p = 7e-5. Route countries also exceed destination countries (1.52% vs 1.06%). `results/health_by_role.csv` | 14 transit countries have survey data; latest year per country; cross-sectional, so it cannot show which came first. Routes = the 234 documented UNODC corridors in `backend/trace_backend/seed/corridors.csv`. Prevalence = UNODC WDR 2026 annex 1.2 (SQLite v2). |
| Same for opiates | **0.45%** vs **0.14%** (3×), p = 0.003 after income | Same limits |
| Violence sits on the routes, not at the destinations | Median homicide **3.0 per 100k** in route countries vs **1.2** in destination-only countries (2.5×), p = 0.03 | World Bank `VC.IHR.PSRC.P5`, 2015–2023 mean. General-population homicide, not drug-attributed. |
| Routes follow trade ties between specific countries | Among 3,314 trading pairs between countries that have at least one corridor (out of 18,016 trading pairs), a documented corridor is about **4× more likely per standard deviation of log bilateral trade**, after holding both countries fixed (p < 1e-14); shared borders also matter. `results/trade_full_results.csv` | UN Comtrade 2019, 137 reporting exporters (US, Spain, UK, Thailand, Turkey, Venezuela, Vietnam still missing). Busier trade lanes may also get more documented. Country-pair level only. |
| Ecuador shows what becoming a route country looks like | Homicides **6.5 → 45.7 per 100k (2015 → 2023)**, container port traffic +40%, poverty flat. `results/snapshot_ECU.csv` | One country; context, not proof. |
| Producers are unstable, not simply poor | Rule of law, political stability, refugees, homicide and inequality differ (p < 0.05); GDP per capita and poverty do not. Producers also lost 1.5 pp of forest 2011–21 vs ~0 elsewhere (p = 0.01). `results/agri_producer_profile.csv` | Only 7 producer countries. |

## 4. Wording to avoid

- **"Destination countries never face the aftermath."** Judges will cite the US overdose crisis, which is in our own frontend. Also, across all countries, destinations do **not** clearly spend more on health than route countries ($531 vs $385 per person, p = 0.24). The 3–4× health-spending gap only appears in the 20-country sample, which is dominated by the US and Western Europe. Safer: *"The biggest consumer markets have the health systems to treat addiction and do not live with the trafficking violence."*
- **"Always."** Use "carry a disproportionate share." The team's fixed-effects model found no within-country seizure–homicide link.
- **"Reduce the effects"** without a mechanism. Name it: prevention and treatment placed where a route is moving, before local use grows.

## 5. Tested and not supported (useful for Q&A)

- Legal crop prices do not predict coca or opium (coffee vs coca r = −0.02). `results/agri_price_vs_cultivation.csv`
- HIV among people who inject and treatment coverage do not differ clearly by route role (small samples; coverage is mostly modeled). `results/health_by_role.csv`

## Evidence files

`evidence/` holds the scripts (`roles.py`, `analysis.py`, `agri.py`, `trade.py`, `trade_full.py`, `health_roles.py`) and `events.json` (18 hand-checked historical events with source links, for a route-history panel). They read the team's SQLite v2 release and data pulled from the World Bank API, the World Bank Pink Sheet and UN Comtrade. Scripts were run outside the repo and have hard-coded local paths, so treat them as a record of the method rather than a pipeline stage.
