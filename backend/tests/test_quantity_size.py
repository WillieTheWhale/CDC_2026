# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Rule-based seizure size from stated quantities (trace_backend.jev.quantity)."""
import pytest

from trace_backend.jev.quantity import size_from_text


@pytest.mark.parametrize("text, expected", [
    # record wording wins
    ("Record 8 tonnes of cocaine seized in Rotterdam container", "record"),
    ("Largest ever cocaine haul in New Zealand traced to South America", "record"),
    ("Police make largest-ever meth bust", "record"),
    ("Biggest ever heroin seizure at the border", "record"),
    ("An unprecedented 40 kg of fentanyl found", "record"),
    ("Record 55 million methamphetamine tablets seized in Laos", "record"),
    # "recordings"/"recorded" are not record wording
    ("Police recordings show 5 kg of cocaine in the car", "small"),
    ("Officers recorded 20 kg of heroin at the port", "small"),
    # weights
    ("Ecuador navy seizes 4.2 tonnes of cocaine bound for Belgium", "major"),
    ("Customs officers in Antwerp find 900 kg of cocaine hidden in banana boxes", "notable"),
    ("Costa Rica coast guard intercepts go-fast boat carrying 1,200 kg of cocaine", "notable"),
    ("French customs seize 1.5 tonnes of cocaine at Le Havre", "major"),
    ("Police seize 99 kilos of cannabis", "small"),
    ("Police seize 100 kilograms of cannabis", "notable"),
    ("Guards find 1,499 kgs of hashish", "notable"),
    ("US Border Patrol seizes 1,000 pounds of meth at San Diego", "notable"),
    ("Agents seize 5,000 lbs of marijuana", "major"),
    ("Officers find 250 grams of heroin", "small"),
    ("Officers find 300 g of cocaine", "small"),
    ("Navy seizes 2 metric tons of cocaine", "major"),
    ("Boat carrying 3 t of cocaine stopped", "major"),
    ("Police seize a tonne of cocaine", "notable"),
    ("Police seize one tonne of cocaine", "notable"),
    ("Police seize half a tonne of cocaine", "notable"),
    ("Brazil seizes 30 tons of marijuana from Paraguay", "major"),
    ("Coast guard seizes tonnes of cocaine off Galicia", "major"),
    ("A 2-tonne cocaine shipment was intercepted", "major"),
    # pill and tablet counts
    ("Thai police intercept 12 million meth pills near Myanmar border", "major"),
    ("Police find 55,000 tablets of ecstasy", "notable"),
    ("Jordan seizes 3.5 million captagon pills", "major"),
    ("Police seize 9,999 pills", "small"),
    ("Police seize 10,000 pills", "notable"),
    ("Customs find 200 thousand yaba tablets", "notable"),
    ("Saudi Arabia seizes millions of amphetamine pills from Lebanon", "major"),
    # several quantities: the largest wins
    ("Police seize 50 kg of heroin and 2 tonnes of cannabis", "major"),
    ("Raid finds 5 kg of meth and 20,000 pills", "notable"),
    # money is not a quantity
    ("Philippine agents seize shabu worth 1 billion pesos in Manila", None),
    ("Cocaine worth $5 million seized at the port", None),
    ("Drugs worth 3 million euros found in a truck", None),
    ("Police seize heroin worth 2 million pounds", None),
    ("Police seize 10 kg of cocaine worth $5 million", "small"),
    # no quantity -> let the model decide
    ("Spanish police intercept cocaine shipment from Colombia at Algeciras port", None),
    ("Interpol operation seizes drugs across 30 countries", None),
    ("Ecuador prison riot leaves 30 dead as gangs fight over cocaine routes", None),
    ("", None),
])
def test_size_from_text(text, expected):
    assert size_from_text(text) == expected
