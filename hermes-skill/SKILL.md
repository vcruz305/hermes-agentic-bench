---
name: hermes-bench
description: Run hermes-agentic-bench's agentic tool-use test battery against a model and report results.
version: 0.1.0
author: vcruz305, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [benchmarking, agentic-testing, model-comparison, local-models]
---

# hermes-bench

Clones and drives [hermes-agentic-bench](https://github.com/vcruz305/hermes-agentic-bench):
a small test battery that probes tool-calling, error recovery, and task planning against
a model, either through a raw OpenAI-compatible endpoint or through this same Hermes CLI.
Produces a Markdown comparison report across however many models get tested. Not a
leaderboard — numbers only mean something for the hardware/model combo they were measured on.

## When to use

- User asks to benchmark, compare, or agentic-test one or more local/provider models
- User references "hermes-agentic-bench," "the Hermes bench," or asks how reliable a
  model is at tool use, not just how smart it is
- Don't use for: static capability leaderboards (MMLU, etc.) — this only measures
  agentic tool-use behavior

## Prerequisites

- `git` and Python 3.9+ on PATH
- Simulated battery: an OpenAI-compatible chat completions endpoint already running
  (e.g. `llama-server`), plus its base URL, API key, and served model name
- Native battery: the model already registered as a `provider` in this Hermes install's
  `config.yaml` — check with `read_file` on the relevant config rather than assuming a
  provider name

## How to Run

Everything below goes through `terminal`, e.g.
`terminal(command="pip install -r requirements.txt", timeout=120)`.

## Quick Reference

```
git clone https://github.com/vcruz305/hermes-agentic-bench && cd hermes-agentic-bench
pip install -r requirements.txt
python simulated_battery.py --base-url <url> --api-key <key> --model <model> --output results_<label>.json
python hermes_native_battery.py --provider <provider> --model <model> --output results_<label>_hermes.json
python generate_report.py results_*.json --output comparison.md
```

## Procedure

1. **Locate or clone the repo.** `search_files(pattern="simulated_battery.py", target="files")`
   from the current directory; if absent, `terminal(command="git clone https://github.com/vcruz305/hermes-agentic-bench", timeout=60)`
   and operate from inside it afterward.
2. **Install dependencies.** `terminal(command="pip install -r requirements.txt", timeout=120)`.
3. **Read the repo's README** (`read_file(path="README.md")`), especially "Known
   limitations" — the file-toolset tests in `hermes_native_battery.py` are not reliably
   sandboxed to a scratch directory. Keep `--enable-destructive` off unless the user
   explicitly asks for it in this conversation; don't infer consent from an earlier run.
4. **Collect per-model targets from the user**, one round per model:
   - a short label for naming result files
   - simulated battery, native battery, or both
   - simulated: `--base-url`, `--api-key`, `--model`
   - native: `--provider` and `--model` exactly as registered in `config.yaml` — ask,
     don't guess
5. **Run each requested battery** via `terminal`, one model at a time (see Quick
   Reference for the exact flags). Native runs commonly take several minutes per test —
   Hermes itself allows 900-1800s stream timeouts for local providers, so a
   long-running-but-still-running process is not a failure.
6. **Generate the comparison** once every requested model has a results file:
   `terminal(command="python generate_report.py results_*.json --output comparison.md", timeout=30)`.
7. **Report back.** `read_file(path="comparison.md")` and summarize it, calling out
   anything that looks off before quoting numbers at face value — a test marked "not
   run," a run far slower than its peers, a non-zero return code.

## Pitfalls

- Simulated and native results **do not always agree** — that gap is the reason both
  scripts exist, not a bug in one of them.
- Sampling temperature affects run-to-run timing more than most people expect; treat a
  single run's timing as noise, not a verdict.
- Never pass `--enable-destructive` speculatively "to be thorough" — it's opt-in for a
  documented reason (see Prerequisites and the repo README).

## Verification

`comparison.md` exists and lists every requested (model, test) pair with a real elapsed
time or an explicit failure reason — never a fabricated number for a run that failed or
was skipped.
