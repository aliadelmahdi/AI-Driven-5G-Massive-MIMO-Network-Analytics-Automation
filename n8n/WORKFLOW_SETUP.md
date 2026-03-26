# n8n Workflow Setup

## What this workflow does

The workflow supports three triggers:

- `Manual Trigger` for one-click testing inside n8n
- `Schedule Trigger` to run every 6 hours
- `Webhook Trigger` at `POST /webhook/telecom-ai-run`

For every trigger, the first runtime step is now:

1. fetch measurement status from MySQL through the local API
2. run the analytics pipeline backed by MySQL
3. enrich the top incidents with local Ollama `qwen3:8b`
4. save outputs to `output/`

This makes the workflow visibly database-first instead of synthetic-data-first.

## Import steps

1. Make sure MySQL is running.
2. Run the analytics API locally on the host:

```powershell
.\.venv\Scripts\python.exe main.py serve --host 0.0.0.0 --port 8010
```

3. Confirm the API is healthy:

```powershell
curl http://127.0.0.1:8010/health
```

4. Confirm the DB preview endpoint responds:

```powershell
curl http://127.0.0.1:8010/data-source-status
```

5. Confirm Ollama is available on the host:

```powershell
ollama run qwen3:8b
```

6. Import `n8n/telecom_ai_workflow.json` into n8n.
7. Activate the workflow if you want scheduled runs.

## URLs expected by the workflow

- DB status check:
  - `http://host.docker.internal:8010/data-source-status`
- Analytics run:
  - `http://host.docker.internal:8010/analyze-and-enrich`
- Webhook trigger path:
  - `/webhook/telecom-ai-run`

## Files written by the API

- `output/joined_analysis.csv`
- `output/incidents_summary.csv`
- `output/llm_input.json`
- `output/llm_enriched_incidents.json`
- `output/top_incidents_report.md`

## Docker mapping notes

- The `n8n` container calls the host API through `host.docker.internal`.
- The analytics API reads source data from MySQL and writes outputs to the project `output/` directory.
- The dashboard UI lives at `http://127.0.0.1:8010/dashboard-data`.
