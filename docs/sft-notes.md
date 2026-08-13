# SFT notes (Muse + Hermes loops)

Do **not** treat a general multi-teacher distill as the main mix for a
community Muse-Hermes release.

| Mix | Role |
|---|---|
| Short traces (1–3 tools, then answer) | primary |
| Stop/recovery (“you already listed, answer”) | primary |
| Dead tool: say unconfigured, don’t retry 8× | primary |
| `r0b0tlab/.../data/sft_tools/*.parquet` | ≤10–20% aux only |
| Full `sft_balanced` / named HF configs | no |

Student: Muse Glimmer QLoRA (`FastModel`, 24GB, vision off, `offload_embedding=True`).
Loss from `<|start|>assistant`. Keep some `reasoning_content` or `to=self` dies.

**Paired Muse UD-Q4_K_XL (DFlash off, 32k):**

| Layer | Score | Read |
|---|---|---|
| Simulated loop gate | 7/20, mean 5.7, **7 HIT_CAP** | empty answers on open-ended tools |
| Native Hermes CLI | 4/5, mean **2.8**, **0 HIT_CAP** | list/file/math/plan stop; web 8 calls because Firecrawl unset |

SFT = **stop after 1–2 tools** and **don’t thrash a dead tool**, not “learn more tools.”
Native file cwd is often HERMES_HOME — don’t use those traces as labels.

Load r0b0tlab with explicit `data/sft_tools/*.parquet`, not `load_dataset(..., "sft_tools")`.

Muse is Apache-2.0; that distill is `license: other`. Seal both
`hermes_loop_gate.py` and `hermes_native_battery.py` before/after SFT.
