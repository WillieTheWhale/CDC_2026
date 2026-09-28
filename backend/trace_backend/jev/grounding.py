# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Grounding guardrails for Live Wire classifications: nothing is shown that the article text does not state.

Every classifier (Reflex, Jev, the keyword mock) answers from a headline. A model can still name a country or drug
that the text never mentions (a prior, not a reading). These guardrails check each answer against evidence found in
the text, in code:

- countries: a predicted origin, transit, destination or map location must be supported by the text: a country
  name or alias, a demonym, a US/Mexican/Australian/Canadian state or province, or a city or port clearly located
  in that country (Natural Earth 150k+ cities from `seed/estimated_flows_cities.csv` plus a curated list of ports
  and border towns). Unsupported countries become None ("not stated"), never a guess;
- drug: the predicted drug must be supported by a synonym list (cocaine: coke, crack, coca paste; meth: yaba,
  shabu, ice; ...). If not, the most probable *supported* option is used when the model gave probabilities,
  otherwise "unclear";
- size: only from an explicit quantity or record wording (`quantity.size_from_text`); otherwise `size_stated` is
  False and the UI shows "not stated";
- is_event: kept only above EVENT_THRESHOLD, only when the event type is not "other" (research, statistics or
  commentary by definition), and only when the text contains drug-trade vocabulary at all.

Thresholds are tuned on the synthetic validation headlines (reflex/llm_data, val split), never on the real-news
benchmark (`jev/data/real_headlines_v1.jsonl`), which stays held out for reporting.
"""
from __future__ import annotations

import csv
import json
import logging
import re
import unicodedata
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from .base import Classification
from .quantity import size_from_text

HERE = Path(__file__).resolve().parent
CITIES_CSV = HERE.parent / "seed" / "estimated_flows_cities.csv"

# Display cut shared by the Live Wire (tuned on synthetic validation data, see benchmark.tune_thresholds).
EVENT_THRESHOLD = 0.7  # synthetic val (295 headlines): recall 0.947, false events 0.030 at MIN_CONFIDENCE 0.6
MIN_CONFIDENCE = 0.6

# ------------------------------------------------------------------ drugs
DRUG_SYNONYMS: dict[str, list[str]] = {
    "cocaine": [r"cocaine", r"crack", r"coca paste", r"coca base", r"paste base", r"coke", r"cocaína", r"perico",
                r"basuco"],
    "heroin": [r"heroin", r"opium", r"opiates?", r"morphine", r"brown sugar", r"poppy straw", r"smack"],
    "meth": [r"methamphetamines?", r"meth", r"crystal meth", r"yaba", r"ya ba", r"shabu", r"(?-i:ice)", r"tik",
             r"crystal methamphetamine", r"methamphetamine hydrochloride", r"amphetamine-type stimulants?"],
    "cannabis": [r"cannabis", r"marijuana", r"marihuana", r"hashish", r"hash", r"weed", r"skunk", r"charas",
                 r"ganja", r"kush", r"THC", r"pot", r"cannabis resin", r"bhang"],
    "fentanyl": [r"fentanyls?", r"carfentanil", r"nitazenes?", r"synthetic opioids?", r"fentanyl-laced",
                 r"isotonitazene", r"protonitazene", r"acetylfentanyl", r"M30s?"],
    "other": [r"ketamine", r"captagon", r"tramadol", r"ecstasy", r"MDMA", r"LSD", r"GHB", r"khat", r"kratom",
              r"xylazine", r"cathinones?", r"mephedrone", r"MDA", r"amphetamines?", r"oxycodone", r"oxycontin", r"benzodiazepines?",
              r"alprazolam", r"diazepam", r"codeine", r"psilocybin", r"magic mushrooms", r"pregabalin", r"PCP",
              r"amphetamine-type stimulants?", r"precursor chemicals?", r"pseudoephedrine", r"ephedrine", r"synthetic cannabinoids?", r"spice",
              r"flakka", r"bath salts", r"nitrous oxide", r"poppers", r"ayahuasca", r"mescaline", r"peyote"],
}
# Drug-trade vocabulary: without any of it the text cannot report a drug-trade event.
TRADE_TERMS = (r"drugs?|narcotics?|narco|traffick\w*|smuggl\w*|cartels?|seiz\w*|bust\w*|haul|contraband|"
               r"dealers?|dealing|trafficker|gang|mules?|consignment|stash|laborator\w*|\blab\b|legali[sz]\w*|"
               r"decriminali[sz]\w*|substances?")


@lru_cache(maxsize=1)
def _drug_res() -> dict[str, re.Pattern]:
    return {d: re.compile(r"(?<![\w-])(?:" + "|".join(pats) + r")(?!\w)", re.I) for d, pats in DRUG_SYNONYMS.items()}


def supported_drugs(text: str) -> set[str]:
    """Drug categories the text names (by name, synonym, slang or chemical name)."""
    t = _fold(text)
    return {d for d, rx in _drug_res().items() if rx.search(t)}


def has_trade_vocabulary(text: str) -> bool:
    t = _fold(text)
    return bool(supported_drugs(t)) or bool(re.search(rf"(?<!\w)(?:{TRADE_TERMS})(?!\w)", t, re.I))


# ------------------------------------------------------------------ countries
ACRONYMS = {"US": ("USA",), "U.S.": ("USA",), "U.S": ("USA",), "USA": ("USA",), "U.S.A.": ("USA",),
            "UK": ("GBR",), "U.K.": ("GBR",), "UAE": ("ARE",), "DRC": ("COD",), "DR Congo": ("COD",),
            "PNG": ("PNG",), "KSA": ("SAU",), "NZ": ("NZL",), "PRC": ("CHN",), "PH": ("PHL",), "KL": ("MYS",),
            "HK": ("HKG",), "SA": (), "NSW": ("AUS",), "WA": ()}
ALIASES = {
    "united states": "USA", "united states of america": "USA", "america": "USA", "britain": "GBR",
    "great britain": "GBR", "england": "GBR", "scotland": "GBR", "wales": "GBR", "northern ireland": "GBR",
    "holland": "NLD", "the netherlands": "NLD", "turkey": "TUR", "turkiye": "TUR", "laos": "LAO", "vietnam": "VNM",
    "viet nam": "VNM", "south korea": "KOR", "korea": "KOR", "north korea": "PRK", "russia": "RUS", "iran": "IRN",
    "syria": "SYR", "venezuela": "VEN", "bolivia": "BOL", "czech republic": "CZE", "czechia": "CZE",
    "ivory coast": "CIV", "cote d'ivoire": "CIV", "egypt": "EGY", "gambia": "GMB", "the gambia": "GMB",
    "democratic republic of congo": "COD", "democratic republic of the congo": "COD", "republic of congo": "COG",
    "congo-brazzaville": "COG", "hong kong": "HKG", "macau": "MAC", "macao": "MAC", "yemen": "YEM",
    "slovakia": "SVK", "kyrgyzstan": "KGZ", "micronesia": "FSM", "brunei": "BRN", "bahamas": "BHS",
    "the bahamas": "BHS", "cape verde": "CPV", "swaziland": "SWZ", "burma": "MMR", "east timor": "TLS",
    "somalia": "SOM", "palestine": "PSE", "gaza": "PSE", "west bank": "PSE", "curaçao": "CUW", "taiwan": None,
    "st lucia": "LCA", "saint lucia": "LCA", "st vincent": "VCT", "saint vincent": "VCT", "st kitts": "KNA",
    "trinidad": "TTO", "tobago": "TTO", "guadeloupe": "FRA", "martinique": "FRA", "french guiana": "FRA",
    "canary islands": "ESP", "balearic islands": "ESP", "sicily": "ITA", "sardinia": "ITA", "corsica": "FRA",
    "the philippines": "PHL", "north macedonia": "MKD", "macedonia": "MKD", "bosnia": "BIH", "herzegovina": "BIH",
    "emirates": "ARE", "united arab emirates": "ARE", "saudi arabia": "SAU", "puerto rico": "PRI",
    "kosovo": "XKX", "tanzania": "TZA", "zanzibar": "TZA", "timor-leste": "TLS", "mainland china": "CHN",
}
DEMONYMS = {
    "colombian": "COL", "mexican": "MEX", "ecuadorian": "ECU", "ecuadorean": "ECU", "peruvian": "PER",
    "bolivian": "BOL", "brazilian": "BRA", "venezuelan": "VEN", "panamanian": "PAN", "paraguayan": "PRY",
    "uruguayan": "URY", "afghan": "AFG", "iranian": "IRN", "pakistani": "PAK", "turkish": "TUR", "thai": "THA",
    "burmese": "MMR", "myanmar's": "MMR", "laotian": "LAO", "chinese": "CHN", "indian": "IND", "spanish": "ESP",
    "dutch": "NLD", "belgian": "BEL", "british": "GBR", "english": "GBR", "scottish": "GBR", "welsh": "GBR",
    "american": "USA", "canadian": "CAN", "australian": "AUS", "moroccan": "MAR", "albanian": "ALB",
    "italian": "ITA", "french": "FRA", "german": "DEU", "nigerian": "NGA", "filipino": "PHL", "philippine": "PHL",
    "malaysian": "MYS", "vietnamese": "VNM", "indonesian": "IDN", "japanese": "JPN", "portuguese": "PRT",
    "greek": "GRC", "bulgarian": "BGR", "serbian": "SRB", "croatian": "HRV", "montenegrin": "MNE",
    "guatemalan": "GTM", "honduran": "HND", "salvadoran": "SLV", "salvadorean": "SLV", "nicaraguan": "NIC",
    "costa rican": "CRI", "dominican": "DOM", "jamaican": "JAM", "haitian": "HTI", "cuban": "CUB",
    "chilean": "CHL", "argentine": "ARG", "argentinian": "ARG", "south african": "ZAF", "kenyan": "KEN",
    "tanzanian": "TZA", "ugandan": "UGA", "ethiopian": "ETH", "ghanaian": "GHA", "senegalese": "SEN",
    "emirati": "ARE", "saudi": "SAU", "syrian": "SYR", "lebanese": "LBN", "jordanian": "JOR", "iraqi": "IRQ",
    "kuwaiti": "KWT", "qatari": "QAT", "omani": "OMN", "israeli": "ISR", "egyptian": "EGY", "libyan": "LBY",
    "algerian": "DZA", "tunisian": "TUN", "bangladeshi": "BGD", "sri lankan": "LKA", "cambodian": "KHM",
    "korean": "KOR", "south korean": "KOR", "north korean": "PRK", "new zealand": "NZL", "kiwi": "NZL",
    "russian": "RUS", "ukrainian": "UKR", "tajik": "TJK", "kazakh": "KAZ", "uzbek": "UZB", "kyrgyz": "KGZ",
    "turkmen": "TKM", "irish": "IRL", "polish": "POL", "czech": "CZE", "slovak": "SVK", "hungarian": "HUN",
    "romanian": "ROU", "swedish": "SWE", "norwegian": "NOR", "danish": "DNK", "finnish": "FIN", "swiss": "CHE",
    "austrian": "AUT", "singaporean": "SGP", "nepali": "NPL", "nepalese": "NPL", "maldivian": "MDV",
    "fijian": "FJI", "papua new guinean": "PNG", "trinidadian": "TTO", "guyanese": "GUY", "surinamese": "SUR",
    "belizean": "BLZ", "bahamian": "BHS", "barbadian": "BRB", "mozambican": "MOZ", "zambian": "ZMB",
    "zimbabwean": "ZWE", "namibian": "NAM", "malawian": "MWI", "cameroonian": "CMR", "ivorian": "CIV",
    "guinean": "GIN", "bissau-guinean": "GNB", "malian": "MLI", "nigerien": "NER", "sudanese": "SDN",
    "somali": "SOM", "yemeni": "YEM", "bahraini": "BHR", "armenian": "ARM", "georgian": "GEO",
    "azerbaijani": "AZE", "belarusian": "BLR", "lithuanian": "LTU", "latvian": "LVA", "estonian": "EST",
    "slovenian": "SVN", "bosnian": "BIH", "macedonian": "MKD", "kosovar": "XKX", "maltese": "MLT",
    "cypriot": "CYP", "icelandic": "ISL", "luxembourgish": "LUX", "mongolian": "MNG", "bhutanese": "BTN",
    "taiwanese": None, "hongkonger": "HKG", "macanese": "MAC", "puerto rican": "PRI",
}
# States, provinces and regions clearly inside one country (Georgia is omitted: also a country).
SUBNATIONAL = {
    "USA": ["Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware",
            "Florida", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine",
            "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska",
            "Nevada", "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota",
            "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
            "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "West Virginia", "Wisconsin", "Wyoming",
            "Washington state", "Washington, D.C.", "Los Angeles", "San Diego", "San Francisco", "New Orleans",
            "Long Beach", "El Paso", "San Ysidro", "Otay Mesa", "Calexico", "Brownsville", "Eagle Pass",
            "Del Rio", "Lukeville", "Douglas, Arizona", "Nogales, Arizona", "Port Everglades", "Port Newark",
            "JFK", "O'Hare", "Rio Grande Valley", "Appalachia", "Puget Sound", "Baltimore", "Philadelphia",
            "Brooklyn", "Bronx", "Manhattan", "Queens", "Boston", "Chicago", "Miami", "Houston", "Phoenix",
            # southwest and northern border ports of entry
            "Pharr", "Hidalgo, Texas", "Laredo", "Santa Teresa", "Presidio", "Roma, Texas", "Progreso, Texas",
            "Tecate, California", "Andrade", "San Luis, Arizona", "Port Huron", "Champlain", "Blaine",
            "Sweetgrass", "Pembina", "Derby Line"],
    "MEX": ["Sinaloa", "Sonora", "Chihuahua", "Jalisco", "Michoacán", "Michoacan", "Tamaulipas", "Baja California",
            "Guerrero", "Zacatecas", "Nuevo León", "Nuevo Leon", "Quintana Roo", "Veracruz", "Oaxaca", "Chiapas",
            "Culiacán", "Culiacan", "Ciudad Juárez", "Ciudad Juarez", "Juárez", "Nuevo Laredo", "Mexicali",
            "Matamoros", "Reynosa", "Tijuana", "Manzanillo", "Lázaro Cárdenas", "Lazaro Cardenas", "Tapachula",
            "Cancún", "Cancun", "Mexico City", "Guadalajara", "Monterrey", "Ensenada", "Sonoyta", "Durango",
            "Nogales, Sonora"],
    "CAN": ["Ontario", "Quebec", "British Columbia", "Alberta", "Manitoba", "Saskatchewan", "Nova Scotia",
            "New Brunswick", "Newfoundland", "Vancouver", "Montreal", "Toronto", "Surrey, B.C.", "Windsor, Ont",
            "Sarnia", "Point Edward", "Lacolle", "Tsawwassen", "Fort Erie", "Emerson, Manitoba", "Coutts",
            "Pacific Highway crossing", "Saint John, N.B.", "Prince Rupert", "Halifax"],
    "AUS": ["New South Wales", "Queensland", "Victoria Police", "Western Australia", "South Australia", "Tasmania",
            "Northern Territory", "Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Fremantle", "Darwin",
            "Gold Coast", "Port Botany", "Geraldton"],
    "COL": ["Antioquia", "Nariño", "Narino", "Cauca", "Valle del Cauca", "Chocó", "Choco", "Catatumbo",
            "Buenaventura", "Cartagena", "Barranquilla", "Santa Marta", "Tumaco", "Medellín", "Medellin", "Bogotá",
            "Urabá", "Uraba", "Turbo"],
    "ECU": ["Guayaquil", "Guayas", "Esmeraldas", "Manabí", "Posorja", "Puerto Bolívar", "Quito"],
    "PER": ["VRAEM", "Callao", "Paita", "Lima"],
    "BOL": ["Chapare", "Santa Cruz de la Sierra"],
    "BRA": ["Santos", "Paranaguá", "Paranagua", "São Paulo", "Sao Paulo", "Rio de Janeiro", "Itajaí", "Pará",
            "Mato Grosso", "Amazonas state"],
    "PRY": ["Ciudad del Este", "Pedro Juan Caballero", "Asunción"],
    "PAN": ["Colón Free Trade Zone", "Balboa", "Panama City"],
    "ESP": ["Algeciras", "Valencia", "Barcelona", "Galicia", "Andalusia", "Cádiz", "Cadiz", "Ceuta", "Melilla",
            "Canary Islands", "Tenerife", "Gran Canaria", "Huelva", "Vigo", "Madrid", "Málaga", "Malaga",
            "Pontevedra", "Costa del Sol", "Marbella", "Campo de Gibraltar"],
    "PRT": ["Lisbon", "Sines", "Leixões", "Madeira", "Azores"],
    "FRA": ["Le Havre", "Marseille", "Dunkirk", "Dunkerque", "Paris", "Roissy", "Charles de Gaulle", "Lyon",
            "Nice", "Guadeloupe", "Martinique", "French Guiana", "Cayenne"],
    "BEL": ["Antwerp", "Zeebrugge", "Brussels", "Ghent", "Liège"],
    "NLD": ["Rotterdam", "Amsterdam", "Schiphol", "Vlissingen", "Moerdijk", "The Hague", "Eindhoven", "Limburg"],
    "DEU": ["Hamburg", "Bremerhaven", "Bremen", "Frankfurt", "Berlin", "Munich", "Bavaria", "Cologne"],
    "GBR": ["Felixstowe", "Southampton", "London Gateway", "Heathrow", "Gatwick", "Dover", "Liverpool",
            "Manchester", "Birmingham", "Glasgow", "Edinburgh", "Belfast", "Tilbury", "Hull", "Essex", "Kent",
            "Merseyside", "London"],
    "IRL": ["Dublin", "Cork", "Rosslare"],
    "ITA": ["Gioia Tauro", "Calabria", "Livorno", "Genoa", "Naples", "Salerno", "Civitavecchia", "Trieste",
            "Palermo", "Rome", "Milan", "Sicily", "Sardinia", "Apulia", "Puglia"],
    "GRC": ["Piraeus", "Thessaloniki", "Athens", "Crete"],
    "ALB": ["Durrës", "Durres", "Tirana"],
    "TUR": ["Mersin", "Istanbul", "Izmir", "Hakkari", "Van province"],
    "IRN": ["Bandar Abbas", "Sistan", "Baluchestan", "Tehran", "Chabahar"],
    "AFG": ["Helmand", "Kandahar", "Nangarhar", "Badakhshan", "Kabul", "Herat", "Nimroz", "Farah"],
    "PAK": ["Karachi", "Port Qasim", "Balochistan", "Baluchistan", "Khyber Pakhtunkhwa", "Peshawar", "Quetta",
            "Lahore", "Islamabad", "Torkham", "Gwadar"],
    "IND": ["Mundra", "Kutch", "Gujarat", "Nhava Sheva", "Mumbai", "Chennai", "Kolkata", "Delhi", "New Delhi",
            "Manipur", "Mizoram", "Assam", "Kerala", "Tamil Nadu", "Andhra Pradesh", "Hyderabad", "Bengaluru",
            "Goa", "Rajasthan", "Uttar Pradesh", "Maharashtra", "Tuticorin", "Thoothukudi", "Jammu", "Kashmir"],
    "BGD": ["Chittagong", "Chattogram", "Cox's Bazar", "Teknaf", "Dhaka"],
    "MMR": ["Shan State", "Shan", "Rakhine", "Kachin", "Yangon", "Tachileik", "Mandalay", "Wa State"],
    "THA": ["Chiang Rai", "Chiang Mai", "Mae Sai", "Mae Hong Son", "Laem Chabang", "Bangkok", "Nakhon Phanom",
            "Songkhla", "Tak province", "Mae Sot", "Phuket", "Pattaya", "Suvarnabhumi"],
    "LAO": ["Bokeo", "Vientiane", "Luang Namtha", "Golden Triangle Special Economic Zone"],
    "VNM": ["Haiphong", "Hai Phong", "Ho Chi Minh City", "Hanoi", "Saigon"],
    "MYS": ["Port Klang", "Tanjung Pelepas", "Johor", "Sabah", "Sarawak", "Penang", "Kuala Lumpur", "Selangor",
            "Kedah", "Perlis", "Kelantan"],
    "IDN": ["Aceh", "Bali", "Sumatra", "Java", "Batam", "Riau", "Jakarta", "Kalimantan", "Surabaya"],
    "PHL": ["Manila", "Luzon", "Mindanao", "Cebu", "Subic", "Bulacan", "Cavite", "Pampanga", "Quezon City", "NAIA"],
    "SGP": ["Changi"],
    "HKG": ["Kowloon", "Kwai Chung", "Chek Lap Kok"],
    "CHN": ["Guangdong", "Yunnan", "Shenzhen", "Guangzhou", "Shanghai", "Beijing", "Fujian", "Hubei", "Wuhan"],
    "AUS_": [],
    "NZL": ["Auckland", "Wellington", "Northland", "Christchurch", "Tauranga", "Waikato"],
    "ARE": ["Dubai", "Abu Dhabi", "Jebel Ali", "Sharjah"],
    "SAU": ["Jeddah", "Riyadh", "Dammam", "Al-Haditha", "Al Haditha", "Jizan", "Jazan"],
    "JOR": ["Amman", "Aqaba", "Jaber crossing"],
    "SYR": ["Latakia", "Tartus", "Damascus", "Aleppo", "Daraa", "Sweida", "Homs"],
    "LBN": ["Beirut", "Bekaa", "Tripoli, Lebanon"],
    "IRQ": ["Baghdad", "Basra", "Anbar", "Kurdistan region"],
    "KWT": ["Kuwait City"],
    "EGY": ["Cairo", "Alexandria", "Port Said", "Sinai"],
    "MAR": ["Tangier", "Tanger Med", "Rif", "Casablanca", "Nador"],
    "DZA": ["Algiers", "Oran"],
    "LBY": ["Benghazi", "Misrata", "Tripoli, Libya"],
    "NGA": ["Lagos", "Murtala Muhammed", "Abuja", "Kano", "Port Harcourt", "Apapa", "Tin Can Island", "Onne"],
    "GHA": ["Accra", "Tema", "Kotoka"],
    "SEN": ["Dakar"],
    "GNB": ["Bissau", "Bijagós"],
    "CIV": ["Abidjan", "San-Pédro"],
    "TGO": ["Lomé", "Lome"],
    "BEN": ["Cotonou"],
    "CPV": ["Praia", "Mindelo"],
    "KEN": ["Mombasa", "Nairobi", "Kisumu", "Jomo Kenyatta"],
    "TZA": ["Dar es Salaam", "Zanzibar", "Tanga"],
    "MOZ": ["Maputo", "Pemba", "Nacala", "Cabo Delgado"],
    "ZAF": ["Durban", "Cape Town", "Johannesburg", "Gauteng", "KwaZulu-Natal", "OR Tambo", "Port Elizabeth",
            "Gqeberha", "Pretoria"],
    "JAM": ["Kingston, Jamaica", "Montego Bay"],
    "DOM": ["Santo Domingo", "Punta Cana", "Caucedo", "Haina"],
    "HTI": ["Port-au-Prince"],
    "GUY": ["Georgetown, Guyana"],
    "SUR": ["Paramaribo"],
    "VEN": ["Caracas", "Zulia", "Apure", "Falcón"],
    "HND": ["Tegucigalpa", "San Pedro Sula", "Gracias a Dios", "Mosquitia"],
    "GTM": ["Guatemala City", "Petén", "Peten", "Puerto Quetzal", "Tecún Umán"],
    "CRI": ["Limón", "Limon", "Moín", "Moin", "San José, Costa Rica", "Caldera"],
    "SLV": ["San Salvador", "Acajutla"],
    "CAN_": [],
}
# Phrases that contain a country word but name no country; consumed so the word inside does not count.
NON_COUNTRY = ["Latin America", "Latin American", "South America", "South American", "Central America",
               "Central American", "North America", "North American", "Indian Ocean", "American Samoa",
               "Americas", "Native American", "Pan American", "Golden Triangle", "Golden Crescent",
               "Indian Point", "Turkish delight", "French fries", "Dutch courage", "Irish coffee",
               "American Airlines", "British Airways", "Swiss cheese", "Chinese New Year", "Mexican standoff",
               "Russian roulette", "Brazil nut", "Indian summer", "New Guinea", "Jordan Peterson", "Michael Jordan",
               "Georgia state", "Atlanta, Georgia", "Georgia's governor", "Guinea pig", "Chad Smith",
               "Middle East", "West Africa", "East Africa", "Southeast Asia", "South Asia", "Central Asia",
               "the Balkans", "Caribbean", "Sahel", "Horn of Africa", "Pacific", "Andean"]
# Natural Earth city names that are also common words or names (never treated as a place).
CITY_STOP = {"aba", "arad", "bade", "bo", "beni", "bida", "bose", "canton", "como", "coro", "crato", "dali",
             "george", "gary", "hail", "hue", "ica", "ife", "ibb", "itu", "iwo", "jackson", "jian", "kure",
             "lincoln", "luan", "mary", "mesa", "mobile", "nancy", "naga", "nice", "nema", "oral", "orel", "ordu",
             "owo", "oyo", "pali", "palma", "puri", "reading", "rize", "salem", "sari", "split", "springs", "stoke",
             "tours", "tula", "tsu", "van", "waco", "york", "anda", "arar", "aurora", "austin", "olympia",
             "phoenix", "regina", "soledad", "sagar", "rashid", "durham", "windsor", "trenton", "elgin", "eugene",
             "everett", "flint", "franca", "formosa", "natal", "ogden", "provo", "reno", "sanford", "timon",
             "valera", "victoria", "vitoria", "hampton", "lowell", "madison", "memphis", "norfolk", "oxford",
             "paris", "rome", "athens", "toledo", "cartago", "colon", "colón", "cuenca", "cadiz", "leon", "león",
             "merida", "mérida", "cordoba", "córdoba", "santiago", "san juan", "armenia", "nyanza",
             "medina", "zamora", "rivera", "salinas", "dayton", "joliet", "akron", "erie", "fargo", "irvine",
             "tampa", "tulsa", "wichita", "tacoma", "boise", "raleigh", "denton", "peoria", "lansing", "albany",
             "augusta", "barlett", "manta", "tanga", "kota", "gaya", "hebi", "bata", "safi", "diwan", "sucre",
             "kochi", "florida", "limbe", "bello", "campos", "iligan", "angeles", "concord", "independence"}


def _fold(s: str) -> str:
    """Strip accents so 'Medellín' and 'Medellin', 'Türkiye' and 'Turkiye' match the same entry."""
    s = s.replace("’", "'").replace("‘", "'")
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


def _country_rows() -> list[dict]:
    """The 217 World Bank economies, from the first source present: the exported API catalogue (shipped in the Vercel
    package), then the contract fixture (repo checkouts, Colab). Loud when both are missing: without country names
    no country can be a candidate, and every origin/destination would silently come back as not stated."""
    from .. import config
    for path, key in ((config.API_DIR / "countries.json", None),
                      (HERE.parents[2] / "contracts" / "fixtures" / "countries.json", "data")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            rows = doc[key] if key else doc
            if rows:
                return rows
        except (OSError, ValueError, KeyError, TypeError):
            continue
    logging.getLogger(__name__).error("grounding: no country catalogue found; country names cannot be recognised")
    return []


def _country_short_names() -> dict[str, str]:
    """World Bank short names (217 economies), e.g. 'Iran, Islamic Rep.' -> 'Iran'."""
    out: dict[str, str] = {}
    for c in _country_rows():
        short = re.sub(r",.*$|\(.*?\)", "", c["name"]).strip()
        out[short.lower()] = c["iso3"]
    return out


@lru_cache(maxsize=1)
def gazetteer() -> dict[str, tuple[str, ...]]:
    """Lowercase, accent-folded place name -> ISO3 codes it supports (empty tuple = consumed, names no country)."""
    g: dict[str, set[str]] = {}

    def add(name: str, iso):
        k = _fold(name).lower().strip()
        if not k:
            return
        g.setdefault(k, set())
        if iso:
            g[k].add(iso)

    # cities: most populous wins unless the runner-up is at least a third its size (then both countries)
    by: dict[str, dict[str, int]] = {}
    try:
        with CITIES_CSV.open(encoding="utf-8") as f:
            for r in csv.DictReader(line for line in f if not line.startswith("#")):
                k = _fold(r["name"]).lower()
                if len(k) < 4 or k in CITY_STOP:
                    continue
                by.setdefault(k, {})
                by[k][r["iso3"]] = max(by[k].get(r["iso3"], 0), int(float(r["pop"] or 0)))
    except OSError:
        pass
    for k, pops in by.items():
        top = max(pops.values())
        for iso, p in pops.items():
            if p * 3 >= top:
                add(k, iso)
    curated: dict[str, set[str]] = {}
    for iso, places in SUBNATIONAL.items():
        for p in places:
            curated.setdefault(_fold(p).lower(), set()).add(iso.rstrip("_"))
    for k, isos in curated.items():  # curated ports and states override the city table
        g[k] = set(isos)
    for name, iso in _country_short_names().items():
        g[_fold(name).lower()] = {iso}
    for name, iso in {**ALIASES, **DEMONYMS}.items():
        g[_fold(name).lower()] = {iso} if iso else set()
    g["georgia"] = {"GEO", "USA"}  # the country or the US state: both are textual support
    g["jordan"] = {"JOR"}
    for p in NON_COUNTRY:
        g[_fold(p).lower()] = set()
    return {k: tuple(sorted(v)) for k, v in g.items()}


@lru_cache(maxsize=1)
def _country_regex() -> re.Pattern:
    names = sorted(gazetteer(), key=len, reverse=True)
    return re.compile(r"(?<![\w])(" + "|".join(re.escape(n) for n in names) + r")(?:'s)?(?![\w])", re.I)


@lru_cache(maxsize=1)
def _acronym_regex() -> re.Pattern:
    keys = sorted(ACRONYMS, key=len, reverse=True)
    return re.compile(r"(?<![\w.])(" + "|".join(re.escape(k) for k in keys) + r")(?![\w])")


def find_countries(text: str) -> list[tuple[int, str, str]]:
    """Every country the text supports, in order: (position, ISO3, the words that support it).

    Place names must be capitalised as proper nouns (unless the whole text is upper case), so 'turkey' the bird,
    'china' the tableware and 'tell us' never count; acronyms (US, UK, UAE) must be upper case."""
    t = _fold(text or "")
    shouting = not re.search(r"[a-z]", t)
    hits: list[tuple[int, str, str]] = []
    taken = [False] * len(t)
    for m in _country_regex().finditer(t):
        word = m.group(1)
        if not shouting and not word[0].isupper() and not word.lower().startswith(("the ", "st ")):
            continue
        for i in range(m.start(), m.end()):
            taken[i] = True
        for iso in gazetteer().get(word.lower(), ()):
            hits.append((m.start(), iso, word))
    if not shouting:
        for m in _acronym_regex().finditer(t):
            if any(taken[m.start():m.end()]):
                continue
            for iso in ACRONYMS[m.group(1)]:
                hits.append((m.start(), iso, m.group(1)))
    return sorted(hits)


def supported_countries(text: str) -> set[str]:
    return {iso for _, iso, _ in find_countries(text)}


def country_candidates(text: str, limit: int = 8) -> list[str]:
    """Distinct supported ISO3 codes in order of first mention (the options a model may choose between)."""
    return list(dict.fromkeys(iso for _, iso, _ in find_countries(text)))[:limit]


# ------------------------------------------------------------------ the guardrail
def ground(c: Classification, title: str, text: str = "", drug_probs: dict[str, float] | None = None,
           event_threshold: float | None = None) -> Classification:
    """Return `c` with every ungrounded answer removed. Idempotent.

    `drug_probs` (option -> probability, e.g. Reflex's Choice probabilities) lets an unsupported drug fall back to
    the most probable supported option instead of "unclear"."""
    state = f"{title}. {text}".strip()
    countries = supported_countries(state)
    drugs = supported_drugs(state)
    dropped = list(c.dropped)
    kw: dict = {}
    for f in ("origin", "transit", "destination", "location"):
        v = getattr(c, f)
        if v and v not in countries:
            kw[f] = None
            if f != "location":
                dropped.append(f"{f}:{v}")
    o = kw.get("origin", c.origin)
    d = kw.get("destination", c.destination)
    if kw.get("location", c.location) is None:  # map pin: the most specific grounded place, else first mention
        kw["location"] = d or o or next(iter(country_candidates(state)), None)
    drug = c.drug
    if drug not in ("unclear",) and drug not in drugs:
        dropped.append(f"drug:{drug}")
        options = [k for k in (drug_probs or {}) if k in drugs]
        drug = max(options, key=drug_probs.get) if options else "unclear"
        kw["drug"] = drug
        kw["drug_conf"] = round(float(drug_probs.get(drug, 0.0)), 3) if drug_probs and drug in drug_probs else 0.0
        # the overall confidence averages is_event, event type and drug: replace the dropped drug's share
        kw["confidence"] = round(max(0.0, c.confidence - (c.drug_conf - kw["drug_conf"]) / 3), 3)
    stated = size_from_text(state)
    if stated:
        kw["size"], kw["size_stated"] = stated, True
        kw["size_score"] = round(["small", "notable", "major", "record"].index(stated) / 3, 3)
    elif c.size_stated:
        kw["size_stated"] = False
    thr = EVENT_THRESHOLD if event_threshold is None else event_threshold
    is_event = c.is_event
    if not has_trade_vocabulary(state):
        is_event = min(is_event, 0.05)
    elif c.event_type == "other":  # by its own definition "other" is research, statistics or commentary
        is_event = min(is_event, 0.49)
    elif is_event < thr:
        is_event = min(is_event, 0.49)  # below the tuned threshold: not an event
    if is_event != c.is_event:
        kw["is_event"] = round(is_event, 3)
        dropped.append("is_event")
    if o is None and d is None and c.route_mentioned >= 0.5 and ("origin" in kw or "destination" in kw):
        kw["route_mentioned"] = 0.3
    return replace(c, **kw, dropped=tuple(dict.fromkeys(dropped)))


def passes_wire(c: Classification, min_conf: float = MIN_CONFIDENCE) -> bool:
    """The Live Wire display cut: a confident event after grounding."""
    return c.confidence >= min_conf and c.is_event >= 0.5
