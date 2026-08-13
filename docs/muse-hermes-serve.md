# Serving Muse Glimmer for Hermes (community recipe)

The stock `C:\models\muse-glimmer-30b-serve.cmd` enables **DFlash**. That is a
speed win on chat. Community loop reports (50–150 `terminal` calls, missed
stops) often include DFlash. For this gate and for Hermes tool work:

1. **DFlash off** for tool-heavy runs (no `-md`, no `--spec-type draft-dflash`).
2. If you use Unsloth Studio in front of Hermes: **`--disable-tools`** so Unsloth
   does not swallow Hermes’s tools.
3. Keep context modest on 24GB (32k–65k) until the gate is green; 131k + a loop
   is how people blow the Hermes consecutive-tool cap.
4. Sampling for think-on Muse: `temp 0.6`, `top_p 0.95`, `top_k 64`.
5. Server must expose OpenAI `tools` / `tool_calls`. An ATEM-only dump that
   never becomes `message.tool_calls` is a **parse fail** on this gate.

Example (Windows, same binary family as the local Muse script, **no drafter**):

```bat
llama-server.exe ^
  -m C:/models/gguf/muse-glimmer-30b/Muse-Glimmer-30B-UD-Q4_K_XL.gguf ^
  -a muse-glimmer-30b --host 127.0.0.1 --port 8084 --api-key local-qwen-key ^
  -ngl 99 -fa on -c 32768 -np 1 -cb -t 9 ^
  --jinja --temp 0.6 --top-p 0.95 --top-k 64
```

Then:

```bash
python hermes_loop_gate.py \
  --base-url http://127.0.0.1:8084/v1 --api-key local-qwen-key \
  --model muse-glimmer-30b --output results_muse_gate.json
```

A release that helps Hermes users should move **pass rate up**, **mean tools
down** (toward 1–3 on these tasks, not 12/HIT_CAP), and **parse-fail / dup
tasks toward 0**. Loss on a GLM `run_python` distill is not that signal.
