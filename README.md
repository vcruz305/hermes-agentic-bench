# hermes-agentic-bench

Small, honest agentic test batteries for local models — written because there's no
published benchmark for models plugged into [Hermes Agent](https://hermes-agent.nousresearch.com),
and static leaderboard numbers don't tell you whether a model can actually chain tools,
recover from a failed call, or stay on task when something it needs isn't configured.

Two scripts, two levels of realism:

- **`simulated_battery.py`** — talks directly to an OpenAI-compatible endpoint (e.g. a
  local `llama-server`) with hand-scripted tool responses. Fast, cheap, good for a first
  read on tool-calling and reasoning-budget behavior.
- **`hermes_native_battery.py`** — drives the actual `hermes chat -q` CLI with real
  toolsets and real tool failures. Slower and messier, but it's what your model will
  actually do in production. **The two batteries do not always agree** — that gap is
  itself informative (see "Known limitations" below).

`generate_report.py` turns one or more result JSON files into a Markdown comparison table.

This came out of an actual comparison ([Muse Glimmer 30B vs. Bonsai 27B](https://claude.ai/code/artifact/af013b83-dc66-4865-a6eb-ad7a2918cddf))
where the simulated battery said one thing and the real Hermes sessions said another —
that discrepancy is the reason this repo has two scripts instead of one.

## Prerequisites

- Python 3.9+
- For `simulated_battery.py`: any OpenAI-compatible chat completions endpoint
  (llama.cpp's `llama-server`, vLLM, etc.) — `pip install -r requirements.txt`
- For `hermes_native_battery.py`: [Hermes Agent](https://hermes-agent.nousresearch.com)
  installed, with your model(s) registered as a `provider` in `config.yaml`

## Quick start

```bash
pip install -r requirements.txt

# Simulated battery against a raw endpoint
python simulated_battery.py \
  --base-url http://127.0.0.1:8080/v1 --api-key local-key \
  --model my-model --temperature 0.6 --top-p 0.95 --top-k 20 \
  --output results_mymodel.json

# Real Hermes CLI battery
python hermes_native_battery.py \
  --provider my-model-provider --model my-model \
  --output results_mymodel_hermes.json

# Compare two runs
python generate_report.py results_bonsai.json results_glimmer.json --output comparison.md
```

## What's tested

| # | Scenario | What it probes |
|---|---|---|
| 1 | Multi-step tool chaining | Can the model use one tool's result as input to a second tool call? |
| 2 | Tool selection under distractors | Does it call the *right* tool (or no tool) instead of the first plausible one? |
| 3 | Error recovery | When a tool call fails, does it adapt/retry, or hallucinate a result? |
| 4 | Structured schema fill | Nested JSON schema (arrays, ISO dates) filled correctly? |
| 5 | Reasoning under a token budget | Does it produce a final answer, or burn the whole budget thinking? |
| 6 | Ambiguous destructive request | Does it ask before acting on "delete the old file" with no path given? |

`hermes_native_battery.py` runs a subset of these (1, 2, 3, and a real task-planning
scenario) by default, using Hermes' actual toolset instead of scripted ones — see the
next section for why test 4 (destructive request) is opt-in there.

## Known limitations (read this before running `--enable-destructive`)

**Hermes' file toolset does not reliably scope to the directory you'd expect.**
We tried four different ways to sandbox `hermes_native_battery.py`'s file-toolset tests
against disposable files instead of real ones:

1. The invoking shell's working directory
2. `subprocess.run(..., cwd=...)`
3. The `TERMINAL_CWD` environment variable
4. `hermes project create <name> <path> --use`

None of them redirected where the file tools actually operate — confirmed by reading
the `hermes-agent` source directly (`tools/file_tools.py`, `tools/environments/`), where
cwd resolution goes through in-process session state (`get_session_cwd` /
`resolve_task_overrides`) that isn't reachable from outside the running session. In
practice, this means file-toolset tests can end up looking at your **real** Hermes home
directory's files, no matter what `--sandbox-dir` you pass.

For that reason, `hermes_native_battery.py`'s destructive-request test is **off by
default** and requires `--enable-destructive` plus an explicit acknowledgment in the
script's warning output. In our own testing across several runs, nothing was ever
actually deleted — both models we tested either asked for clarification or never reached
tool-call approval — but that's an observation about two specific models' behavior, not
a safety guarantee about Hermes' sandboxing. If you find an actual working override,
please open an issue or PR.

**Timeouts**: Hermes itself sets a 900-1800s stream-read timeout for local providers,
expecting them to be slow. Don't set `--timeout` below ~120s and conclude a model is
"hung" — in our testing, a run that looked dead at 60s sometimes completed correctly at
2-3 minutes. `hermes_native_battery.py` defaults to 300s for exactly this reason.

**Sampling matters more than you'd think**: run-to-run variance on the same test can be
large for models sampled at higher temperature (we saw 41s to 168s for the identical
task on the same model, same hardware). Run more than once before concluding a timing
difference is real.

## License

MIT — see [LICENSE](LICENSE).
