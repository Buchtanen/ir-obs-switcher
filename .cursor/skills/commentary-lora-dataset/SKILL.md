---
name: commentary-lora-dataset
description: >-
  Map of commentary LoRA / SFT / DPO / ChatML sources, overlay llm_polish
  pairs, prompt families (SKELETON, ANCHOR, facts/3, DATA), and the private
  ir-commentary-lora repo. Use when the user mentions LoRA, fine-tune, SFT,
  DPO, ChatML, polish pairs, commentary dataset, eval cases, clean_tapes,
  ir-commentary-lora, or where to find test data for Qwen / Ollama polish.
---

# Commentary LoRA / test-data map

Read `docs/commentary_lora_dataset.md` first. Manipulation contract (keep/drop,
gold, CLI) is `../ir-commentary-lora/DATASETS.md` (private clone next to irswitch).

## Quick lookup

1. **Raw pairs:** `recordings/overlay-*.jsonl` → `type: llm_polish`.
2. **Eval (propositions, not gold sentences):** `tests/fixtures/commentary/commentary_eval_cases.json` (2026-09-01 ANCHOR/skeleton tapes).
3. **ChatML:** private `ir-commentary-lora` `datasets/facts3/sft|dpo/` after `python scripts/clean_tapes.py`.
4. **Live prompt:** `src/irswitch/commentary/polish.py` — user is only `DATA:` (role keys, no STYLE/example).

HUD / VOD / overlayMode bugs: skill `overlay-tape-triage`, not this file.

## Rules

- Do not mix prompt families in one SFT split.
- `outcome=ok` is not gold; invented numbers → canonical.
- No `llm_polish` on an INFO tape (pre-#219) means DEBUG was off, not a dead model.
- Default cleaner `--family facts3` skips live `DATA:` rows (classified `other`). Use `--family all` until the detector is updated.
- Never copy tapes or adapters into public irswitch.
