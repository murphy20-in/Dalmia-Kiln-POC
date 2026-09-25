"""Evidence-based classification helpers (Objectives C, J, K).

Classification uses ONLY header text, sheet title and the unit row. Every result
carries the evidence string and a confidence:
  HIGH   - keyword found in the column's own header text
  MEDIUM - keyword is an abbreviation (PC, TAD, PH, SFM, HAG ...) or found only in the
           positional group header (group headers are NOT merged cells in the source,
           so assigning them to neighbouring columns is an inference)
  LOW    - weak / partial evidence
  (UNKNOWN family when nothing matches)
"""
from __future__ import annotations

import re

FAMILIES = ["KILN", "FUEL", "ALTERNATIVE FUEL", "COMBUSTION", "PREHEATER", "CALCINER", "DRAFT / ID FAN",
            "COOLER", "EFFICIENCY", "PRODUCTION", "CLINKER QUALITY", "EVENT / MAINTENANCE", "OTHER", "UNKNOWN"]

# (family, regex, abbreviation_only)
RULES = [
    ("ALTERNATIVE FUEL", r"\bAFR\b|alternat|\bRDF\b|plastic|\bAF\b", False),
    ("EFFICIENCY", r"sp\.?\s?heat|sp\.?\s?power|heat\s+consum|specific|tota\s?l\s+power", False),
    ("CLINKER QUALITY", r"free\s*lime|\bLSF\b|\bLSM\b|\bSM\b|\bAM\b|litre\s*weight|\bC3S\b|\bfcao\b", False),
    ("EVENT / MAINTENANCE", r"coating|\bring\b|deposit|cleaning|shutdown|maintenance|breakdown|\btrip\b", False),
    ("COMBUSTION", r"\bO2\b|\bCO\b|\bNOX\b|\bCO2\b|excess\s+air|combustion|stoik", False),
    ("FUEL", r"coal|diesel|\bfuel\b|firing|\bHAG\b", False),
    ("COOLER", r"cooler|grate|clinker\s+tem|roller\s+cru|roller\s+curs", False),
    ("PREHEATER", r"cyclone|pre\s?heater\b(?!\s+fan)", False),
    ("PREHEATER", r"\bPH\b", True),
    ("CALCINER", r"calciner", False),
    ("CALCINER", r"\bPC\b|\bTAD\b|\bTA\s+Duct", True),
    ("DRAFT / ID FAN", r"pre\s?heater\s+fan|\bID\s+fan|draft", False),
    ("PRODUCTION", r"kiln\s+feed|pfister|clinker\s+tph|bucket\s+elevator", False),
    ("PRODUCTION", r"\bSFM\b", True),
    ("KILN", r"kiln\s+main\s+drive|kiln\s+hood|kiln\s+inlet|burning\s+zone|\bkiln\b", False),
    ("KILN", r"kiln\s+md", True),
    ("OTHER", r"\bESP\b|\bCBS\b|quench|quanch|\bBH\b|dust|conveyor|blower|pump|\bRAL\b|spout|bulker|"
              r"jet\s+air|swirl|\bPA\s+FAN|chim|bypass|water\s+spray|fresh\s+air|vent", False),
]

# Documented overrides where positional context clearly dominates own-text keywords.
OVERRIDES = {
    ("Kiln-I", "I"): ("FUEL", "MEDIUM", "own header 'PC' (unit TPH) sits under positional group 'Coal Firing' "
                      "(not a merged cell); interpreted as PC coal firing rate - REQUIRES PLANT CONFIRMATION"),
    ("Kiln-I", "E"): ("EFFICIENCY", "MEDIUM", "own header 'Sp.Power' (kwh/T) although row-1 text in this cell is "
                      "'Coal Firing'; header layout ambiguous - REQUIRES PLANT CONFIRMATION"),
}

ABBREV_NOTE = {
    "PC": "'PC' read as pre-calciner abbreviation (not defined in source)",
    "TAD": "'TAD'/'TA Duct' read as tertiary-air duct abbreviation (not defined in source)",
    "PH": "'PH' read as preheater abbreviation (not defined in source)",
    "SFM": "'SFM' abbreviation not defined in source; positioned next to 'Kiln Feed'",
    "HAG": "'HAG' abbreviation not defined in source",
    "Kiln MD": "'Kiln MD' not defined in source (possibly kiln main drive); unit is hours",
}


def classify_family(equipment: str, col_letter: str, own_text: str, group_ffill: str | None, title: str | None):
    if (equipment, col_letter) in OVERRIDES:
        return OVERRIDES[(equipment, col_letter)]
    for fam, rx, abbrev in RULES:
        m = re.search(rx, own_text or "", re.I)
        if m:
            tok = m.group(0)
            note = ABBREV_NOTE.get(tok.upper() if tok.upper() in ABBREV_NOTE else tok, "")
            if tok.lower().startswith("kiln md"):
                note = ABBREV_NOTE["Kiln MD"]
            conf = "MEDIUM" if abbrev else "HIGH"
            return fam, conf, f"own header matched '{tok}'" + (f"; {note}" if note else "")
    if group_ffill:
        for fam, rx, abbrev in RULES:
            m = re.search(rx, group_ffill, re.I)
            if m:
                return fam, ("LOW" if abbrev else "MEDIUM"), (f"matched '{m.group(0)}' only in positional group header "
                                                              f"'{group_ffill}' (not merged; inferred)")
    return "UNKNOWN", "", "no taxonomy keyword in header text"


# measurement type from the explicit unit row
UNIT_TYPE = {
    "deg.c": "TEMPERATURE", "mmwc": "PRESSURE / DRAFT", "mbar": "PRESSURE / DRAFT", "bar": "PRESSURE / DRAFT",
    "a": "ELECTRICAL CURRENT", "amps": "ELECTRICAL CURRENT", "ma": "ELECTRICAL CURRENT", "kv": "VOLTAGE",
    "rpm": "ROTATIONAL SPEED", "kw": "POWER", "hrs": "RUN HOURS / TIME", "tph": "MASS FLOW RATE",
    "lph": "VOLUMETRIC FLOW RATE", "m3/m": "VOLUMETRIC FLOW RATE", "m3/hr": "VOLUMETRIC FLOW RATE",
    "nm3/min": "VOLUMETRIC FLOW RATE", "kg/h": "MASS FLOW RATE", "%": "PERCENT / RATIO", "ppm": "GAS CONCENTRATION",
    "ton": "MASS", "tons": "MASS", "kwh/t": "SPECIFIC ENERGY", "kw/ton": "SPECIFIC ENERGY",
    "kcla/kgclnkr": "SPECIFIC HEAT", "kcal/kg": "SPECIFIC HEAT",
}

# expected unit dimension from measurement words in the label (label-unit coherence check)
LABEL_EXPECT = [
    (r"\btemp|\btemo\b|\bI/LTemp", {"deg.c"}),
    (r"press\b|pressure|\bpr\.|draft|\bDP\b", {"mmwc", "mbar", "bar"}),
    (r"current|curent", {"a", "amps", "ma"}),
    (r"\bspeed\b", {"rpm"}),
    (r"run\s+hrs", {"hrs"}),
    (r"\bweight\b", {"ton", "tons"}),
    (r"\bpos\b|position|damp\.?pos|damper\s+pos", {"%"}),
    (r"\bO2\b", {"%"}),
    (r"\bCO\b|\bNOX\b", {"ppm"}),
    (r"\bpower\b|^\s*KW\s*$", {"kw", "kwh/t", "kw/ton"}),
]


def unit_key(u: str | None) -> str:
    return (u or "").strip().lower()


def measurement_type(unit: str | None) -> str:
    return UNIT_TYPE.get(unit_key(unit), "UNKNOWN" if not unit else f"UNMAPPED UNIT '{unit}'")


def label_unit_check(sub_label: str, unit: str | None) -> tuple[bool, str]:
    """Returns (review_required, reason). Uses only the column's own (non-group) label."""
    if not unit:
        return True, "no unit in source unit row"
    for rx, allowed in LABEL_EXPECT:
        if re.search(rx, sub_label or "", re.I):
            if unit_key(unit) not in allowed:
                return True, f"label '{sub_label}' suggests {sorted(allowed)} but unit row says '{unit}'"
            return False, ""
    return False, ""
