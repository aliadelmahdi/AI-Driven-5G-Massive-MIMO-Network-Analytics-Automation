# Telecom Analytics Project

For a shorter version of this guide, see [README.summary.md](README.summary.md).

This project is a simple telecom analytics system built with Python, MySQL, FastAPI, n8n, and a local Ollama model.

It reads UE and beam measurement data, detects network problems such as congestion, interference, and coverage issues, and shows the results in a local dashboard and API.

## What This Project Does

- It processes telecom KPI data such as `RSRP` and `SINR` from a local MySQL database by using SQL queries.
- It detects common network problems like congestion, interference, coverage issues, and reliability degradation.
- It generates structured outputs and short natural-language recommendations for network optimization.
- It connects the analytics flow with `n8n` so the full process can be triggered as an automated pipeline.
- It uses a local Ollama LLM to enrich the top incidents with readable insights.

## Project Showcase

This project focuses on two main parts:

1. Built an AI-powered telecom analytics system using Python, processing UE measurement reports such as `RSRP` and `SINR` from a local MySQL database through SQL queries, so the system can retrieve data and detect congestion, interference, and coverage issues.
2. Developed an end-to-end automation pipeline that connects `n8n` with a local Ollama LLM, generating structured insights and natural-language recommendations to support data-driven network optimization.

## Important Note About The Data

The data in this repository is not real operator data.

It is sample data used only to try and test the `n8n` approach, the analytics flow, and the local dashboard. In a real deployment, this sample data should be replaced with real network data provided by telecom operators.

## Main Flow

The project follows this flow:

1. Read telecom CSV files from the `data` folder.
2. Load the data into MySQL tables.
3. Query the data from MySQL with SQL files.
4. Build features and detect incidents.
5. Enrich top incidents with the local Ollama model.
6. Save reports and serve the results through FastAPI and the dashboard.
7. Allow `n8n` to trigger the same process as an automated workflow.

## Project Structure

The main folders in this project are:

- `data/` contains the sample telecom CSV files used for testing.
- `sql/` contains the MySQL schema file and the SQL queries used to read the telecom data.
- `src/` contains the Python source code for data loading, analysis, API endpoints, dashboard logic, and LLM integration.
- `n8n/` contains the workflow JSON file and setup notes for the automation pipeline.
- `output/` contains the generated reports, CSV summaries, and LLM enrichment files.
- `.venv/` is the local Python virtual environment created for this project.

## Main Files

- [main.py](main.py) is the main entry point.
- [src/api.py](src/api.py) serves the API and dashboard.
- [sql/01_create_schema.sql](sql/01_create_schema.sql) creates the MySQL tables.
- [sql/10_fetch_ue_measurements.sql](sql/10_fetch_ue_measurements.sql) reads UE data from MySQL.
- [sql/11_fetch_beam_kpis.sql](sql/11_fetch_beam_kpis.sql) reads beam KPI data from MySQL.
- [n8n/telecom_ai_workflow.json](n8n/telecom_ai_workflow.json) contains the workflow for automation.

## Requirements

Before running the project, install these tools:

- Python 3.11 or newer
- Docker Desktop or Docker Engine
- GNU Make or a compatible `make` command
- Optional but recommended: Ollama, if you want LLM enrichment

You also need the required Docker images and containers for the local services used by this project:

- MySQL image: `mysql:8.4`
- n8n image: `n8nio/n8n:latest`

Create and start the MySQL container:

```powershell
docker pull mysql:8.4
docker run --name mysql -e MYSQL_ROOT_PASSWORD=root -e MYSQL_DATABASE=telecom_analytics -p 3306:3306 -d mysql:8.4
```

Create and start the n8n container:

```powershell
docker pull n8nio/n8n:latest
docker run --name n8n -p 5678:5678 -d n8nio/n8n:latest
```

If the containers already exist, start them with:

```powershell
docker start mysql
docker start n8n
```

## Setup

Create the virtual environment and install the dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Start MySQL if it is not running:

```powershell
docker start mysql
```

If you do not already have a `mysql` container, create one:

```powershell
docker run --name mysql -e MYSQL_ROOT_PASSWORD=root -e MYSQL_DATABASE=telecom_analytics -p 3306:3306 -d mysql:8.4
```

Start n8n if it is not running:

```powershell
docker start n8n
```

If you do not already have an `n8n` container, create one:

```powershell
docker run --name n8n -p 5678:5678 -d n8nio/n8n:latest
```

Optional environment values:

```powershell
$env:MYSQL_HOST="127.0.0.1"
$env:MYSQL_PORT="3306"
$env:MYSQL_USER="root"
$env:MYSQL_PASSWORD="root"
$env:MYSQL_DATABASE="telecom_analytics"
```

## Best Way To Run

The main command for this project is:

```powershell
make run
```

This command does four things:

1. Loads the CSV data into MySQL.
2. Runs the telecom analysis pipeline.
3. Saves the output files.
4. Starts the local API and dashboard.

## Expected `make run` Output

You will see output like this:

```text
make run
"[1/4] Loading existing CSV datasets into MySQL"
"      This step reads data/ue_measurements.csv and data/beam_kpis.csv and loads them into MySQL."
.venv/Scripts/python.exe main.py load-db --force-reload
[status] Loading existing telecom CSVs into MySQL | ETA 10-30s
[status] Reading existing CSV datasets | ETA 2-8s
[status] Refreshing MySQL tables from CSV files | ETA 5-20s
[status] Loading UE measurements into MySQL | ETA 5-20s
[status] Loading beam KPIs into MySQL | ETA 5-15s
Loaded UE rows: 150000
Loaded beam KPI rows: 96768
[done] load-db finished in 40.4s
""
"[2/4] Running telecom analysis pipeline"
"      This step shows live status and ETA while MySQL reads, rules, and Ollama enrichment run."
.venv/Scripts/python.exe main.py analyze --enrich-with-llm --top-n-incidents 25
[status] Starting telecom analysis pipeline | ETA 20s to 5 min
[status] Preparing MySQL-backed datasets | ETA 8-30s
[status] Reading existing CSV datasets | ETA 2-8s
[status] Fetching UE measurements from MySQL | ETA 2-8s
[status] Fetching beam KPI windows from MySQL | ETA 2-8s
[status] Loaded data: UE rows=150,000, beam rows=96,768 | ETA 5-10s
[status] Aggregating UE data into 5-minute windows | ETA 5-15s
[status] Joining beam KPIs with UE aggregates | ETA 2-6s
[status] Engineering telecom features | ETA 2-5s
[status] Detecting anomalies | ETA 2-5s
[status] Classifying incidents and severity | ETA 2-5s
[status] Selecting top 25 incidents for LLM enrichment | ETA 1-3s
[status] Running Ollama enrichment for 25 incidents | ETA 25-75 min
...
[status] Ollama incident 18/25 | ETA 7-21 min
[status] Ollama incident 19/25 | ETA 6-18 min
[status] Ollama incident 20/25 | ETA 5-15 min
[status] Ollama incident 21/25 | ETA 4-12 min
[status] Ollama incident 22/25 | ETA 3-9 min
[status] Ollama incident 23/25 | ETA 2-6 min
[status] Ollama incident 24/25 | ETA 1-3 min
[status] Ollama incident 25/25 | ETA 0-1 min
[status] Building markdown report | ETA 1-3s
[status] Analysis complete in 183.6s | ETA 0s
Joined rows: 96768
Incidents rows: 96768
LLM used: True
[done] analyze finished in 183.7s
""
"[3/4] Analysis finished"
"      Report: output/top_incidents_report.md"
"      Incidents CSV: output/incidents_summary.csv"
"      Enriched JSON: output/llm_enriched_incidents.json"
""
"[4/4] Starting local API service"
"      Next: keep this terminal open, then open one of these URLs in your browser:"
"      Telecom Analytics API: http://127.0.0.1:8010"
"      API health: http://127.0.0.1:8010/health"
"      Dashboard UI: http://127.0.0.1:8010/dashboard-data"
"      API docs: http://127.0.0.1:8010/docs"
"      n8n UI: http://127.0.0.1:5678"
"      n8n webhook: http://127.0.0.1:5678/webhook/telecom-ai-run"
""
"      If you only want analysis files and do not want to keep the server running, use:"
"      .venv/Scripts/python.exe main.py analyze --enrich-with-llm --top-n-incidents 25"
.venv/Scripts/python.exe main.py serve --host 0.0.0.0 --port 8010
[status] Starting API server on 0.0.0.0:8010 | ETA 2-5s
INFO:     Started server process [2952]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8010 (Press CTRL+C to quit)
INFO:     127.0.0.1:56411 - "GET /docs HTTP/1.1" 200 OK
INFO:     127.0.0.1:56411 - "GET /openapi.json HTTP/1.1" 200 OK
INFO:     127.0.0.1:60641 - "GET /health HTTP/1.1" 200 OK
```

## Local URLs

- Dashboard UI: `http://127.0.0.1:8010/dashboard-data`
- Dashboard JSON: `http://127.0.0.1:8010/api/dashboard-data`
- API health: `http://127.0.0.1:8010/health`
- API docs: `http://127.0.0.1:8010/docs`
- Database status: `http://127.0.0.1:8010/data-source-status`
- n8n UI: `http://127.0.0.1:5678`

## Output Files

- `output/joined_analysis.csv`
- `output/incidents_summary.csv`
- `output/llm_input.json`
- `output/llm_enriched_incidents.json`
- `output/top_incidents_report.md`

## n8n Workflow

Import [n8n/telecom_ai_workflow.json](n8n/telecom_ai_workflow.json) and follow [n8n/WORKFLOW_SETUP.md](n8n/WORKFLOW_SETUP.md).

The workflow can trigger the analysis pipeline automatically and then call the local API.
