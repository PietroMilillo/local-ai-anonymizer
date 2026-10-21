"""Measure what leaks. Runs one detector configuration over the synthetic corpus.

  python -m eval.evaluate --corpus corpus --config regex
  python -m eval.evaluate --corpus corpus --config llm:gpt-oss:20b [--no-verify]

Unit of measurement: each distinct planted identifier string per document.
A PERSON value counts as leaked if any part of it (surname, first name)
survives; common-word parts (Grant, Hope, Will) are matched case-sensitively.
"Effective" leaks are leaks in documents the guard did not block, i.e. text
that would actually have been sent.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from pathlib import Path

from anonymizer import core
from anonymizer.llm_detect import LLMDetectError
from anonymizer.pseudonymize import COMMON_WORDS

QUASI_TYPES = {"DATE"}


def leaked(value: str, typ: str, text: str) -> bool:
    if typ == "PERSON":
        for part in re.split(r"[\s,.]+", value):
            if len(part) < 2:
                continue
            if part.lower() in COMMON_WORDS:
                if re.search(r"(?<!\w)%s(?!\w)" % re.escape(part), text):
                    return True
            elif re.search(r"(?<!\w)%s(?!\w)" % re.escape(part), text, re.I):
                return True
        return False
    return re.search(r"(?<!\w)%s(?!\w)" % re.escape(value), text, re.I) is not None


def overlaps_truth(surface: str, truth_values: list[str]) -> bool:
    s = surface.lower()
    return any(s in v.lower() or v.lower() in s for v in truth_values)


def run(corpus: Path, config: str, verify: bool, out: Path):
    truth = json.loads((corpus / "truth.json").read_text())
    detector, _, model = config.partition(":")
    rows = []
    for doc_id, planted in sorted(truth.items()):
        text = (corpus / f"{doc_id}.txt").read_text()
        t0 = time.time()
        try:
            r = core.anonymize(text, detector=detector, model=model or "gpt-oss:20b", verify=verify)
            err = None
        except LLMDetectError as e:
            r, err = None, str(e)
        secs = time.time() - t0
        if r is None:
            rows.append({"doc": doc_id, "error": err, "blocked": True, "seconds": secs})
            continue
        uniq = {}
        for p in planted:
            uniq.setdefault((p["value"], p["type"]), p["case"])
        ids = [{"value": v, "type": t, "case": c, "leaked": leaked(v, t, r.sanitized)} for (v, t), c in uniq.items()]
        tv = [p["value"] for p in planted]
        fps = [s for e in r.mapping.values() for s in e["surfaces"] if not overlaps_truth(s, tv)]
        rows.append({"doc": doc_id, "blocked": bool(r.blocks), "warned": bool(r.warns), "ids": ids,
                     "false_positives": sorted(set(fps)), "seconds": secs, "n_blocks": len(r.blocks)})
    out.mkdir(parents=True, exist_ok=True)
    tag = config.replace(":", "_") + ("" if verify or detector == "regex" else "_noverify")
    (out / f"{tag}.json").write_text(json.dumps(rows, indent=1))
    return tag, summarize(rows)


def summarize(rows):
    s = {"docs": len(rows), "errors": sum(1 for r in rows if r.get("error"))}
    direct = [(r, i) for r in rows if "ids" in r for i in r["ids"] if i["type"] not in QUASI_TYPES]
    quasi = [(r, i) for r in rows if "ids" in r for i in r["ids"] if i["type"] in QUASI_TYPES]
    s["direct_ids"] = len(direct)
    s["direct_leaked"] = sum(i["leaked"] for _, i in direct)
    s["recall"] = 1 - s["direct_leaked"] / max(1, len(direct))
    s["dates_leaked"] = sum(i["leaked"] for _, i in quasi)
    s["dates"] = len(quasi)
    leak_docs = [r for r in rows if "ids" in r and any(i["leaked"] and i["type"] not in QUASI_TYPES for i in r["ids"])]
    s["docs_with_leak"] = len(leak_docs)
    s["docs_blocked"] = sum(1 for r in rows if r["blocked"] or r.get("warned"))
    s["docs_leak_sent"] = sum(1 for r in leak_docs if not (r["blocked"] or r.get("warned")))
    s["docs_blocked_clean"] = sum(1 for r in rows if (r["blocked"] or r.get("warned")) and r not in leak_docs)
    s["fp_per_doc"] = sum(len(r.get("false_positives", [])) for r in rows) / max(1, len(rows))
    s["sec_per_doc"] = sum(r["seconds"] for r in rows) / max(1, len(rows))
    by_type, by_case = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for _, i in direct:
        by_type[i["type"]][0] += i["leaked"]
        by_type[i["type"]][1] += 1
        by_case[i["case"]][0] += i["leaked"]
        by_case[i["case"]][1] += 1
    s["leaked_by_type"] = {k: f"{v[0]}/{v[1]}" for k, v in sorted(by_type.items())}
    s["leaked_by_case"] = {k: f"{v[0]}/{v[1]}" for k, v in sorted(by_case.items())}
    return s


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, default=Path("corpus"))
    ap.add_argument("--config", required=True)
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--out", type=Path, default=Path("results"))
    a = ap.parse_args(argv)
    tag, s = run(a.corpus, a.config, not a.no_verify, a.out)
    (a.out / f"{tag}.summary.json").write_text(json.dumps(s, indent=1))
    print(json.dumps({tag: s}, indent=1))


if __name__ == "__main__":
    main()
