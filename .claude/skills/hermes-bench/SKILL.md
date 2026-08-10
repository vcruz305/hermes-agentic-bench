---
name: hermes-bench
description: Set up and run the hermes-agentic-bench agentic test battery (simulated OpenAI-endpoint battery and/or real Hermes CLI battery) against one or more local models, then generate a comparison report.
user-invocable: true
---

# hermes-bench

Runs this repo's test batteries end-to-end and hands back a comparison report, without
the user having to remember flags or file names.

## Trigger

When the user runs `/hermes-bench`, or asks to benchmark/compare model(s) against this
repo's agentic tests.

## Workflow

1. **Confirm location.** Check for `README.md` and `simulated_battery.py` in the current
   directory. If missing, ask whether to clone
   `https://github.com/vcruz305/hermes-agentic-bench` here or run the skill somewhere else.
2. **Install dependencies.** `pip install -r requirements.txt`.
3. **Read `README.md`**, especially "Known limitations." The file-toolset tests are not
   reliably sandboxed to a scratch directory — keep the destructive-request test
   (`--enable-destructive`) off unless the user explicitly asks for it in this
   conversation. Don't infer consent from a prior run.
4. **Collect targets.** For each model the user wants tested, ask:
   - a short label (used to name result files)
   - which battery: simulated, real Hermes CLI, or both
   - simulated: OpenAI-compatible `--base-url`, `--api-key`, `--model`
   - Hermes: `--provider` and `--model` exactly as registered in the user's Hermes
     `config.yaml` — ask rather than guess, or read the file if the user points to it
5. **Run the batteries**, one model at a time:
   - `python simulated_battery.py --base-url <url> --api-key <key> --model <model> --output results_<label>.json`
   - `python hermes_native_battery.py --provider <provider> --model <model> --output results_<label>_hermes.json`
   - Hermes-native runs can legitimately take minutes per test (900-1800s stream
     timeouts are expected for local providers) — don't treat a slow-but-running
     process as hung.
6. **Generate the report** once every requested model has finished:
   `python generate_report.py results_*.json --output comparison.md`
7. **Report back.** Show `comparison.md` and call out anything that looks off before the
   user reads the raw numbers — a test marked "not run", a large elapsed-time outlier
   versus the other models, a non-zero return code.

## Failure handling

If a run fails or times out, report it and ask whether to retry with a longer
`--timeout` rather than silently skipping the test or fabricating a result.
