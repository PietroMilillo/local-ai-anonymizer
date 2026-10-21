"""laia: local AI anonymizer.

  laia anonymize  FILE                 detect + tokenise locally, write sanitized text and mapping
  laia send       SANITIZED --task ..  wrap in a prompt and send (default: dry-run, nothing sent)
  laia reidentify RESPONSE --map MAP   put the real values back, locally
  laia run        FILE --task ..       all three in one go

Nothing printed by this tool contains an original value: stdout may be read by a
cloud agent. Exit status 2 means the guard blocked the document.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

from . import backends, core, store
from .llm_detect import LLMDetectError
from .pseudonymize import reidentify


def _tag(text: str) -> str:
    # Neutral file names: an input called advising_Reyes.txt must not name its outputs.
    return hashlib.sha256((text + str(time.time())).encode()).hexdigest()[:8]


def _add_anon_args(p):
    p.add_argument("input", type=Path)
    p.add_argument("--detector", choices=["regex", "llm"], default="llm")
    p.add_argument("--model", default="gpt-oss:20b", help="local Ollama model for the llm detector")
    p.add_argument("--no-verify", action="store_true", help="skip the second LLM pass over the sanitized text")
    p.add_argument("--keep-dates", action="store_true")
    p.add_argument("--generalize-money", action="store_true")
    p.add_argument("--generalize-gpa", action="store_true")
    p.add_argument("--allow", action="append", default=[], help="extra term to keep (repeatable)")
    p.add_argument("--allow-warnings", action="store_true", help="proceed despite guard warnings")
    p.add_argument("--allow-remote-model", action="store_true",
                   help="let OLLAMA_HOST point off this machine (only if that machine is approved for the data)")
    p.add_argument("--map", type=Path, help=f"mapping file (default under {store.DEFAULT_DIR})")
    p.add_argument("--no-encrypt", dest="encrypt", action="store_false",
                   help="store the mapping file unencrypted (default: encrypted with a passphrase; "
                        "set ANONYMIZER_PASSPHRASE to skip the prompt)")
    p.add_argument("--outdir", type=Path, default=Path("out"))


def _anonymize(a) -> tuple[core.Result, Path, Path] | None:
    text = a.input.read_text()
    from .pseudonymize import DEFAULT_ALLOWLIST
    allow = DEFAULT_ALLOWLIST | {x.lower() for x in a.allow}
    try:
        r = core.anonymize(text, detector=a.detector, model=a.model, verify=not a.no_verify,
                           keep_dates=a.keep_dates, allowlist=allow,
                           generalize_money=a.generalize_money, generalize_gpa=a.generalize_gpa,
                           allow_remote_model=a.allow_remote_model)
    except LLMDetectError as e:
        print(f"BLOCKED: local detector failed, refusing to fall back silently: {e}")
        return None
    tag = _tag(text)
    a.outdir.mkdir(parents=True, exist_ok=True)
    san = a.outdir / f"sanitized-{tag}.txt"
    mp = a.map or store.DEFAULT_DIR / f"map-{tag}.json"
    store.save(r.mapping, mp, encrypt=a.encrypt)

    types = Counter(e["type"] for e in r.audit["entities"])
    print(f"detector: {a.detector}" + (f" ({a.model})" if a.detector == "llm" else ""))
    print("replaced entities: " + (", ".join(f"{k} {v}" for k, v in sorted(types.items())) or "none"))
    print("replacements: %d" % sum(e["replacements"] for e in r.audit["entities"]))
    if r.audit.get("llm_strings_not_in_text"):
        print(f"model strings not found verbatim (ignored): {r.audit['llm_strings_not_in_text']}")
    print("time: " + ", ".join(f"{k} {v:.1f}s" for k, v in r.seconds.items()))
    for q in r.quasi:
        print(f"quasi-identifier {q['type']}: {q['count']} left in text")
    print(f"mapping: {mp}  (Level 1 data: keep local)")
    for b in r.blocks:
        print("BLOCK: " + b)
    warns = list(r.warns)
    if a.detector == "regex":
        warns.append("regex detector does not look for names, organizations or most places; use --detector llm")
    for w in warns:
        print("WARN:  " + w)
    if r.blocks or (warns and not a.allow_warnings):
        print("BLOCKED: nothing written for sending. Review the input, then rerun.")
        return None
    san.write_text(r.sanitized)
    print(f"sanitized: {san}")
    return r, san, mp


def main(argv=None):
    ap = argparse.ArgumentParser(prog="laia", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_an = sub.add_parser("anonymize")
    _add_anon_args(p_an)

    p_send = sub.add_parser("send")
    p_send.add_argument("sanitized", type=Path)
    p_send.add_argument("--task", required=True)
    p_send.add_argument("--backend", choices=["dry-run", "file", "claude-cli"], default="dry-run")
    p_send.add_argument("--cloud-model")
    p_send.add_argument("--outdir", type=Path, default=Path("out"))

    p_re = sub.add_parser("reidentify")
    p_re.add_argument("response", type=Path)
    p_re.add_argument("--map", type=Path, required=True)
    p_re.add_argument("-o", "--output", type=Path)

    p_run = sub.add_parser("run")
    _add_anon_args(p_run)
    p_run.add_argument("--task", required=True)
    p_run.add_argument("--backend", choices=["dry-run", "file", "claude-cli"], default="dry-run")
    p_run.add_argument("--cloud-model")

    a = ap.parse_args(argv)

    if a.cmd == "anonymize":
        return 0 if _anonymize(a) else 2

    if a.cmd == "reidentify":
        out, unknown = reidentify(a.response.read_text(), store.load(a.map))
        dest = a.output or a.response.with_name(a.response.stem + ".reidentified.txt")
        dest.write_text(out)
        print(f"re-identified: {dest}")
        if unknown:
            print(f"WARN: {len(unknown)} token(s) in the response are not in the mapping")
        return 0

    if a.cmd == "send":
        san = a.sanitized
        prompt = backends.build_prompt(a.task, san.read_text())
        outgoing = a.outdir / f"outgoing-{san.stem.split('-')[-1]}.txt"
        response = a.outdir / f"response-{san.stem.split('-')[-1]}.txt"
        a.outdir.mkdir(parents=True, exist_ok=True)
        got = backends.send(prompt, a.backend, outgoing, response, model=a.cloud_model)
        print(f"outgoing prompt: {outgoing}")
        if got is None:
            print(f"backend {a.backend}: nothing sent. Save the reply as {response}, then run reidentify.")
        else:
            print(f"response: {response}")
        return 0

    if a.cmd == "run":
        res = _anonymize(a)
        if not res:
            return 2
        r, san, mp = res
        tag = san.stem.split("-")[-1]
        outgoing, response = a.outdir / f"outgoing-{tag}.txt", a.outdir / f"response-{tag}.txt"
        got = backends.send(backends.build_prompt(a.task, r.sanitized), a.backend, outgoing, response,
                            model=a.cloud_model)
        print(f"outgoing prompt: {outgoing}")
        if got is None:
            print(f"backend {a.backend}: nothing sent. Save the reply as {response}, then:\n"
                  f"  laia reidentify {response} --map {mp}")
            return 0
        out, unknown = reidentify(got, r.mapping)
        dest = a.outdir / f"final-{tag}.txt"
        dest.write_text(out)
        print(f"re-identified answer: {dest}")
        if unknown:
            print(f"WARN: {len(unknown)} token(s) in the response are not in the mapping")
        return 0


if __name__ == "__main__":
    sys.exit(main())
