"""Local-LLM layer: names, organisations, places and free-text identifiers.

Talks only to a local Ollama server. The model returns surface strings; we keep
only those that occur verbatim in the input, so a hallucinated entity cannot
add text and a paraphrased one is simply dropped (and reported).
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .regex_detect import Span

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
if not OLLAMA_URL.startswith("http"):
    OLLAMA_URL = "http://" + OLLAMA_URL

class LLMDetectError(RuntimeError):
    pass


LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}


def check_host(allow_remote: bool = False) -> None:
    """Records may only be read by a model on this machine (a UH-owned system, in the
    UH case). A remote Ollama, even on your own network, is refused unless allowed."""
    host = urllib.parse.urlparse(OLLAMA_URL).hostname or ""
    if host not in LOCAL_HOSTS and not allow_remote:
        raise LLMDetectError(f"OLLAMA_HOST points off this machine ({host}); refusing. "
                             "Pass --allow-remote-model only if that machine is approved for this data.")


LLM_TYPES = ["PERSON", "ORG", "LOCATION", "ID_NUMBER"]

SYSTEM = """You find personal identifiers in documents so they can be removed before the text leaves the computer.
Return every span that could identify a specific person, directly or together with other facts:
- PERSON: every mention of a person's name, including first name alone, surname alone, nicknames, initials with surname (J. Reyes), misspelled or lowercase names, names inside email headers, signatures and subject lines, and possessives (copy without the 's).
- ORG: names of specific companies, labs, schools or departments other than the main university, and other universities.
- LOCATION: street names, neighbourhoods, towns, counties, specific buildings or rooms, home towns.
- ID_NUMBER: any account, student, employee, award, contract, purchase-order or other reference number, and usernames.
Do NOT return generic roles (the student, the PI, my advisor), pronouns, course subjects, or ordinary words.
Copy each span EXACTLY as it appears in the text, character for character. List each distinct span once.
When unsure, include it: a missed name is worse than an extra one."""

SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "type": {"type": "string", "enum": LLM_TYPES},
                },
                "required": ["text", "type"],
            },
        }
    },
    "required": ["entities"],
}


def _chunks(text: str, limit: int = 3000) -> list[str]:
    paras, out, cur = text.split("\n\n"), [], ""
    for p in paras:
        if cur and len(cur) + len(p) > limit:
            out.append(cur)
            cur = ""
        cur += (p + "\n\n")
    if cur.strip():
        out.append(cur)
    return out or [text]


def _call(model: str, chunk: str, timeout: int, num_ctx: int) -> list[dict]:
    body = {
        "model": model,
        "stream": False,
        "format": SCHEMA,
        "think": "low",
        "options": {"temperature": 0, "num_ctx": num_ctx},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "Document:\n<<<\n" + chunk + "\n>>>"},
        ],
    }
    req = urllib.request.Request(OLLAMA_URL + "/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            resp = json.load(r)
    except (urllib.error.URLError, TimeoutError) as e:
        raise LLMDetectError(f"Ollama call failed ({model}): {e}") from e
    content = resp.get("message", {}).get("content", "")
    try:
        return json.loads(content).get("entities", [])
    except json.JSONDecodeError as e:
        raise LLMDetectError(f"model returned invalid JSON: {content[:200]!r}") from e


def detect(text: str, model: str = "gpt-oss:20b", timeout: int = 300, num_ctx: int = 8192,
           allow_remote: bool = False):
    """Return (spans, dropped, seconds). dropped = model strings not found in the text."""
    check_host(allow_remote)
    t0 = time.time()
    spans, dropped = [], []
    for chunk in _chunks(text):
        for ent in _call(model, chunk, timeout, num_ctx):
            surface = (ent.get("text") or "").strip().strip(".,;:")
            if len(surface) < 2:
                continue
            if surface.lower().endswith("'s"):
                surface = surface[:-2]
            typ = ent.get("type") if ent.get("type") in LLM_TYPES else "PERSON"
            found = False
            for m in re.finditer(re.escape(surface), text):
                spans.append(Span(m.start(), m.end(), typ, m.group(0), source="llm"))
                found = True
            if not found:
                dropped.append(surface)
    return spans, sorted(set(dropped)), time.time() - t0
