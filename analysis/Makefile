# One-command, re-runnable evaluation harness (Speedrun grade 12%).
# Usage: `make eval` (or `make -C analysis eval`). Temporal splits everywhere.
PY ?= .venv/bin/python
# The demo/dashboard talk to the live engine, so they use Anki's built Python.
ANKI_PY ?= ../anki/out/pyenv/bin/python

.PHONY: eval clean venv simulate demo dashboard outline ai bench crash bridge bridge-llm

eval: simulate
	$(PY) leakage_check.py
	$(PY) irt_fit.py
	$(PY) calibration.py
	$(PY) perf_eval.py
	$(PY) score_map.py
	$(PY) paraphrase_real.py
	$(PY) ablation.py
	$(PY) graph_eval.py
	$(PY) report.py
	@echo "=== eval complete: see analysis/RESULTS.md and data/eval/*.json ==="

simulate:
	$(PY) simulate.py

venv:
	uv venv .venv && .venv/bin/python -m ensurepip >/dev/null 2>&1 || true
	uv pip install --python .venv/bin/python numpy

# Build a real tagged Anki collection and run the end-to-end readiness dashboard
# (memory pulled live from the Rust mastery query).
demo:
	$(ANKI_PY) make_demo_collection.py
	$(ANKI_PY) dashboard.py

dashboard:
	$(ANKI_PY) dashboard.py

# Local-AI card generation + grading (needs Ollama running: `ollama serve`, model llama3).
# Generates grounded cards, grades vs baselines + injection defense, exports passing cards.
ai:
	$(PY) ai/ai_eval.py
	$(ANKI_PY) ai/ai_export.py
	$(PY) report.py
	@echo "=== ai complete: see data/eval/ai_eval.json and data/ai/MCAT_AI_Generated.apkg ==="

# One-command benchmark on the shared 50,000-card deck (Speedrun 7h + sec.10).
bench:
	$(ANKI_PY) make_bench.py 50000

# Crash/durability test: kill mid-review 20x, prove zero corruption (Speedrun 7g).
crash:
	$(ANKI_PY) crash_test.py

# Memory->Performance bridge on real matched items. `bridge-llm` collects a real
# local-LLM respondent (needs Ollama); `make bridge` analyzes all collected
# responses. Add human respondents with: python perf_bridge.py quiz <name>
bridge-llm:
	$(PY) perf_bridge.py run_llm 5
bridge:
	$(PY) perf_bridge.py analyze

# Regenerate the desktop (Svelte) + Android (Kotlin) OUTLINE maps from the JSON
# source of truth so the three surfaces never drift. `outline-check` fails CI if stale.
outline:
	$(ANKI_PY) gen_outline_maps.py

outline-check:
	$(ANKI_PY) gen_outline_maps.py --check

clean:
	rm -rf ../data/sim ../data/eval ../data/fitted_params.json ../data/demo RESULTS.md
