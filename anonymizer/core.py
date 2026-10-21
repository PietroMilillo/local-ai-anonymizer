"""One call that runs detection, tokenisation, generalisation and the guard."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import guard, llm_detect, quasi, regex_detect
from .pseudonymize import DEFAULT_ALLOWLIST, TOKEN_RE, pseudonymize


@dataclass
class Result:
    sanitized: str
    mapping: dict
    audit: dict
    blocks: list
    warns: list
    quasi: list
    seconds: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.blocks


def anonymize(text: str, detector: str = "regex", model: str = "gpt-oss:20b", verify: bool = True,
              keep_dates: bool = False, allowlist=None, generalize_money=False, generalize_gpa=False,
              timeout: int = 300, allow_remote_model: bool = False) -> Result:
    allowlist = DEFAULT_ALLOWLIST if allowlist is None else allowlist
    secs = {}
    t0 = time.time()
    spans = regex_detect.detect(text)
    secs["regex"] = time.time() - t0
    dropped = []
    if detector == "llm":
        llm_spans, dropped, secs["llm"] = llm_detect.detect(text, model=model, timeout=timeout, allow_remote=allow_remote_model)
        spans += llm_spans
    elif detector != "regex":
        raise ValueError(detector)

    sanitized, mapping, audit = pseudonymize(text, spans, allowlist=allowlist, keep_dates=keep_dates)
    sanitized = quasi.generalize(sanitized, money=generalize_money, gpa=generalize_gpa)
    audit["llm_strings_not_in_text"] = len(dropped)

    verify_spans = None
    if detector == "llm" and verify:
        vs, _, secs["verify"] = llm_detect.detect(sanitized, model=model, timeout=timeout, allow_remote=allow_remote_model)
        verify_spans = [s for s in vs if s.text.strip().lower() not in allowlist and not TOKEN_RE.search(s.text)]
    blocks, warns = guard.check(text, sanitized, mapping, audit["common_word_parts"], verify_spans)
    return Result(sanitized, mapping, audit, blocks, warns, quasi.report(sanitized), secs)
