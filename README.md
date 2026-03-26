# Telecom Analytics Project Summary

For the full documentation, setup details, and example output, see [README.md](README.md).

## Overview

This project is a telecom analytics system built with Python, MySQL, FastAPI, `n8n`, and an optional local Ollama model.

It reads sample telecom KPI data, detects network issues such as congestion, interference, and coverage problems, and shows the results through a dashboard and API.

## Main Features

- Loads telecom CSV datasets into MySQL
- Runs analytics to detect incidents and classify severity
- Generates recommendations and optional LLM-enriched insights
- Exposes a local dashboard and API
- Supports `n8n` workflow automation
- Can publish a static dashboard snapshot through GitHub Pages

## Requirements

- Python 3.11 or newer
- Docker Desktop or Docker Engine
- GNU Make or a compatible `make` command
- Optional: Ollama for LLM enrichment

Required containers:

- MySQL: `mysql:8.4`
- n8n: `n8nio/n8n:latest`

Create the containers:

```powershell
docker pull mysql:8.4
docker run --name mysql -e MYSQL_ROOT_PASSWORD=root -e MYSQL_DATABASE=telecom_analytics -p 3306:3306 -d mysql:8.4

docker pull n8nio/n8n:latest
docker run --name n8n -p 5678:5678 -d n8nio/n8n:latest
```

If they already exist:

```powershell
docker start mysql
docker start n8n
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Optional MySQL environment values:

```powershell
$env:MYSQL_HOST="127.0.0.1"
$env:MYSQL_PORT="3306"
$env:MYSQL_USER="root"
$env:MYSQL_PASSWORD="root"
$env:MYSQL_DATABASE="telecom_analytics"
```

## Run

Best option:

```powershell
make run
```

Manual commands:

```powershell
.\.venv\Scripts\python.exe main.py load-db --force-reload
.\.venv\Scripts\python.exe main.py analyze --enrich-with-llm --top-n-incidents 25
.\.venv\Scripts\python.exe main.py serve --host 0.0.0.0 --port 8010
```

## Local Links

- Dashboard UI: `http://127.0.0.1:8010/dashboard-data`
- Dashboard JSON: `http://127.0.0.1:8010/api/dashboard-data`
- API docs: `http://127.0.0.1:8010/docs`
- API health: `http://127.0.0.1:8010/health`
- n8n UI: `http://127.0.0.1:5678`

## Important Files

- [main.py](main.py)
- [src/api.py](src/api.py)
- [n8n/telecom_ai_workflow.json](n8n/telecom_ai_workflow.json)
- [n8n/WORKFLOW_SETUP.md](n8n/WORKFLOW_SETUP.md)
- [sql/01_create_schema.sql](sql/01_create_schema.sql)
