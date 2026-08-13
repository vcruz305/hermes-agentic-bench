# SFT notes (Muse + Hermes loops)

Do **not** treat a general multi-teacher distill as the main mix for a
community Muse-Hermes release.

| Mix | Role |
|---|---|
| Hermes-native short traces (5–15 tools, then answer) | primary |
| Loop/recovery (“you already have `ls`, stop”) | primary |
| Malformed → corrected OpenAI `tool_calls` | primary |
| `r0b0tlab/.../data/sft_tools/*.parquet` | ≤10–20% aux only |
| Full `sft_balanced` / named HF configs | no — configs currently dump the same ~890k mix |

Student: Muse Glimmer QLoRA (`FastModel`, 24GB, vision off, `offload_embedding=True`).
Loss from `<|start|>assistant` so tool turns train. Keep some `reasoning_content`
or `to=self` dies.

Load the r0b0tlab tool slice with explicit parquet paths, not
`load_dataset(repo, "sft_tools")`.

License: Muse is Apache-2.0; that distill is `license: other`. Don’t ship it as
the public mix without reading `LICENSE` / `PROVENANCE.md`.

Seal this repo’s `hermes_loop_gate.py` **before** and **after** SFT. No upload
until pass rate and mean-tools move the right way.
