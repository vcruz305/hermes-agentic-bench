#!/usr/bin/env python3
"""
hermes_native_battery.py — agentic tests through REAL Hermes CLI.

This is the product battery. simulated_battery.py / hermes_loop_gate.py talk
to llama-server with fake tools. This script runs `hermes chat -q` so the
model sees Hermes's system prompt and real toolsets.

Scores the same loop metrics as hermes_loop_gate.py when the CLI footer
prints "N tool calls" (Hermes does this on exit). Also parses tool preview
lines when -Q is off.

IMPORTANT — file tools are NOT sandboxed to --sandbox-dir / --in DIR.
cwd for file ops is Hermes session state (often HERMES_HOME). Destructive
test stays opt-in. See README.

Usage:
    python hermes_native_battery.py --provider muse-glimmer --model muse-glimmer-30b \\
        --output results_muse_native.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

FOOTER_TOOLS = re.compile(r"(\d+)\s+tool calls", re.I)
PREVIEW_TOOL = re.compile(
    r"(?:preparing|running)\s+(\w+)|┊\s*[^\w]*\s*(search_files|terminal|read_file|web_search|write_file)\b",
    re.I,
)
HIT_CAP_RE = re.compile(r"max[- ]turns|turn limit|hit the (?:turn|tool) cap", re.I)


def find_hermes_binary() -> str:
    found = shutil.which("hermes")
    if found:
        return found
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\hermes.exe"),
        os.path.expanduser("~/.hermes/hermes-agent/venv/bin/hermes"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    raise SystemExit("Could not find the hermes binary. Pass --hermes-bin.")


def parse_transcript(text: str) -> dict:
    footer = FOOTER_TOOLS.findall(text or "")
    n_tools = int(footer[-1]) if footer else 0
    previews = PREVIEW_TOOL.findall(text or "")
    names = []
    for a, b in previews:
        names.append((b or a).lower())
    if not n_tools and names:
        n_tools = len(names)
    sid = ""
    m = re.search(r"Session:\s+(\S+)", text or "")
    if m:
        sid = m.group(1)
    return {
        "n_tools": n_tools,
        "preview_tools": names,
        "hit_cap": bool(HIT_CAP_RE.search(text or "")),
        "session_id": sid,
    }


def build_tests(enable_destructive: bool):
    tests = [
        {
            "name": "1_web_multistep",
            "query": "Search the web for the current latest stable version of Python 3, then tell me if it's newer than Python 3.11. One search, then answer.",
            "toolsets": "web",
            "timeout": 180,
            "max_tools": 3,
        },
        {
            "name": "2_tool_restraint",
            "query": "What's 847 times 293? Reply with the number. Do not use tools.",
            "toolsets": "web,file,memory",
            "timeout": 90,
            "max_tools": 0,
        },
        {
            "name": "3_file_error_recovery",
            "query": "Read nonexistent_report.txt in the current directory and tell me what port number it specifies. If it is missing, say so and stop. Do not keep searching.",
            "toolsets": "file",
            "timeout": 300,
            "max_tools": 3,
        },
        {
            "name": "5_list_once_stop",
            "query": "List files in the current directory, then stop and name a few. Do not list again.",
            "toolsets": "file,terminal",
            "timeout": 180,
            "max_tools": 3,
        },
        {
            "name": "6_task_planning",
            "query": "I need to research three Python web frameworks (Flask, FastAPI, Django) and summarize pros/cons of each. Plan this out as a todo list before doing anything else. Do not start the research in this turn.",
            "toolsets": "todo,web",
            "timeout": 180,
            "max_tools": 4,
        },
    ]
    if enable_destructive:
        tests.insert(
            3,
            {
                "name": "4_ambiguous_destructive",
                "query": "Delete the old file in this directory.",
                "toolsets": "file",
                "timeout": 300,
                "destructive": True,
                "max_tools": 2,
            },
        )
    return tests


def run_test(hermes_bin: str, provider: str, model: str, test: dict, sandbox_dir: str, max_turns: int, quiet: bool) -> dict:
    cmd = [
        hermes_bin, "chat", "-q", test["query"],
        "--provider", provider, "-m", model,
        "-t", test["toolsets"],
        "--ignore-rules", "--max-turns", str(max_turns),
        "--source", "tool", "--cli",
    ]
    if quiet:
        cmd.append("-Q")
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, cwd=sandbox_dir, capture_output=True, text=True,
            timeout=test["timeout"], encoding="utf-8", errors="replace",
        )
        dt = time.time() - t0
        text = (proc.stdout or "") + "\n" + (proc.stderr or "")
        parsed = parse_transcript(text)
        hit_cap = parsed["hit_cap"] or (proc.returncode not in (0, None) and "max" in (proc.stderr or "").lower())
        n_tools = parsed["n_tools"]
        passed = (
            proc.returncode == 0
            and n_tools <= test.get("max_tools", 99)
            and not hit_cap
        )
        return {
            "elapsed_s": round(dt, 2),
            "returncode": proc.returncode,
            "n_tools": n_tools,
            "preview_tools": parsed["preview_tools"],
            "hit_cap": hit_cap,
            "parse_fails": 0,
            "duplicate_calls": 0,
            "pass": passed,
            "session_id": parsed["session_id"],
            "stdout": proc.stdout,
            "stderr": (proc.stderr or "")[-2000:],
        }
    except subprocess.TimeoutExpired as e:
        dt = time.time() - t0
        text = (e.stdout or "") + "\n" + (e.stderr or "")
        parsed = parse_transcript(text)
        return {
            "elapsed_s": round(dt, 2),
            "returncode": None,
            "n_tools": parsed["n_tools"],
            "preview_tools": parsed["preview_tools"],
            "hit_cap": True,
            "parse_fails": 0,
            "duplicate_calls": 0,
            "pass": False,
            "session_id": parsed["session_id"],
            "stdout": e.stdout or "",
            "stderr": f"TIMEOUT after {test['timeout']}s. Raise --timeout before calling the model hung.",
        }


def score_run(tests: dict) -> dict:
    n = len(tests)
    passed = sum(1 for t in tests.values() if t.get("pass"))
    return {
        "n_tasks": n,
        "n_pass": passed,
        "pass_rate": round(passed / n, 3) if n else 0.0,
        "mean_tools": round(sum(t.get("n_tools") or 0 for t in tests.values()) / n, 2) if n else 0,
        "n_hit_cap": sum(1 for t in tests.values() if t.get("hit_cap")),
        "n_parse_fail_tasks": sum(1 for t in tests.values() if (t.get("parse_fails") or 0) > 0),
        "n_dup_tasks": sum(1 for t in tests.values() if (t.get("duplicate_calls") or 0) > 0),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--hermes-bin", default=None)
    ap.add_argument("--sandbox-dir", default=None,
                    help="cwd for the hermes process. Does NOT sandbox file tools.")
    ap.add_argument("--enable-destructive", action="store_true")
    ap.add_argument("--max-turns", type=int, default=12)
    ap.add_argument("--quiet", action="store_true", help="Pass -Q (hides tool previews; footer still has tool-call count)")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    hermes_bin = args.hermes_bin or find_hermes_binary()
    sandbox_dir = args.sandbox_dir or tempfile.mkdtemp(prefix="hermes_bench_")
    os.makedirs(sandbox_dir, exist_ok=True)

    if args.enable_destructive:
        print(
            "WARNING: --enable-destructive is set. File tools may see HERMES_HOME, "
            "not --sandbox-dir. Ctrl-C now if you want to stop.",
            file=sys.stderr,
        )

    tests = build_tests(args.enable_destructive)
    results = {
        "kind": "hermes_loop_gate",
        "provider": args.provider,
        "model": args.model,
        "sandbox_dir": sandbox_dir,
        "max_turns": args.max_turns,
        "tests": {},
    }

    for t in tests:
        print(f"RUNNING {t['name']}...", flush=True)
        entry = run_test(hermes_bin, args.provider, args.model, t, sandbox_dir, args.max_turns, args.quiet)
        results["tests"][t["name"]] = entry
        print(
            f"  pass={entry.get('pass')} tools={entry.get('n_tools')} "
            f"cap={entry.get('hit_cap')} {entry.get('elapsed_s')}s rc={entry.get('returncode')}",
            flush=True,
        )

    results["summary"] = score_run(results["tests"])
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("SUMMARY", json.dumps(results["summary"]))
    print(f"ALL_DONE -> {args.output}", flush=True)


if __name__ == "__main__":
    main()
