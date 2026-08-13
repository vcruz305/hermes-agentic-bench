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
    if isinstance(entry, dict) and "pass" in entry and "n_tools" in entry:
        mark = "PASS" if entry.get("pass") else "FAIL"
        bits = [mark, f"tools={entry.get('n_tools')}"]
        if entry.get("hit_cap"):
            bits.append("HIT_CAP")
        if entry.get("parse_fails"):
            bits.append(f"parse={entry['parse_fails']}")
        if entry.get("duplicate_calls"):
            bits.append(f"dup={entry['duplicate_calls']}")
        if entry.get("error"):
            bits.append("error")
        return " ".join(bits)
    if isinstance(entry, dict) and "turn1" in entry:
        last_key = sorted(k for k in entry.keys() if k.startswith("turn"))[-1]
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
    if any(r.get("kind") == "hermes_loop_gate" for r in runs):
        lines.append("## Loop-gate summary")
        lines.append("")
        lines.append("| Run | pass | mean tools | HIT_CAP | parse-fail tasks | dup tasks |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for r in runs:
            s = r.get("summary") or {}
            if not s:
                continue
            lines.append(
                f"| {label_of(r)} | {s.get('n_pass')}/{s.get('n_tasks')} "
                f"({s.get('pass_rate')}) | {s.get('mean_tools')} | "
                f"{s.get('n_hit_cap')} | {s.get('n_parse_fail_tasks')} | "
                f"{s.get('n_dup_tasks')} |"
            )
        lines.append("")
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
