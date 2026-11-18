#!/usr/bin/env python3
"""Deterministic Requirement Traceability gate.

Reads .stories/<KEY>/02-traceability.json (written by the requirement-traceability
agent), computes the coverage score and compares it to traceability.threshold
in .claude/qe.config.yaml (default 75).

score = sum(weight[status]) / count(criteria where status != not_applicable) * 100
weights default: implemented=1.0, partial=0.5, not_found=0.0

Exit code: 0 = gate passed, 2 = gate failed, 1 = input error.

Usage:
  trace_score.py KEY [--file PATH] [--no-state]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from common import config, die, out, read_json, story_dir, validate_key, write_json

VALID = {"implemented", "partial", "not_found", "not_applicable"}


def score(doc: dict, weights: dict, threshold: float) -> dict:
    criteria = doc.get("criteria") or []
    if not criteria:
        die("No 'criteria' in traceability JSON.")
    rows, total, counted = [], 0.0, 0
    for c in criteria:
        status = c.get("status")
        if status not in VALID:
            die(f"Criterion {c.get('id')} has invalid status '{status}'. Valid: {sorted(VALID)}")
        if status in ("implemented", "partial") and not c.get("evidence"):
            die(f"Criterion {c.get('id')} is '{status}' but has no evidence (file:line required).")
        if status == "not_applicable":
            rows.append({"id": c.get("id"), "status": status, "weight": None})
            continue
        w = float(weights.get(status, 0.0))
        total += w
        counted += 1
        rows.append({"id": c.get("id"), "status": status, "weight": w})
    if counted == 0:
        die("All criteria are not_applicable; nothing to score.")
    pct = round(total / counted * 100, 2)
    return {
        "score": pct,
        "threshold": threshold,
        "passed": pct >= threshold,
        "counted_criteria": counted,
        "breakdown": rows,
        "gaps": [r["id"] for r in rows if r["status"] in ("partial", "not_found")],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("key")
    ap.add_argument("--file", help="Override path to traceability JSON")
    ap.add_argument("--no-state", action="store_true", help="Do not write result into state.json")
    a = ap.parse_args()
    key = validate_key(a.key)
    cfg = config().get("traceability", {})
    threshold = float(cfg.get("threshold", 75))
    weights = cfg.get("weights") or {"implemented": 1.0, "partial": 0.5, "not_found": 0.0}

    path = a.file or story_dir(key) / "02-traceability.json"
    doc = read_json(path)
    result = score(doc, weights, threshold)

    # Stamp result into the traceability doc and the story state
    doc["score"] = {k: result[k] for k in ("score", "threshold", "passed", "gaps")}
    doc["score"]["computed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_json(path, doc)
    if not a.no_state:
        state_p = story_dir(key) / "state.json"
        if state_p.is_file():
            st = read_json(state_p)
            st.setdefault("gates", {}).setdefault("traceability", {}).update(
                score=result["score"], threshold=threshold, passed=result["passed"])
            write_json(state_p, st)

    out(result)
    sys.exit(0 if result["passed"] else 2)


if __name__ == "__main__":
    main()
