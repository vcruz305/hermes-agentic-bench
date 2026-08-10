#!/usr/bin/env python3
"""
generate_report.py — turn one or more result JSON files (from either
simulated_battery.py or hermes_native_battery.py) into a single readable
Markdown comparison table.

Usage:
    python generate_report.py results_bonsai.json results_glimmer.json --output comparison.md
"""

import argparse
import json


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def label_of(run):
    return run.get("model") or run.get("provider") or "unknown"


def test_summary(entry):
    if entry is None:
        return "not run"
    if isinstance(entry, dict) and "turn1" in entry:
        # multi-turn simulated test
        last_key = sorted(entry.keys())[-1]
        entry = entry[last_key]
    elapsed = entry.get("elapsed_s")
    finish = entry.get("finish_reason") or entry.get("returncode")
    return f"{elapsed}s (finish={finish})" if elapsed is not None else "n/a"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", nargs="+", help="Result JSON files to compare")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    runs = [load(p) for p in args.results]
    all_test_names = []
    for run in runs:
        for name in run.get("tests", {}).keys():
            if name not in all_test_names:
                all_test_names.append(name)
    all_test_names.sort()

    lines = ["# Agentic battery comparison", ""]
    lines.append("| Test | " + " | ".join(label_of(r) for r in runs) + " |")
    lines.append("|---|" + "---|" * len(runs))
    for name in all_test_names:
        row = [name]
        for run in runs:
            row.append(test_summary(run.get("tests", {}).get(name)))
        lines.append("| " + " | ".join(row) + " |")

    lines.append("")
    lines.append("Raw source files: " + ", ".join(args.results))

    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
