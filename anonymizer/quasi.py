"""Quasi-identifiers: facts that are not names but can still single someone out.

These are reported, not removed, because the cloud model usually needs them
(an award amount in a budget memo, a GPA in a probation note). The user decides.
Optional generalisation coarsens money and GPA.
"""
from __future__ import annotations

import re

QUASI = [
    ("MONEY", re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:k|K|M|million|thousand))?")),
    ("GPA", re.compile(r"(?i)\bGPA\b[^.\n]{0,15}?\d\.\d{1,2}|\b\d\.\d{1,2}\s+GPA\b")),
    ("AGE", re.compile(r"(?i)\b\d{2}[- ]year[- ]old\b|\bage[d]?\s+\d{2}\b")),
    ("COURSE", re.compile(r"\b[A-Z]{3,4}[\s-]?\d{4}\b")),
    ("YEAR", re.compile(r"\b(?:19|20)\d{2}\b")),
    ("SMALL_GROUP", re.compile(
        r"(?i)\b(?:only|sole|single|first)\s+(?:student|woman|man|person|one|veteran|international|female|male)\b"
        r"|\bone of (?:two|three|four|five|\d)\b|\bfirst[- ]generation\b")),
    ("SENSITIVE_ATTR", re.compile(
        r"(?i)\b(?:accommodation|disabilit\w+|diagnos\w+|pregnan\w+|medical leave|therapy|counsel(?:l)?ing|"
        r"F-1|J-1|visa|immigration|veteran|probation|dismissal|misconduct|financial aid|scholarship)\b")),
]


def report(text: str) -> list[dict]:
    out = []
    for typ, pat in QUASI:
        hits = [m.group(0) for m in pat.finditer(text)]
        if hits:
            out.append({"type": typ, "count": len(hits), "examples": sorted(set(hits))[:5]})
    return out


def _round_money(m: re.Match) -> str:
    raw = m.group(0)
    digits = re.sub(r"[^\d.]", "", raw)
    try:
        v = float(digits)
    except ValueError:
        return raw
    if re.search(r"(?i)k|thousand", raw):
        v *= 1e3
    if re.search(r"(?i)M\b|million", raw):
        v *= 1e6
    if v < 1000:
        return "under $1,000"
    mag = 10 ** (len(str(int(v))) - 2)
    return "about $%s" % f"{round(v / mag) * mag:,.0f}"


def generalize(text: str, money=False, gpa=False) -> str:
    if money:
        text = QUASI[0][1].sub(_round_money, text)
    if gpa:
        def band(m):
            v = float(re.search(r"\d\.\d{1,2}", m.group(0)).group(0))
            lo = int(v * 2) / 2
            return m.group(0).replace(re.search(r"\d\.\d{1,2}", m.group(0)).group(0), f"{lo:.1f}-{lo + 0.5:.1f}")
        text = QUASI[1][1].sub(band, text)
    return text
