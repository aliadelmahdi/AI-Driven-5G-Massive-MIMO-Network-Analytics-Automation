ifeq ($(OS),Windows_NT)
VENV_BIN := .venv/Scripts
PYTHON := $(VENV_BIN)/python.exe
PIP := $(PYTHON) -m pip
else
VENV_BIN := .venv/bin
PYTHON := $(VENV_BIN)/python
PIP := $(PYTHON) -m pip
endif

HOST ?= 0.0.0.0
PORT ?= 8010
TOP_N ?= 25
N8N_PORT ?= 5678

.PHONY: install run export-dashboard clean

install:
	python -m venv .venv
	$(PIP) install -r requirements.txt

run:
	@echo "[1/4] Loading existing CSV datasets into MySQL"
	@echo "      This step reads data/ue_measurements.csv and data/beam_kpis.csv and loads them into MySQL."
	$(PYTHON) main.py load-db --force-reload
	@echo ""
	@echo "[2/4] Running telecom analysis pipeline"
	@echo "      This step shows live status and ETA while MySQL reads, rules, and Ollama enrichment run."
	$(PYTHON) main.py analyze --enrich-with-llm --top-n-incidents $(TOP_N)
	@echo ""
	@echo "[3/4] Analysis finished"
	@echo "      Report: output/top_incidents_report.md"
	@echo "      Incidents CSV: output/incidents_summary.csv"
	@echo "      Enriched JSON: output/llm_enriched_incidents.json"
	@echo ""
	@echo "[4/4] Starting local API service"
	@echo "      Next: keep this terminal open, then open one of these URLs in your browser:"
	@echo "      Telecom Analytics API: http://127.0.0.1:$(PORT)"
	@echo "      API health: http://127.0.0.1:$(PORT)/health"
	@echo "      Dashboard UI: http://127.0.0.1:$(PORT)/dashboard-data"
	@echo "      API docs: http://127.0.0.1:$(PORT)/docs"
	@echo "      n8n UI: http://127.0.0.1:$(N8N_PORT)"
	@echo "      n8n webhook: http://127.0.0.1:$(N8N_PORT)/webhook/telecom-ai-run"
	@echo ""
	@echo "      If you only want analysis files and do not want to keep the server running, use:"
	@echo "      $(PYTHON) main.py analyze --enrich-with-llm --top-n-incidents $(TOP_N)"
	$(PYTHON) main.py serve --host $(HOST) --port $(PORT)

export-dashboard:
	@echo "[1/1] Exporting a static dashboard snapshot for GitHub Pages"
	@echo "      This creates docs/index.html and docs/dashboard-data.json so others can open the dashboard from a GitHub link."
	$(PYTHON) main.py export-dashboard --output-dir docs --limit 200

clean:
	$(PYTHON) -c "from pathlib import Path; [p.unlink() for folder in ('data','output') for p in Path(folder).glob('*') if p.is_file()]"
