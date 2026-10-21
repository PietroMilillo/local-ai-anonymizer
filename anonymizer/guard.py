"""Fail-closed checks on the text that is about to leave the machine.

Messages give line numbers, never the values, because stdout may itself be read
by a cloud agent. Any blocking finding stops the pipeline. Warnings also stop it unless the user
passes --allow-warnings after reading them.
"""
from __future__ import annotations

import re

from . import regex_detect
from .pseudonymize import COMMON_WORDS, TOKEN_RE


def _line(text, pos):
    return text.count("\n", 0, pos) + 1


def check(original: str, sanitized: str, mapping: dict, skipped_parts=(), verify_spans=None):
    blocks, warns = [], []

    reasons = regex_detect.refuse_reasons(original)
    if reasons:
        blocks.append("refuse marker in input (CUI / export control / proprietary): " + ", ".join(reasons))

    stripped = TOKEN_RE.sub(" ", sanitized)
    for sp in regex_detect.detect(stripped):
        if sp.type in regex_detect.HIGH_RISK_TYPES:
            blocks.append(f"{sp.type} pattern still present at line {_line(stripped, sp.start)}")

    low = sanitized.lower()
    for tok, v in mapping.items():
        for s in v["surfaces"]:
            if s.lower() in COMMON_WORDS:
                continue  # checked case-sensitively below
            m = re.search(r"(?<!\w)%s(?!\w)" % re.escape(s.lower()), low) if len(s) >= 3 else None
            if m:
                blocks.append(f"original text for {tok} still present at line {_line(low, m.start())}")
                break

    for part in skipped_parts:
        # Common-word name parts are replaced only when capitalised; any capitalised one left is a leak.
        m = re.search(r"(?<!\w)%s(?!\w)" % re.escape(part), sanitized)
        if m:
            blocks.append(f"a name part that is also a common word is left at line {_line(sanitized, m.start())}")

    if verify_spans:
        for sp in verify_spans:
            if not TOKEN_RE.search(sp.text) and sp.type == "PERSON":
                blocks.append(f"verification pass found an unreplaced name at line {_line(sanitized, sp.start)}")
    return sorted(set(blocks)), sorted(set(warns))
