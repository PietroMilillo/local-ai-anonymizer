"""Turn detected spans into consistent tokens and back.

Every mention of the same entity gets the same token ([PERSON_1]) so the cloud
model can still reason about who did what. The mapping table is the only way
back and is Level 1 data in its own right: it never leaves the machine.
"""
from __future__ import annotations

import re
from collections import defaultdict

from .regex_detect import Span

# Kept in the text because they are context, not identifiers. Extend per use.
DEFAULT_ALLOWLIST = {
    "university of houston", "uh", "cullen college of engineering", "nasa", "nsf", "nih",
    "doe", "dod", "nga", "ferpa", "texas", "houston", "houston, tx", "united states", "usa", "us",
    "office of contracts and grants", "division of research", "disability office",
}

# Name parts that are also ordinary words. They are expanded case-sensitively only
# ("Grant" yes, "grant budget" no), and the guard checks them case-sensitively.
COMMON_WORDS = {
    "grant", "hope", "may", "june", "april", "august", "will", "mark", "bill", "rose", "faith",
    "dean", "chase", "hunter", "summer", "joy", "grace", "art", "frank", "earnest", "young",
    "long", "white", "black", "brown", "green", "rich", "price", "page", "hall", "king", "love",
    "case", "lane", "park", "ford", "story", "sterling", "major", "dr", "prof", "mr", "ms", "mrs",
}

TOKEN_TYPES = ["PERSON", "ORG", "LOCATION", "ID_NUMBER", "EMAIL", "PHONE", "SSN", "GRANT_NUMBER",
               "COST_CENTER", "IP_ADDRESS", "ADDRESS", "URL", "DATE"]
TOKEN_RE = re.compile(r"\[(?:%s)_\d+\]" % "|".join(TOKEN_TYPES))


def _norm(typ: str, s: str) -> str:
    if typ in {"PHONE", "SSN", "ID_NUMBER", "COST_CENTER"}:
        d = re.sub(r"\D", "", s)
        return d[-10:] if typ == "PHONE" else d
    return re.sub(r"\s+", " ", s.strip().lower())


def _name_parts(s: str) -> list[str]:
    return [p for p in re.split(r"[\s.,]+", s) if len(p) >= 3]


TITLE_RE = re.compile(r"^(?:Dr|Prof|Professor|Mr|Ms|Mrs|Mx)\.?\s+")


def _strip_title(sp: Span) -> Span:
    """Leave "Dr." in the text so the reply does not come back as "Dr. Dr. Name"."""
    if sp.type != "PERSON":
        return sp
    m = TITLE_RE.match(sp.text)
    if not m or m.end() >= len(sp.text):
        return sp
    return Span(sp.start + m.end(), sp.end, sp.type, sp.text[m.end():], sp.source)


def _edit1(a: str, b: str) -> bool:
    """True if a and b differ by exactly one insertion, deletion or substitution."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b):
        a, b = b, a
    return any(a == b[:i] + b[i + 1:] for i in range(len(b)))


def _pattern(surface: str, case_sensitive: bool) -> str:
    body = re.escape(surface).replace(r"\ ", r"\s+")
    body = body if case_sensitive else "(?i:%s)" % body
    return r"(?<!\w)%s(?!\w)" % body


def build_entities(text: str, spans: list[Span], allowlist=None, keep_dates=False):
    allowlist = DEFAULT_ALLOWLIST if allowlist is None else allowlist
    spans = [s for s in spans if s.text.strip().lower() not in allowlist
             and not (keep_dates and s.type == "DATE") and not TOKEN_RE.fullmatch(s.text)]
    spans = [_strip_title(s) for s in spans]
    # The model often returns "award 80NSSC..." or "UH ID 1828004". Keep the regex span
    # (typed, label left readable) and drop the model's wider ID_NUMBER span.
    structured = [s for s in spans if s.source == "regex" and s.type not in {"LOCATION", "DATE"}]
    spans = [s for s in spans if not (
        s.source == "llm" and s.type == "ID_NUMBER" and
        any(r.start >= s.start and r.end <= s.end and (r.end - r.start) < (s.end - s.start) for r in structured))]
    spans.sort(key=lambda s: (s.start, -(s.end - s.start)))
    # When regex and model both flag the same string, the regex type is more specific.
    regex_type = {s.text.lower(): s.type for s in spans if s.source == "regex"}

    # Group surfaces into entities. People sharing a name part (or a near-miss
    # spelling of one, e.g. "McAlliste") are one entity.
    groups: list[dict] = []
    index: dict[tuple[str, str], int] = {}
    part_index: dict[str, int] = {}
    common_index: dict[str, int] = {}
    for sp in spans:
        typ = regex_type.get(sp.text.lower(), sp.type)
        key = (typ, _norm(typ, sp.text))
        if key in index:
            g = groups[index[key]]
        else:
            gid = None
            if typ == "PERSON":
                parts = _name_parts(sp.text)
                for part in parts:
                    pl = part.lower()
                    if pl in COMMON_WORDS:
                        # "Grant" alone joins "Grant Whitfield"; "Grant Okafor" does not join him.
                        if len(parts) == 1 and pl in common_index:
                            gid = common_index[pl]
                            break
                        continue
                    if pl in part_index:
                        gid = part_index[pl]
                        break
                    near = [k for k in part_index if len(pl) >= 5 and _edit1(pl, k)]
                    if near:
                        gid = part_index[near[0]]
                        break
            if gid is None:
                gid = len(groups)
                groups.append({"type": typ, "surfaces": [], "sources": set(), "first": sp.start})
            g = groups[gid]
            index[key] = gid
        if sp.text not in g["surfaces"]:
            g["surfaces"].append(sp.text)
        g["sources"].add(sp.source)
        if typ == "PERSON":
            for part in _name_parts(sp.text):
                if part.lower() not in COMMON_WORDS:
                    part_index.setdefault(part.lower(), index[key])
                elif len(_name_parts(sp.text)) > 1:
                    common_index.setdefault(part.lower(), index[key])
    return groups


def pseudonymize(text: str, spans: list[Span], allowlist=None, keep_dates=False):
    """Return (sanitized_text, mapping, audit)."""
    groups = build_entities(text, spans, allowlist, keep_dates)
    groups.sort(key=lambda g: g["first"])
    counters: dict[str, int] = defaultdict(int)
    alts: list[tuple[str, str, str]] = []  # (surface, token, pattern)
    lookup: dict[str, str] = {}
    mapping, skipped_parts = {}, set()
    for g in groups:
        counters[g["type"]] += 1
        token = f"[{g['type']}_{counters[g['type']]}]"
        surfaces = list(g["surfaces"])
        expanded, exact = [], []
        if g["type"] == "PERSON":
            for s in g["surfaces"]:
                for part in _name_parts(s):
                    if part in surfaces or part in expanded or part in exact:
                        continue
                    if part.lower() in COMMON_WORDS:
                        # "Grant", "Hope": replace only the capitalised form, so "the grant
                        # budget" survives. A sentence-initial "Grant funds..." is replaced too:
                        # a wasted word costs less than a leaked name.
                        if part[0].isupper() and part.lower() not in {"dr", "prof", "mr", "ms", "mrs"}:
                            exact.append(part)
                            skipped_parts.add(part)
                    else:
                        expanded.append(part)
        for s in surfaces:
            alts.append((s, token, _pattern(s, case_sensitive=False)))
            lookup[s.lower()] = token
        for p in expanded:
            alts.append((p, token, _pattern(p, case_sensitive=False)))
            lookup.setdefault(p.lower(), token)
        for p in exact:
            alts.append((p, token, _pattern(p, case_sensitive=True)))
            lookup.setdefault(p.lower(), token)
        mapping[token] = {"type": g["type"], "canonical": max(surfaces, key=len),
                          "surfaces": surfaces + expanded, "exact_case_parts": exact,
                          "sources": sorted(g["sources"])}

    counts: dict[str, int] = defaultdict(int)
    if alts:
        alts.sort(key=lambda a: -len(a[0]))
        big = re.compile("|".join(a[2] for a in alts))

        def repl(m):
            tok = lookup.get(m.group(0).lower())
            if tok is None:  # whitespace variant of a multi-word surface
                tok = lookup.get(re.sub(r"\s+", " ", m.group(0)).lower(), "[REDACTED]")
            counts[tok] += 1
            return tok

        sanitized = big.sub(repl, text)
    else:
        sanitized = text
    audit = {
        "entities": [{"token": t, "type": v["type"], "replacements": counts.get(t, 0),
                      "sources": v["sources"], "n_surfaces": len(v["surfaces"])}
                     for t, v in mapping.items()],
        "common_word_parts": sorted(skipped_parts),
    }
    return sanitized, mapping, audit


REID_RE = re.compile(r"\[\s*(%s)[ _-]?(\d+)\s*\]|\b(%s)_(\d+)\b" % ("|".join(TOKEN_TYPES), "|".join(TOKEN_TYPES)),
                     re.I)


def reidentify(response: str, mapping: dict):
    """Replace tokens (and near-miss spellings like 'Person_1') with the original text."""
    unknown = set()

    def repl(m):
        typ = (m.group(1) or m.group(3)).upper()
        num = m.group(2) or m.group(4)
        tok = f"[{typ}_{num}]"
        if tok in mapping:
            return mapping[tok]["canonical"]
        unknown.add(m.group(0))
        return m.group(0)

    return REID_RE.sub(repl, response), sorted(unknown)
