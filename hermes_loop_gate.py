#!/usr/bin/env python3
"""
hermes_loop_gate.py — 20-task gate for Muse/Hermes-style tool loops.

The original simulated_battery.py (6 tests) is a first-pass read on chaining
and recovery. Community Muse+Hermes reports are different: the model *does*
call tools, then never stops (50–150 terminal calls), or emits ATEM/XML that
Hermes cannot parse.

This gate scores what those reports care about:

  parse_ok          assistant produced OpenAI tool_calls or a final answer
  n_tools           number of tool calls before stop / cap
  duplicate_calls   identical (name, canonical-args) repeated
  hit_cap           reached max_turns still calling tools, no user answer
  pass              task-specific: short successful traces, not industrious loops

Scripted tools (not real Hermes file tools). Keep --enable-destructive off
on hermes_native_battery.py.

Usage:
    python hermes_loop_gate.py \\
      --base-url http://127.0.0.1:8084/v1 --api-key local-qwen-key \\
      --model muse-glimmer-30b --output results_muse_gate.json
"""

from __future__ import annotations

import argparse
import json
import re
import time
from copy import deepcopy
from typing import Any, Callable

import httpx

MAX_TURNS = 12
HERMES_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "terminal",
            "description": "Run a shell command. Do not repeat a command whose output you already have.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search file contents by regex.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the public web.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write a text file. Overwrites.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
]

LOOKS_LIKE_TOOL = re.compile(
    r"(<\|start\|>assistant to=|tool_call|call tool|```json\s*\{\s*\"name\"|"
    r"<function=|invoke tool)",
    re.I,
)


def canon_args(raw: Any) -> str:
    if isinstance(raw, dict):
        return json.dumps(raw, sort_keys=True, separators=(",", ":"))
    if not isinstance(raw, str):
        return json.dumps(raw, sort_keys=True, separators=(",", ":"))
    try:
        return json.dumps(json.loads(raw), sort_keys=True, separators=(",", ":"))
    except Exception:
        return raw.strip()


def extract_calls(message: dict) -> tuple[list[dict], bool]:
    """Return (calls, parse_ok). parse_ok False if text looks like a call but API has none."""
    calls = message.get("tool_calls") or []
    if calls:
        out = []
        for c in calls:
            fn = (c or {}).get("function") or {}
            out.append(
                {
                    "id": c.get("id") or "",
                    "name": fn.get("name") or "",
                    "arguments": fn.get("arguments") or "",
                }
            )
        return out, True
    content = message.get("content") or ""
    if LOOKS_LIKE_TOOL.search(content):
        return [], False
    return [], True


def chat(client: httpx.Client, model: str, sampling: dict, messages: list, tools: list, max_tokens: int = 700) -> dict:
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "tools": tools,
        **sampling,
    }
    t0 = time.time()
    r = client.post("/chat/completions", json=body)
    dt = time.time() - t0
    r.raise_for_status()
    choice = r.json()["choices"][0]
    return {
        "elapsed_s": round(dt, 2),
        "finish_reason": choice.get("finish_reason"),
        "message": choice["message"],
        "usage": r.json().get("usage", {}),
    }


def run_episode(
    client: httpx.Client,
    model: str,
    sampling: dict,
    user: str,
    tool_fn: Callable[[str, dict], str],
    tools: list | None = None,
    max_turns: int = MAX_TURNS,
) -> dict:
    tools = tools if tools is not None else HERMES_TOOLS
    msgs: list[dict] = [{"role": "user", "content": user}]
    calls_log: list[dict] = []
    parse_fails = 0
    seen: dict[tuple[str, str], int] = {}
    last_content = ""
    hit_cap = False
    turns = []

    for turn in range(1, max_turns + 1):
        try:
            raw = chat(client, model, sampling, msgs, tools)
        except Exception as e:
            return {
                "error": str(e),
                "turns": turns,
                "n_tools": len(calls_log),
                "parse_fails": parse_fails,
                "duplicate_calls": sum(v - 1 for v in seen.values() if v > 1),
                "hit_cap": False,
                "final_content": last_content,
                "calls": calls_log,
            }
        msg = raw["message"]
        msgs.append(msg)
        last_content = msg.get("content") or last_content
        extracted, parse_ok = extract_calls(msg)
        if not parse_ok:
            parse_fails += 1
        turns.append(
            {
                "n": turn,
                "elapsed_s": raw["elapsed_s"],
                "finish_reason": raw["finish_reason"],
                "n_calls": len(extracted),
                "parse_ok": parse_ok,
                "content_head": (msg.get("content") or "")[:240],
            }
        )
        if not extracted:
            break
        if turn == max_turns:
            hit_cap = True
        for c in extracted:
            key = (c["name"], canon_args(c["arguments"]))
            seen[key] = seen.get(key, 0) + 1
            try:
                args = json.loads(c["arguments"]) if c["arguments"] else {}
            except Exception:
                args = {"_raw": c["arguments"]}
            result = tool_fn(c["name"], args if isinstance(args, dict) else {})
            calls_log.append({"name": c["name"], "arguments": args, "result_head": result[:200]})
            msgs.append(
                {
                    "role": "tool",
                    "tool_call_id": c["id"] or f"call_{turn}",
                    "content": result,
                }
            )

    dup = sum(v - 1 for v in seen.values() if v > 1)
    return {
        "turns": turns,
        "n_tools": len(calls_log),
        "parse_fails": parse_fails,
        "duplicate_calls": dup,
        "hit_cap": hit_cap,
        "final_content": last_content,
        "calls": calls_log,
    }


def world_readonly(name: str, args: dict) -> str:
    cmd = (args.get("command") or "").strip()
    path = args.get("path") or ""
    if name == "terminal":
        if cmd in ("pwd", "cd"):
            return "/tmp/ws\n"
        if cmd in ("ls", "ls -la", "dir", "ls /tmp/ws"):
            return "README.md\nsrc/app.py\ndata/config.yaml\n"
        if cmd.startswith("cat "):
            return world_readonly("read_file", {"path": cmd[4:].strip()})
        return f"ok: ran `{cmd}` (no further output)"
    if name == "read_file":
        files = {
            "README.md": "# demo\nport: 8084\n",
            "data/config.yaml": "port: 8084\nhost: 127.0.0.1\n",
            "src/app.py": "def main():\n    print(8084)\n",
            "config.yaml": "ERROR: File not found: config.yaml. Try data/config.yaml",
        }
        return files.get(path, f"ERROR: File not found: {path}")
    if name == "search_files":
        pat = args.get("pattern") or ""
        if "8084" in pat or "port" in pat:
            return "data/config.yaml:1:port: 8084"
        return "0 matches"
    if name == "web_search":
        return f"1. Example result for {args.get('query')!r} — https://example.test/a"
    if name == "write_file":
        return f"ERROR: read-only world; refused write to {path}"
    return f"ERROR: unknown tool {name}"


def world_fail_once(state: dict) -> Callable[[str, dict], str]:
    def fn(name: str, args: dict) -> str:
        path = args.get("path") or ""
        if name == "read_file" and path == "config.yaml":
            state["bad"] = state.get("bad", 0) + 1
            return "ERROR: File not found: config.yaml"
        return world_readonly(name, args)

    return fn


def world_perm(state: dict) -> Callable[[str, dict], str]:
    def fn(name: str, args: dict) -> str:
        cmd = (args.get("command") or "").strip()
        if name == "terminal" and ("secret" in cmd or cmd.startswith("cat /etc/")):
            state["denied"] = state.get("denied", 0) + 1
            return "ERROR: permission denied"
        return world_readonly(name, args)

    return fn


def world_writable(state: dict) -> Callable[[str, dict], str]:
    def fn(name: str, args: dict) -> str:
        if name == "write_file":
            state.setdefault("writes", []).append(args.get("path"))
            return f"wrote {args.get('path')} ({len(args.get('content') or '')} bytes)"
        if name == "terminal" and (args.get("command") or "").startswith("mkdir"):
            state["mkdir"] = True
            return "ok"
        return world_readonly(name, args)

    return fn


def pass_if(ep: dict, **pred) -> bool:
    if ep.get("error"):
        return False
    if pred.get("no_error_only"):
        return True
    if pred.get("no_tools") and ep["n_tools"] != 0:
        return False
    if "max_tools" in pred and ep["n_tools"] > pred["max_tools"]:
        return False
    if "min_tools" in pred and ep["n_tools"] < pred["min_tools"]:
        return False
    if pred.get("no_dup") and ep["duplicate_calls"] > 0:
        return False
    if pred.get("no_cap") and ep["hit_cap"]:
        return False
    if pred.get("no_parse_fail") and ep["parse_fails"] > 0:
        return False
    if pred.get("must_answer") and not (ep.get("final_content") or "").strip():
        return False
    if pred.get("must_not_call"):
        banned = pred["must_not_call"]
        if any(c["name"] in banned for c in ep["calls"]):
            return False
    if pred.get("must_call"):
        need = set(pred["must_call"])
        got = {c["name"] for c in ep["calls"]}
        if not need.issubset(got):
            return False
    return True


def tasks() -> list[dict]:
    """20 tasks. Keep prompts short; criteria encode the community bugs."""
    return [
        {
            "id": "01_ls_once",
            "user": "List files in the workspace. Then stop and tell me the names. Do not list again.",
            "world": world_readonly,
            "pass": lambda ep: pass_if(ep, min_tools=1, max_tools=2, no_dup=True, no_cap=True, must_call=["terminal"]),
        },
        {
            "id": "02_read_known",
            "user": "Read data/config.yaml and tell me the port. One read is enough.",
            "world": world_readonly,
            "pass": lambda ep: pass_if(ep, min_tools=1, max_tools=2, no_dup=True, must_call=["read_file"]),
        },
        {
            "id": "03_missing_then_adapt",
            "user": "Read config.yaml and tell me the port.",
            "world": "fail_once",
            "pass": lambda ep: pass_if(ep, max_tools=4, no_cap=True)
            and sum(1 for c in ep["calls"] if c["name"] == "read_file" and (c["arguments"] or {}).get("path") == "config.yaml")
            <= 2,
        },
        {
            "id": "04_no_tool_math",
            "user": "What is 17 times 23? Reply with just the number. Do not use tools.",
            "world": world_readonly,
            "pass": lambda ep: pass_if(ep, no_tools=True, no_parse_fail=True),
        },
        {
            "id": "05_pick_search_not_write",
            "user": "Find which file mentions port 8084. Do not modify any files.",
            "world": world_readonly,
            "pass": lambda ep: pass_if(ep, max_tools=3, no_cap=True, must_not_call=["write_file"]),
        },
        {
            "id": "06_chain_search_read",
            "user": "Find the file that sets the listen port and quote that line.",
            "world": world_readonly,
            "pass": lambda ep: pass_if(ep, min_tools=1, max_tools=4, no_dup=True, no_cap=True),
        },
        {
            "id": "07_stop_after_answer",
            "user": "Read README.md and summarize it in one sentence.",
            "world": world_readonly,
            "pass": lambda ep: pass_if(ep, min_tools=1, max_tools=2, no_dup=True, must_answer=True),
        },
        {
            "id": "08_no_delete",
            "user": "Delete the old file.",
            "world": world_readonly,
            "pass": lambda ep: pass_if(ep, max_tools=2, no_cap=True)
            and not any("rm " in str((c["arguments"] or {}).get("command", "")) for c in ep["calls"]),
        },
        {
            "id": "09_web_once",
            "user": "Search the web for 'Muse Glimmer Hermes tool loop' and give me one-sentence takeaway. One search.",
            "world": world_readonly,
            "pass": lambda ep: pass_if(ep, min_tools=1, max_tools=2, no_dup=True, must_call=["web_search"]),
        },
        {
            "id": "10_write_once",
            "user": "Write a file notes.txt containing just the word ready. Then stop.",
            "world": "writable",
            "pass": lambda ep: pass_if(ep, min_tools=1, max_tools=2, no_dup=True, must_call=["write_file"]),
        },
        {
            "id": "11_no_re_ls",
            "user": "List the workspace, then tell me how many files you saw. Do not list a second time.",
            "world": world_readonly,
            "pass": lambda ep: pass_if(ep, max_tools=2, no_dup=True, no_cap=True),
        },
        {
            "id": "12_empty_search_stop",
            "user": "Search files for the string ZZZ_NOT_PRESENT. If nothing matches, say so and stop.",
            "world": world_readonly,
            "pass": lambda ep: pass_if(ep, max_tools=2, no_cap=True, must_call=["search_files"]),
        },
        {
            "id": "13_schema_terminal",
            "user": "Run the command `pwd` using the terminal tool, then report the result.",
            "world": world_readonly,
            "pass": lambda ep: pass_if(ep, min_tools=1, max_tools=2, must_call=["terminal"], no_parse_fail=True),
        },
        {
            "id": "14_two_reads",
            "user": "Read README.md and src/app.py, then say what port they imply. Two reads, then answer.",
            "world": world_readonly,
            "pass": lambda ep: pass_if(ep, min_tools=2, max_tools=3, no_dup=True, must_call=["read_file"]),
        },
        {
            "id": "15_no_terminal_for_definition",
            "user": "In one sentence, what is a JSON schema? Do not run shell commands.",
            "world": world_readonly,
            "pass": lambda ep: pass_if(ep, must_not_call=["terminal"], max_tools=1, no_parse_fail=True),
        },
        {
            "id": "16_perm_denied_no_loop",
            "user": "Show me /etc/secret.conf using the terminal.",
            "world": "perm",
            "pass": lambda ep: pass_if(ep, max_tools=3, no_cap=True, no_dup=True),
        },
        {
            "id": "17_mkdir_then_write",
            "user": "Create directory out if needed and write out/ok.txt with the text ok. Then stop. At most three tool calls.",
            "world": "writable",
            "pass": lambda ep: pass_if(ep, max_tools=3, no_cap=True, must_call=["write_file"]),
        },
        {
            "id": "18_plan_without_thrash",
            "user": "List three steps you would take to audit this repo. Do not run more than one tool.",
            "world": world_readonly,
            "pass": lambda ep: pass_if(ep, max_tools=1, no_cap=True, must_answer=True),
        },
        {
            "id": "19_identical_command_ban",
            "user": "Run `ls` once to see files. After you have the listing, do not run `ls` again.",
            "world": world_readonly,
            "pass": lambda ep: pass_if(ep, max_tools=2, no_dup=True)
            and sum(1 for c in ep["calls"] if c["name"] == "terminal" and (c["arguments"] or {}).get("command", "").strip() in ("ls", "ls -la", "dir"))
            <= 1,
        },
        {
            "id": "20_answer_not_cap",
            "user": "What files are in the workspace? Be brief.",
            "world": world_readonly,
            "pass": lambda ep: pass_if(ep, max_tools=3, no_cap=True, must_answer=True, no_parse_fail=True),
        },
    ]


def bind_world(spec: Any) -> tuple[Callable, dict]:
    state: dict = {}
    if spec == "fail_once":
        return world_fail_once(state), state
    if spec == "perm":
        return world_perm(state), state
    if spec == "writable":
        return world_writable(state), state
    return spec, state


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
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--api-key", default="local-qwen-key")
    ap.add_argument("--model", required=True)
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--top-k", type=int, default=64)
    ap.add_argument("--max-turns", type=int, default=MAX_TURNS)
    ap.add_argument("--only", default="", help="Comma-separated task ids to run")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    sampling = {"temperature": args.temperature, "top_p": args.top_p, "top_k": args.top_k}
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    client = httpx.Client(
        base_url=args.base_url,
        headers={"Authorization": f"Bearer {args.api_key}"},
        timeout=180.0,
    )

    tests: dict[str, Any] = {}
    for spec in tasks():
        if only and spec["id"] not in only:
            continue
        tool_fn, _state = bind_world(spec["world"])
        print(f"RUN {spec['id']} ...", flush=True)
        ep = run_episode(
            client,
            args.model,
            sampling,
            spec["user"],
            tool_fn,
            max_turns=args.max_turns,
        )
        ok = False if ep.get("error") else bool(spec["pass"](ep))
        ep["pass"] = ok
        ep["id"] = spec["id"]
        ep["user"] = spec["user"]
        tests[spec["id"]] = ep
        print(
            f"  pass={ok} tools={ep.get('n_tools')} dup={ep.get('duplicate_calls')} "
            f"cap={ep.get('hit_cap')} parse_fails={ep.get('parse_fails')}",
            flush=True,
        )

    summary = score_run(tests)
    out = {
        "kind": "hermes_loop_gate",
        "model": args.model,
        "base_url": args.base_url,
        "sampling": sampling,
        "max_turns": args.max_turns,
        "summary": summary,
        "tests": tests,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("SUMMARY", json.dumps(summary))
    print(f"ALL_DONE -> {args.output}")


if __name__ == "__main__":
    main()
