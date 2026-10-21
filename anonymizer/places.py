"""Place names the regex layer replaces without asking the model.

The local model misses small towns (Pearland, Katy) more often than names. A
gazetteer closes that gap for the places your records actually mention. Extend
PLACES for your region; counties are matched by pattern, not by list.
"""
import re

# Greater Houston cities, towns and neighbourhoods (Houston itself is allowlisted).
PLACES = [
    "Alvin", "Atascocita", "Bacliff", "Baytown", "Bellaire", "Brookshire", "Channelview", "Clear Lake",
    "Cleveland", "Conroe", "Crosby", "Deer Park", "Dickinson", "Friendswood", "Fulshear",
    "Galena Park", "Galveston", "Hitchcock", "Hockley", "Huffman", "Humble", "Jersey Village",
    "Katy", "Kemah", "Kingwood", "La Marque", "La Porte", "League City", "Manvel",
    "Meadows Place", "Missouri City", "Mont Belvieu", "Nassau Bay", "Pasadena",
    "Pearland", "Rosenberg", "Seabrook", "Sealy", "Sienna",
    "Stafford", "Sugar Land", "Texas City", "Tomball", "Webster", "West University Place",
    "Willis", "Woodlands", "The Woodlands", "Montrose", "Third Ward", "Fifth Ward",
    "Gulfton", "Alief", "Sharpstown", "Meyerland", "Spring Branch",
    "Freeport", "Lake Jackson", "Angleton", "Clute", "Brazos", "College Station", "Bryan",
    "Austin", "San Antonio", "Dallas", "Fort Worth", "El Paso", "Corpus Christi", "Beaumont",
]

# Left out on purpose: places that are also everyday words in university records
# (Spring as in "Spring 2027", Heights, Cypress, Magnolia, Porter). The model handles those.

COUNTY_RE = re.compile(r"\b(?:[A-Z][a-z]+\s){1,2}(?:County|Parish)\b")


def pattern() -> re.Pattern:
    alts = sorted(PLACES, key=len, reverse=True)
    return re.compile(r"(?<!\w)(?:%s)(?!\w)" % "|".join(re.escape(p) for p in alts))
