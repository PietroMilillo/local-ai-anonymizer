"""Regex layer: structured identifiers that a pattern can find reliably.

Each pattern returns spans (start, end, type). Patterns are deliberately
greedy: a false positive costs a little utility, a false negative is a leak.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    type: str
    text: str
    source: str = "regex"


# Order matters only for readability; overlaps are resolved later by length.
PATTERNS: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("URL", re.compile(r"\bhttps?://[^\s<>\"')]+", re.I)),
    # US phone numbers: (713) 555-0123, 713-555-0123, 713.555.0123, +1 713 555 0123
    ("PHONE", re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\b\d{3}\)?[\s.-]?\d{3}[\s.-]\d{4}\b")),
    # SSN-like, including the 9xx range that is never issued (used in synthetic data)
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    # NASA-style award numbers (80NSSC24K1234, 80NM0018D0004), NGA-style (HM04762616008)
    ("GRANT_NUMBER", re.compile(r"\b80N[A-Z]{2,4}\d{2}[A-Z]\d{4}\b|\bHM\d{11}\b")),
    # NIH-style (R01GM123456, 1R21EB012345-01)
    ("GRANT_NUMBER", re.compile(r"\b\d?[A-Z]\d{2}[A-Z]{2}\d{6}(?:-\d{2})?\b")),
    # Generic alphanumeric award / contract numbers: letters and >=3 digits, 8+ chars
    ("GRANT_NUMBER", re.compile(r"\b(?=[A-Z0-9-]*\d[A-Z0-9-]*\d[A-Z0-9-]*\d)(?=[A-Z0-9-]*[A-Z])[A-Z0-9][A-Z0-9-]{7,}\b")),
    # UH cost centre (G + 7 digits) and speedtype (5 digits after the label)
    ("COST_CENTER", re.compile(r"\bG\d{7}\b")),
    ("COST_CENTER", re.compile(r"(?i)(?<=speedtype)[\s:#]*\d{5}\b|(?<=speed type)[\s:#]*\d{5}\b")),
    # 7-digit numbers: UH student/employee IDs, NSF award numbers. Also "1 234 567".
    ("ID_NUMBER", re.compile(r"(?<![\d-])\d{7}(?![\d-])|\b\d\s\d{3}\s\d{3}\b")),
    # Labelled IDs of other lengths ("ID: 12345678", "PeopleSoft #123456")
    ("ID_NUMBER", re.compile(r"(?i)(?<=\bid)[\s:#]*\d{5,10}\b|(?<=peoplesoft)[\s:#]*\d{5,10}\b")),
    # Usernames like jreyes7 / cougarnet ids following a label
    ("ID_NUMBER", re.compile(r"(?i)(?<=cougarnet)[\s:]*(?:id)?[\s:]*[a-z]{2,}\d{1,4}\b|(?<=username)[\s:]*[a-z0-9._-]{3,}\b")),
    ("IP_ADDRESS", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("ADDRESS", re.compile(
        r"\b\d{1,5}\s+(?:[A-Z][a-z]+\s){1,3}(?:St|Street|Ave|Avenue|Blvd|Boulevard|Rd|Road|Dr|Drive|Ln|Lane|Way|Ct|Court|Pkwy|Parkway)\b\.?"
        r"(?:,?\s*(?:Apt|Unit|Suite|#)\s*\w+)?")),
    ("DATE", re.compile(
        r"\b(?:\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}|"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})\b")),
]

# Types that must never survive into the outgoing text (used by the guard).
HIGH_RISK_TYPES = {"EMAIL", "PHONE", "SSN", "GRANT_NUMBER", "COST_CENTER", "ID_NUMBER", "IP_ADDRESS", "ADDRESS", "URL"}

# Markers that mean the document must not leave the machine at all, sanitized or not.
REFUSE_MARKERS = re.compile(
    r"\b(?:CUI|CONTROLLED UNCLASSIFIED|ITAR|EAR99|EXPORT[- ]CONTROLLED|NOFORN|FOUO|"
    r"DISTRIBUTION (?:STATEMENT )?[B-F]\b|PROPRIETARY(?: INFORMATION)?|CONFIDENTIAL - SPONSOR)",
    re.I,
)


def detect(text: str) -> list[Span]:
    from . import places
    spans = [Span(m.start(), m.end(), "LOCATION", m.group(0))
             for pat in (places.pattern(), places.COUNTY_RE) for m in pat.finditer(text)]
    for typ, pat in PATTERNS:
        for m in pat.finditer(text):
            s, e = m.start(), m.end()
            # trim leading separators captured by look-behind labels
            while s < e and text[s] in " :#\t":
                s += 1
            if s < e:
                spans.append(Span(s, e, typ, text[s:e]))
    return spans


def refuse_reasons(text: str) -> list[str]:
    return sorted({m.group(0).upper() for m in REFUSE_MARKERS.finditer(text)})
