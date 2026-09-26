# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Reflex training and evaluation data (docs/REFLEX_SPEC.md section 4). Everything is free and reproducible.

Every example becomes a System One request: a state, one question (Choice / Score / Noul) whose wording is varied,
options shuffled and sometimes structured, and the index of the correct option.

- General tasks (Hugging Face, openly licensed): BoolQ, MultiNLI (Noul); AG News, DBpedia-14, Yahoo Answers topics
  (Choice); Yelp reviews (Score). Held out entirely for zero-shot tests: RTE (Noul), Emotion (Choice), SST-5 (Score).
- TRACE domain: news-style headlines generated from real UNODC IDS seizure records in the SQLite archive (real
  country, city, drug, quantity, place, transport mode), with routes drawn from the cited corridor table and
  non-seizure event variants. Labels are exact by construction. The 100-headline Live Wire eval set (written
  separately) is used only for testing.
"""
from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, dataclass

from .. import config
from .types import Choice, Noul, NoulCriteria, Score

OUT = config.DATA / "reflex"
RNG_SEED = 20260926


@dataclass
class Example:
    task: str
    prim: str
    state: object
    instructions: object
    criteria: object
    gold: int          # index into option order (Noul: 0 = yes, 1 = no)
    split: str

    def question(self):
        if self.prim == "choice":
            return Choice(self.instructions, dict(self.criteria))
        if self.prim == "score":
            return Score(self.instructions, list(self.criteria))
        c = self.criteria or {}
        return Noul(self.instructions, NoulCriteria(c.get("true"), c.get("false")) if c else None)

    def to_json(self):
        d = asdict(self)
        if self.prim == "choice":
            d["criteria"] = [[k, v] for k, v in self.criteria.items()]
        return d

    @classmethod
    def from_json(cls, d):
        if d["prim"] == "choice":
            d = {**d, "criteria": {k: v for k, v in d["criteria"]}}
        return cls(**d)


def _words(s: str, n: int) -> str:
    w = s.split()
    return " ".join(w[:n]) + (" ..." if len(w) > n else "")


def _choice(task, state, instr, opts: list[tuple[str, object]], gold_key, split, rng, k_max=None, other=False):
    """Build a Choice with shuffled (optionally sub-sampled) options; gold is always kept."""
    opts = list(opts)
    if k_max and len(opts) > k_max:
        gold = [o for o in opts if o[0] == gold_key]
        rest = [o for o in opts if o[0] != gold_key]
        opts = gold + rng.sample(rest, k_max - 1)
    if other and rng.random() < 0.15:
        opts.append(("other", "None of the other options fits"))
    rng.shuffle(opts)
    crit = {k: v for k, v in opts}
    return Example(task, "choice", state, instr, crit, [k for k, _ in opts].index(gold_key), split)


# ------------------------------------------------------------------ general tasks
def _load(name, config_=None, split="train"):
    import os

    from datasets import load_dataset
    os.environ.setdefault("HF_HOME", str(OUT / "hf"))
    return load_dataset(name, config_, split=split)


def boolq(n, rng, split):
    d = _load("google/boolq", split="train" if split != "test" else "validation")
    rows = [r for r in d if len(r["passage"].split()) <= 90]
    rng.shuffle(rows)
    out = []
    for r in rows[:n]:
        q = r["question"].strip().rstrip("?") + "?"
        q = q[0].upper() + q[1:]
        crit = rng.choice([None, None, {"true": "The passage says or clearly implies yes",
                                        "false": "The passage says no or does not support it"}])
        state = r["passage"] if rng.random() < 0.7 else {"passage": r["passage"]}
        instr = q if isinstance(state, str) else f"Based on `passage`: {q}"
        out.append(Example("boolq", "noul", state, instr, crit, 0 if r["answer"] else 1, split))
    return out


def mnli(n, rng, split):
    d = _load("nyu-mll/multi_nli", split="train" if split != "test" else "validation_matched")
    idx = rng.sample(range(len(d)), min(len(d), n * 3))
    out = []
    for i in idx:
        r = d[i]
        if r["label"] not in (0, 1, 2) or len(r["premise"].split()) > 80:
            continue
        tmpl = rng.choice(["Is it true that {h}", "Does the text support this statement: {h}", "{h}",
                           "Judge the statement: {h}"])
        crit = rng.choice([None, {"true": "The text states or clearly implies it",
                                  "false": "The text contradicts it or gives no indication"}])
        out.append(Example("mnli", "noul", r["premise"], tmpl.format(h=r["hypothesis"].strip()), crit,
                           0 if r["label"] == 0 else 1, split))
        if len(out) >= n:
            break
    return out


AG = {"World": "World news, politics, international affairs", "Sports": "Sport, games, athletes, competitions",
      "Business": "Business, companies, markets, the economy", "Sci/Tech": "Science and technology"}
DBP = ["Company", "EducationalInstitution", "Artist", "Athlete", "OfficeHolder", "MeanOfTransportation", "Building",
       "NaturalPlace", "Village", "Animal", "Plant", "Album", "Film", "WrittenWork"]
DBP_DESC = {"Company": "a business or company", "EducationalInstitution": "a school, college or university",
            "Artist": "an artist, musician or writer", "Athlete": "a sportsperson", "OfficeHolder": "a politician or official",
            "MeanOfTransportation": "a vehicle, ship, aircraft or train", "Building": "a building or structure",
            "NaturalPlace": "a mountain, river, lake or other natural place", "Village": "a village or small settlement",
            "Animal": "an animal species", "Plant": "a plant species", "Album": "a music album", "Film": "a film",
            "WrittenWork": "a book, journal or other written work"}
YAHOO = ["Society & Culture", "Science & Mathematics", "Health", "Education & Reference", "Computers & Internet",
         "Sports", "Business & Finance", "Entertainment & Music", "Family & Relationships", "Politics & Government"]


def ag_news(n, rng, split):
    d = _load("fancyzhx/ag_news", split="train" if split != "test" else "test")
    names = d.features["label"].names
    out = []
    for i in rng.sample(range(len(d)), n):
        r = d[i]
        gold = names[r["label"]]
        opts = [(k, v if rng.random() < 0.7 else None) for k, v in AG.items()]
        instr = rng.choice(["What is this news article about?", "Which section of a newspaper does this belong in?",
                            "What is the topic of the text?"])
        out.append(_choice("ag_news", r["text"], instr, opts, gold, split, rng, other=True))
    return out


def dbpedia(n, rng, split):
    d = _load("fancyzhx/dbpedia_14", split="train" if split != "test" else "test")
    out = []
    for i in rng.sample(range(len(d)), n):
        r = d[i]
        gold = DBP[r["label"]]
        opts = [(k, DBP_DESC[k] if rng.random() < 0.8 else None) for k in DBP]
        state = {"title": r["title"], "description": _words(r["content"], 60)}
        instr = rng.choice(["What kind of entity is `title`?", "What is the subject of this encyclopedia entry?"])
        out.append(_choice("dbpedia", state, instr, opts, gold, split, rng, k_max=rng.choice([4, 5, 14])))
    return out


def yahoo(n, rng, split):
    d = _load("community-datasets/yahoo_answers_topics", split="train" if split != "test" else "test")
    out = []
    for i in rng.sample(range(len(d)), n * 2):
        r = d[i]
        text = f"{r['question_title']} {r['question_content']}".strip()
        if len(text.split()) < 4:
            continue
        gold = YAHOO[r["topic"]]
        instr = rng.choice(["Which category does this question belong to?", "What topic is the user asking about?"])
        state = text if rng.random() < 0.6 else {"question": _words(text, 60), "best_answer": _words(r["best_answer"], 40)}
        out.append(_choice("yahoo", state, instr, [(k, None) for k in YAHOO], gold, split, rng,
                           k_max=rng.choice([4, 5, 10])))
        if len(out) >= n:
            break
    return out


YELP_LEVELS = [
    ["Very negative: the customer had a bad experience and would not return",
     "Mostly negative: more complaints than praise",
     "Mixed or neutral: good and bad points roughly balance",
     "Mostly positive: a good experience with minor complaints",
     "Very positive: an excellent experience, strongly recommended"],
    [{"what": "Terrible", "examples": ["awful service", "never again"]},
     {"what": "Poor", "examples": ["disappointing", "not worth it"]},
     {"what": "Average", "examples": ["it was okay", "nothing special"]},
     {"what": "Good", "examples": ["would come back", "tasty"]},
     {"what": "Excellent", "examples": ["best in town", "amazing"]}],
]


def yelp(n, rng, split):
    d = _load("Yelp/yelp_review_full", split="train" if split != "test" else "test")
    out = []
    for i in rng.sample(range(len(d)), n * 3):
        r = d[i]
        if len(r["text"].split()) > 90:
            continue
        instr = rng.choice(["How satisfied is the reviewer?", "What is the overall sentiment of this review?",
                            "How would the reviewer rate the business?"])
        out.append(Example("yelp", "score", r["text"], instr, rng.choice(YELP_LEVELS), r["label"], split))
        if len(out) >= n:
            break
    return out


# ------------------------------------------------------------------ zero-shot test tasks (never trained on)
def rte(n, rng):
    d = _load("nyu-mll/glue", "rte", split="validation")
    out = []
    for r in list(d)[:n]:
        out.append(Example("rte", "noul", r["sentence1"], f"Is it true that {r['sentence2']}", None,
                           0 if r["label"] == 0 else 1, "zeroshot"))
    return out


EMO = {"sadness": "The writer feels sad, down or hurt", "joy": "The writer feels happy or glad",
       "love": "The writer feels love, affection or tenderness", "anger": "The writer feels angry or irritated",
       "fear": "The writer feels afraid, anxious or nervous", "surprise": "The writer feels surprised or amazed"}


def emotion(n, rng):
    d = _load("dair-ai/emotion", "split", split="test")
    names = d.features["label"].names
    return [_choice("emotion", r["text"], "Which emotion does the writer express?", list(EMO.items()),
                    names[r["label"]], "zeroshot", rng) for r in list(d)[:n]]


SST_LEVELS = ["Very negative about the film", "Negative about the film", "Neutral or mixed about the film",
              "Positive about the film", "Very positive about the film"]


def sst5(n, rng):
    d = _load("SetFit/sst5", split="test")
    return [Example("sst5", "score", r["text"], "What is the reviewer's opinion of the film?", SST_LEVELS,
                    int(r["label"]), "zeroshot") for r in list(d)[:n]]


# ------------------------------------------------------------------ TRACE domain (from real IDS seizure records)
EVENT_TYPES = {
    "seizure": "Drugs were seized, intercepted, found or confiscated",
    "arrest_or_indictment": "People were arrested, charged, extradited, convicted or sentenced",
    "lab_dismantled": "A drug laboratory or production site was raided or dismantled",
    "law_or_policy_change": "A law, regulation, ban, court ruling or policy on drugs changed or was proposed",
    "violence": "Killings, shootings, clashes or attacks linked to the drug trade",
    "corruption": "Officials took bribes or protected traffickers",
    "other": "None of the above: research, statistics, commentary, or not about a drug event",
}
DRUG_OPTS = {"cocaine": "Cocaine, crack or coca paste", "heroin": "Heroin, opium or other opiates",
             "meth": "Methamphetamine, crystal meth, yaba or ice", "cannabis": "Cannabis, marijuana or hashish",
             "fentanyl": "Fentanyl or other synthetic opioids", "other": "Another drug such as ketamine, captagon, tramadol or ecstasy",
             "unclear": "No specific drug is named"}
SIZE_LEVELS = ["Small: personal or street-level amount, under about 100 kg or a few thousand pills",
               "Notable: hundreds of kilograms, up to about a tonne",
               "Major: tonnes or millions of pills",
               "Record: described as a record, the largest ever, or unprecedented"]
DRUG_WORDS = {"cocaine": ["cocaine", "cocaine", "coke", "crack cocaine", "cocaine paste"],
              "heroin": ["heroin", "heroin", "opium", "opiates"],
              "meth": ["methamphetamine", "crystal meth", "meth", "yaba pills", "methamphetamine tablets"],
              "cannabis": ["cannabis", "marijuana", "hashish", "cannabis resin", "weed"],
              "fentanyl": ["fentanyl", "fentanyl pills"],
              "other": ["ketamine", "captagon pills", "tramadol", "ecstasy pills"]}
AUTH = ["police", "customs officers", "border guards", "the navy", "anti-narcotics agents", "the coast guard",
        "federal agents", "authorities"]
PLACE = {"Airport": "at the airport", "Seaport/Riverport station/Harbour": "at the port",
         "Road/ Street/highway": "on a highway", "Post Office": "in a postal parcel",
         "Private dwelling/Residence/Home/Private Garage": "in a house", "Warehouse": "in a warehouse",
         "Territorial waters (seas, lakes, rivers, etc.)": "at sea", "Commercial premises": "in a shop"}
MODE = {"Airplane": "on a flight", "Vessel/boat": "aboard a boat", "Truck/lorry/van": "in a truck",
        "Car/motorcycle": "in a car", "Postal/Mail/Express Parcel": "in a parcel", "Train/Bus": "on a bus"}
NON_EVENT = [
    "Study finds {dw} use rising among young adults in {C}",
    "Opinion: {C} needs a public health approach to {dw}",
    "UN report tracks global {dw} market trends",
    "{C} central bank holds interest rates steady",
    "Heatwave pushes temperatures to record highs in {city}",
    "{C} beat their rivals 2-1 in World Cup qualifier",
    "Treatment centres in {C} report more demand for {dw} services",
    "Documentary follows families affected by {dw} in {C}",
]


def _fmt_qty(kg: float, drug: str, rng) -> tuple[str, str]:
    if drug == "meth" and rng.random() < 0.3:
        pills = int(kg / 0.0001)
        if pills >= 1_000_000:
            return f"{pills / 1e6:.1f} million meth pills".replace(".0 ", " "), "major" if pills >= 1_000_000 else "notable"
        return f"{pills:,} meth pills", "small" if pills < 50_000 else "notable"
    if kg >= 1000:
        t = kg / 1000
        s = f"{t:.1f} tonnes" if t < 10 else f"{t:.0f} tonnes"
        return s, "major" if kg >= 1500 else "notable"
    if kg >= 100:
        return f"{kg:,.0f} kg", "notable"
    if kg >= 1:
        return f"{kg:,.0f} kg" if kg >= 10 else f"{kg:.1f} kg", "small"
    return f"{kg * 1000:,.0f} grams", "small"


def _names(countries):
    from ..jev.mock import DEMONYMS
    dem = {}
    for k, v in DEMONYMS.items():
        if len(k) > 3 and k.isalpha():
            dem.setdefault(v, k.title())
    short = {c["iso3"]: re.sub(r",.*$|\(.*?\)", "", c["name"]).strip() for c in countries}
    fix = {"USA": "the United States", "GBR": "the United Kingdom", "NLD": "the Netherlands", "IRN": "Iran",
           "VEN": "Venezuela", "RUS": "Russia", "LAO": "Laos", "KOR": "South Korea", "EGY": "Egypt", "SYR": "Syria",
           "TUR": "Turkey", "COD": "the Democratic Republic of Congo", "PHL": "the Philippines", "ARE": "the UAE"}
    short.update(fix)
    return short, dem


def trace_domain(n_headlines: int, rng, split: str, records=None, corridors=None, countries=None):
    from .. import db
    if countries is None:
        countries = db.read_table("countries").to_dict("records")
    short, dem = _names(countries)
    if records is None:
        records = db.query(
            "SELECT iso3, city, location, mode, drug, kg FROM archive.seizures_raw WHERE drug IS NOT NULL AND kg > 0 "
            "AND iso3 IS NOT NULL ORDER BY random() LIMIT 60000").to_dict("records")
        big = [r for r in records if r["kg"] >= 5]
        records = big + rng.sample(records, min(len(records), len(big) // 3))
    if corridors is None:
        corridors = db.read_table("corridors_seed").to_dict("records")
    by_to, by_from = {}, {}
    for c in corridors:
        by_to.setdefault((c["drug"], c["to_iso3"]), []).append(c["from_iso3"])
        by_from.setdefault((c["drug"], c["from_iso3"]), []).append(c["to_iso3"])
    iso_all = [c for c in short if c in {x["iso3"] for x in countries}]
    out = []
    recs = [r for r in records if r["iso3"] in short]
    rng.shuffle(recs)
    for r in recs[:n_headlines]:
        drug = r["drug"]
        if rng.random() < 0.08:
            drug = rng.choice(["fentanyl", "other"])
        dw = rng.choice(DRUG_WORDS[drug])
        loc = r["iso3"]
        C = short[loc]
        city = (r["city"] or "").split("/")[0].split(",")[0].strip()
        city = city if city and city != "Data not available" and len(city) < 25 else None
        place_c = f"{city}, {C}" if city and rng.random() < 0.5 else C
        auth = rng.choice(AUTH)
        who = f"{dem[loc]} {auth}" if loc in dem and rng.random() < 0.5 else f"{auth.capitalize()} in {place_c}"
        roll = rng.random()
        origin = dest = None
        route = False
        if roll < 0.62:  # seizure
            et = "seizure"
            qty, size = _fmt_qty(r["kg"] * rng.choice([1, 1, 1, 10, 100]) if r["kg"] < 50 else r["kg"], drug, rng)
            record = rng.random() < 0.05
            size = "record" if record else size
            where = PLACE.get(r["location"]) or MODE.get(r["mode"]) or ""
            o_cands = by_to.get((drug, loc), []) or (rng.sample(iso_all, 1) if rng.random() < 0.3 else [])
            d_cands = by_from.get((drug, loc), [])
            style = rng.random()
            route_txt = ""
            if style < 0.35 and o_cands:
                origin = rng.choice(o_cands)
                route_txt = rng.choice([f" from {short[origin]}", f" shipped from {short[origin]}",
                                        f" arriving from {short[origin]}", f" smuggled in from {short[origin]}"])
                dest = loc
            elif style < 0.6 and d_cands:
                dest = rng.choice(d_cands)
                origin = loc
                route_txt = rng.choice([f" bound for {short[dest]}", f" destined for {short[dest]}",
                                        f" headed to {short[dest]}"])
            else:
                dest = loc
            route = bool(route_txt)
            lead = "Record haul: " if record and rng.random() < 0.5 else ""
            big = "largest-ever " if record and not lead else ""
            text = rng.choice([
                f"{lead}{who} seize {qty} of {big}{dw}{(' ' + where) if where else ''}{route_txt}",
                f"{lead}{qty} of {dw} found {where or 'in a raid'} in {place_c}{route_txt}",
                f"{who} intercept {big}{dw} shipment{route_txt}; {qty} confiscated",
                f"{C}: {qty} {dw} haul{route_txt}",
                f"{who} confiscate {big}{dw} worth millions{route_txt}",
            ])
            if "worth millions" in text:
                size = "record" if record else ("notable" if size == "small" else size)
        elif roll < 0.92:
            et = rng.choice(["arrest_or_indictment", "arrest_or_indictment", "lab_dismantled", "law_or_policy_change",
                             "violence", "corruption"])
            size = "small"
            dest = loc
            k = rng.randint(2, 30)
            text = {
                "arrest_or_indictment": rng.choice([f"{who} arrest {k} suspected {dw} traffickers",
                                                    f"Court in {place_c} sentences {dw} smuggler to {k} years",
                                                    f"{who} charge {k} people in {dw} trafficking ring"]),
                "lab_dismantled": rng.choice([f"{who} dismantle clandestine {dw} laboratory",
                                              f"Secret {dw} lab raided near {city or C}"]),
                "law_or_policy_change": rng.choice([f"{C} lawmakers approve bill to regulate {dw}",
                                                    f"{C} toughens penalties for {dw} trafficking",
                                                    f"{C} court rules on {dw} possession law"]),
                "violence": rng.choice([f"Gunmen kill {k} in {dw} gang dispute in {place_c}",
                                        f"Clashes between drug gangs leave {k} dead in {place_c}"]),
                "corruption": rng.choice([f"Port officials in {place_c} arrested for taking bribes from {dw} smugglers",
                                          f"{C} police commander accused of protecting {dw} traffickers"]),
            }[et]
            if "drug gangs" in text and dw not in text:
                drug = "unclear"
        else:
            et, size = "other", "small"
            text = rng.choice(NON_EVENT).format(dw=dw, C=C, city=city or C)
            dest = None
            if not any(w in text for w in DRUG_WORDS[drug]):
                drug = "unclear"
        is_event = et != "other"
        mentioned = [loc] + [x for x in (origin, dest) if x and x != loc]
        headline = text[0].upper() + text[1:]
        state = headline if rng.random() < 0.8 else {"title": headline, "source": "newswire"}
        # questions (wording varied)
        out.append(Example("trace_is_event", "noul", state, rng.choice([
            "Does the article describe a specific drug seizure, arrest, lab raid, violence, corruption case or policy change?",
            "Is this a report of a specific drug-related event?"]), None, 0 if is_event else 1, split))
        out.append(_choice("trace_event_type", state, "What kind of event does the article report?",
                           list(EVENT_TYPES.items()), et, split, rng))
        out.append(_choice("trace_drug", state, "Which drug is mainly involved?", list(DRUG_OPTS.items()), drug,
                           split, rng))
        cands = list(dict.fromkeys(mentioned + rng.sample(iso_all, 2)))
        for field_, gold in (("origin", origin), ("destination", dest)):
            opts = [(short[c], None) for c in cands] + [("not_stated", "The article does not say")]
            gkey = short[gold] if gold else "not_stated"
            q = {"origin": "Which country did the drugs come from, according to the article?",
                 "destination": "Which country were the drugs seized in or going to, according to the article?"}[field_]
            if et == "other" and field_ == "destination":
                gkey = "not_stated"
            out.append(_choice(f"trace_{field_}", state, q, opts, gkey, split, rng))
        if et == "seizure":
            out.append(Example("trace_size", "score", state, "How large is the seizure?", SIZE_LEVELS,
                               ["small", "notable", "major", "record"].index(size), split))
        out.append(Example("trace_route", "noul", state,
                           "Does the article say where the drugs came from or were going?", None,
                           0 if route else 1, split))
    return out


# ------------------------------------------------------------------ build
PLAN = {  # task: (train, val, test)
    "boolq": (900, 120, 150), "mnli": (1100, 120, 150), "ag_news": (700, 100, 150), "dbpedia": (600, 100, 150),
    "yahoo": (600, 100, 150), "yelp": (900, 120, 150),
}
DOMAIN_HEADLINES = (900, 120, 150)


def build(scale: float = 1.0, seed: int = RNG_SEED) -> dict[str, int]:
    rng = random.Random(seed)
    OUT.mkdir(parents=True, exist_ok=True)
    fns = {"boolq": boolq, "mnli": mnli, "ag_news": ag_news, "dbpedia": dbpedia, "yahoo": yahoo, "yelp": yelp}
    splits = {"train": [], "val": [], "test": [], "zeroshot": []}
    for task, sizes in PLAN.items():
        tv = fns[task](int((sizes[0] + sizes[1]) * scale) + 1, rng, "train")
        rng.shuffle(tv)
        nv = int(sizes[1] * scale)
        for e in tv[:nv]:
            e.split = "val"
        splits["val"] += tv[:nv]
        splits["train"] += tv[nv:]
        splits["test"] += fns[task](int(sizes[2] * scale), rng, "test")
    for sp, n in zip(("train", "val", "test"), DOMAIN_HEADLINES, strict=True):
        splits[sp] += trace_domain(int(n * scale), rng, sp)
    zs = int(200 * scale)
    splits["zeroshot"] = rte(zs, rng) + emotion(zs, rng) + sst5(zs, rng)
    counts = {}
    for sp, ex in splits.items():
        (OUT / f"{sp}.jsonl").write_text("\n".join(json.dumps(e.to_json(), ensure_ascii=False) for e in ex), "utf-8")
        counts[sp] = len(ex)
    return counts


def load_split(split: str) -> list[Example]:
    lines = (OUT / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
    return [Example.from_json(json.loads(x)) for x in lines if x.strip()]


# ------------------------------------------------------------------ v0.2: headlines written and labelled by Claude
LLM_DIR = config.BACKEND / "trace_backend" / "reflex" / "llm_data"
EVENTS_ = set(EVENT_TYPES)
DRUGS_ = set(DRUG_OPTS)
SIZES_ = ["small", "notable", "major", "record"]


def _norm(t: str) -> str:
    return re.sub(r"\W+", " ", t.lower()).strip()


_QTY = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(tonnes?|tons?|metric tons?|kilograms?|kilos?|kgs?|kg|pounds|lbs?|grams?|g)\b",
                  re.I)
_UNIT_KG = {"t": 1000.0, "k": 1.0, "p": 0.4536, "l": 0.4536, "g": 0.001}


def normalise_size(r: dict) -> str:
    """One fixed size rule wherever a seizure states a weight (blind re-labelling showed boundary disagreements):
    record wording wins; otherwise < 100 kg small, 100 kg to < 1.5 t notable, >= 1.5 t major."""
    if r["event_type"] != "seizure":
        return r["size"]
    t = r["title"].lower()
    if re.search(r"\brecord\b|largest[- ]ever|biggest[- ]ever|unprecedented", t):
        return "record"
    m = _QTY.search(r["title"])
    if not m:
        return r["size"]
    val, unit = float(m.group(1).replace(",", "")), m.group(2).lower()
    kg = val * (1000.0 if unit.startswith(("tonne", "ton", "metric")) else _UNIT_KG.get(unit[0], 1.0))
    return "small" if kg < 100 else "notable" if kg < 1500 else "major"


def _disputed_titles() -> set[str]:
    """Titles where the blind re-labelling disagreed with the writer on any field: genuinely ambiguous, dropped."""
    tp, lp = LLM_DIR / "verify_round1_titles.jsonl", LLM_DIR / "verify_round1_labels.jsonl"
    if not (tp.exists() and lp.exists()):
        return set()
    titles = {json.loads(x)["id"]: json.loads(x)["title"] for x in tp.read_text("utf-8").splitlines() if x.strip()}
    labels = {json.loads(x)["id"]: json.loads(x) for x in lp.read_text("utf-8").splitlines() if x.strip()}
    gold = {}
    for f in LLM_DIR.glob("batch_*.jsonl"):
        for x in f.read_text("utf-8").splitlines():
            if x.strip():
                r = json.loads(x)
                gold[_norm(r["title"])] = r
    fields = ["is_event", "event_type", "drug", "origin", "destination", "size", "route_mentioned"]
    out = set()
    for i, t in titles.items():
        g, v = gold.get(_norm(t)), labels.get(i)
        if g and v and any(g[f] != v.get(f) for f in fields if f != "size"):
            out.add(_norm(t))
    return out


def load_llm_rows(countries: list[dict]) -> tuple[list[dict], dict]:
    """Validated rows from llm_data/batch_*.jsonl; drops malformed rows and anything overlapping the 100-headline
    Live Wire test set."""
    from ..api.livewire import load_eval
    codes = {c["iso3"] for c in countries}
    held = {_norm(r["title"]) for r in load_eval()}
    disputed = _disputed_titles()
    rows, seen = [], set()
    stats = {"read": 0, "bad": 0, "overlap_test": 0, "dupe": 0, "disputed_dropped": 0, "size_normalised": 0}
    for f in sorted(LLM_DIR.glob("batch_*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            stats["read"] += 1
            try:
                r = json.loads(line)
                ok = (isinstance(r["title"], str) and r["event_type"] in EVENTS_ and r["drug"] in DRUGS_
                      and r["size"] in SIZES_ and r["is_event"] in (0, 1) and r["route_mentioned"] in (0, 1)
                      and all(r[k] is None or r[k] in codes for k in ("origin", "destination")))
            except (ValueError, KeyError, TypeError):
                ok = False
            if not ok:
                stats["bad"] += 1
                continue
            k = _norm(r["title"])
            if k in disputed:
                stats["disputed_dropped"] += 1
                continue
            fixed = normalise_size(r)
            if fixed != r["size"]:
                stats["size_normalised"] += 1
                r["size"] = fixed
            if k in held:
                stats["overlap_test"] += 1
                continue
            if k in seen:
                stats["dupe"] += 1
                continue
            seen.add(k)
            r["batch"] = f.stem
            rows.append(r)
    stats["kept"] = len(rows)
    return rows, stats


def headline_examples(r: dict, rng, split: str, short: dict, iso_all: list[str], prefix: str = "llm"):
    from ..jev.mock import _find
    text = r["title"]
    state = text if rng.random() < 0.85 else {"title": text, "source": "newswire"}
    ev = [Example(f"{prefix}_is_event", "noul", state, rng.choice([
        "Does the article describe a specific drug seizure, arrest, lab raid, violence, corruption case or policy change?",
        "Is this a report of a specific drug-related event?"]), None, 0 if r["is_event"] else 1, split)]
    ev.append(_choice(f"{prefix}_event_type", state, "What kind of event does the article report?",
                      list(EVENT_TYPES.items()), r["event_type"], split, rng))
    ev.append(_choice(f"{prefix}_drug", state, "Which drug is mainly involved?", list(DRUG_OPTS.items()), r["drug"],
                      split, rng))
    found = [iso for _, iso in _find(text)]
    gold = [x for x in (r["origin"], r["destination"]) if x]
    cands = list(dict.fromkeys(found + gold + rng.sample(iso_all, 2)))[:8]
    for field_ in ("origin", "destination"):
        opts = [(short.get(c, c), None) for c in cands] + [("not_stated", "The article does not say")]
        gkey = short.get(r[field_], r[field_]) if r[field_] else "not_stated"
        q = {"origin": "Which country did the drugs come from, according to the article?",
             "destination": "Which country were the drugs seized in or going to, according to the article?"}[field_]
        ev.append(_choice(f"{prefix}_{field_}", state, q, opts, gkey, split, rng))
    if r["event_type"] == "seizure":
        ev.append(Example(f"{prefix}_size", "score", state, "How large is the seizure?", SIZE_LEVELS,
                          SIZES_.index(r["size"]), split))
    ev.append(Example(f"{prefix}_route", "noul", state, "Does the article say where the drugs came from or were going?",
                      None, 0 if r["route_mentioned"] else 1, split))
    return ev


def build_llm(seed: int = RNG_SEED) -> dict:
    """Write llm_{train,val,test}.jsonl (80/10/10 by headline, stratified by batch)."""
    from .. import db
    rng = random.Random(seed + 2)
    countries = db.read_table("countries").to_dict("records")
    short, _ = _names(countries)
    iso_all = sorted(short)
    rows, stats = load_llm_rows(countries)
    by = {}
    for r in rows:
        by.setdefault(r["batch"], []).append(r)
    out = {"llm_train": [], "llm_val": [], "llm_test": []}
    for _, rs in sorted(by.items()):
        rng.shuffle(rs)
        n = len(rs)
        cut1, cut2 = int(0.8 * n), int(0.9 * n)
        for sp, part in (("llm_train", rs[:cut1]), ("llm_val", rs[cut1:cut2]), ("llm_test", rs[cut2:])):
            for r in part:
                out[sp] += headline_examples(r, rng, sp.split("_")[1], short, iso_all)
    for sp, ex in out.items():
        (OUT / f"{sp}.jsonl").write_text("\n".join(json.dumps(e.to_json(), ensure_ascii=False) for e in ex), "utf-8")
    stats.update({sp: len(ex) for sp, ex in out.items()})
    return stats
