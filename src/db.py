from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd
import pymysql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .utils import DATA_DIR, PROJECT_ROOT, ensure_directories

ProgressCallback = Callable[[str, str], None]


@dataclass(frozen=True)
class MySQLConfig:
    host: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    port: int = int(os.getenv("MYSQL_PORT", "3306"))
    user: str = os.getenv("MYSQL_USER", "root")
    password: str = os.getenv("MYSQL_PASSWORD", "root")
    database: str = os.getenv("MYSQL_DATABASE", "telecom_analytics")


def _emit_progress(progress: ProgressCallback | None, message: str, eta: str) -> None:
    if progress is not None:
        progress(message, eta)


def _mysql_url(config: MySQLConfig, include_database: bool = True) -> str:
    database_part = f"/{config.database}" if include_database else ""
    return f"mysql+pymysql://{config.user}:{config.password}@{config.host}:{config.port}{database_part}?charset=utf8mb4"


def _schema_path() -> Path:
    return PROJECT_ROOT / "sql" / "01_create_schema.sql"


def _sql_path(filename: str) -> Path:
    return PROJECT_ROOT / "sql" / filename


def wait_for_mysql(config: MySQLConfig | None = None, timeout_seconds: int = 90) -> None:
    config = config or MySQLConfig()
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            connection = pymysql.connect(
                host=config.host,
                port=config.port,
                user=config.user,
                password=config.password,
                charset="utf8mb4",
                autocommit=True,
            )
            connection.close()
            return
        except Exception as error:  # pragma: no cover - connection errors are environment-specific
            last_error = error
            time.sleep(2)
    raise RuntimeError(f"MySQL is not reachable at {config.host}:{config.port}. Last error: {last_error}") from last_error


def ensure_database_schema(config: MySQLConfig | None = None) -> None:
    config = config or MySQLConfig()
    wait_for_mysql(config)
    schema_sql = _schema_path().read_text(encoding="utf-8")
    statements = [statement.strip() for statement in schema_sql.split(";") if statement.strip()]
    connection = pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
    finally:
        connection.close()


def get_engine(config: MySQLConfig | None = None) -> Engine:
    config = config or MySQLConfig()
    ensure_database_schema(config)
    return create_engine(_mysql_url(config), future=True, pool_pre_ping=True)


def _normalize_datetime_columns(df: pd.DataFrame, column: str) -> pd.DataFrame:
    normalized = df.copy()
    normalized[column] = pd.to_datetime(normalized[column], utc=True).dt.strftime("%Y-%m-%d %H:%M:%S")
    return normalized


def _write_dataframe(connection, table_name: str, dataframe: pd.DataFrame) -> None:
    records = dataframe.where(pd.notna(dataframe), None).to_dict(orient="records")
    if not records:
        return
    columns = list(dataframe.columns)
    quoted_columns = ", ".join(f"`{column}`" for column in columns)
    placeholders = ", ".join(f"%({column})s" for column in columns)
    sql = f"INSERT INTO `{table_name}` ({quoted_columns}) VALUES ({placeholders})"
    with connection.cursor() as cursor:
        for start in range(0, len(records), 2000):
            cursor.executemany(sql, records[start : start + 2000])
    connection.commit()


def bootstrap_database_from_csvs(force_reload: bool = False, progress: ProgressCallback | None = None) -> dict[str, int]:
    ensure_directories()
    config = MySQLConfig()
    ensure_database_schema(config)

    ue_path = DATA_DIR / "ue_measurements.csv"
    beam_path = DATA_DIR / "beam_kpis.csv"
    if not ue_path.exists() or not beam_path.exists():
        raise FileNotFoundError("Expected existing data/ue_measurements.csv and data/beam_kpis.csv before loading MySQL.")

    _emit_progress(progress, "Reading existing CSV datasets", "ETA 2-8s")
    ue_df = _normalize_datetime_columns(pd.read_csv(ue_path), "timestamp_utc")
    beam_df = _normalize_datetime_columns(pd.read_csv(beam_path), "window_start_utc")

    connection = pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=config.database,
        charset="utf8mb4",
        autocommit=False,
    )
    try:
        with connection.cursor() as cursor:
            if force_reload:
                _emit_progress(progress, "Refreshing MySQL tables from CSV files", "ETA 5-20s")
                cursor.execute("TRUNCATE TABLE ue_measurements")
                cursor.execute("TRUNCATE TABLE beam_kpis")
            else:
                cursor.execute("SELECT COUNT(*) FROM ue_measurements")
                ue_existing = int(cursor.fetchone()[0])
                cursor.execute("SELECT COUNT(*) FROM beam_kpis")
                beam_existing = int(cursor.fetchone()[0])
                if ue_existing > 0 and beam_existing > 0:
                    return {"ue_rows": ue_existing, "beam_rows": beam_existing}

        _emit_progress(progress, "Loading UE measurements into MySQL", "ETA 5-20s")
        _write_dataframe(connection, "ue_measurements", ue_df)
        _emit_progress(progress, "Loading beam KPIs into MySQL", "ETA 5-15s")
        _write_dataframe(connection, "beam_kpis", beam_df)

        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM ue_measurements")
            ue_rows = int(cursor.fetchone()[0])
            cursor.execute("SELECT COUNT(*) FROM beam_kpis")
            beam_rows = int(cursor.fetchone()[0])
        return {"ue_rows": ue_rows, "beam_rows": beam_rows}
    finally:
        connection.close()


def load_measurements_from_mysql(progress: ProgressCallback | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    engine = get_engine()
    _emit_progress(progress, "Fetching UE measurements from MySQL", "ETA 2-8s")
    ue_query = text(_sql_path("10_fetch_ue_measurements.sql").read_text(encoding="utf-8"))
    beam_query = text(_sql_path("11_fetch_beam_kpis.sql").read_text(encoding="utf-8"))
    with engine.connect() as connection:
        ue_df = pd.read_sql(ue_query, connection)
        _emit_progress(progress, "Fetching beam KPI windows from MySQL", "ETA 2-8s")
        beam_df = pd.read_sql(beam_query, connection)

    ue_df["timestamp_utc"] = pd.to_datetime(ue_df["timestamp_utc"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    beam_df["window_start_utc"] = pd.to_datetime(beam_df["window_start_utc"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return ue_df, beam_df


def database_snapshot() -> dict:
    engine = get_engine()
    with engine.connect() as connection:
        summary = {
            "ue_rows": int(connection.execute(text("SELECT COUNT(*) FROM ue_measurements")).scalar_one()),
            "beam_rows": int(connection.execute(text("SELECT COUNT(*) FROM beam_kpis")).scalar_one()),
            "latest_ue_timestamp": connection.execute(text("SELECT DATE_FORMAT(MAX(timestamp_utc), '%Y-%m-%dT%H:%i:%sZ') FROM ue_measurements")).scalar_one(),
            "latest_beam_window": connection.execute(text("SELECT DATE_FORMAT(MAX(window_start_utc), '%Y-%m-%dT%H:%i:%sZ') FROM beam_kpis")).scalar_one(),
        }
        ue_preview = pd.read_sql(
            text("SELECT timestamp_utc, ue_id, serving_cell_id, beam_id, sinr_db, latency_ms FROM ue_measurements ORDER BY timestamp_utc DESC LIMIT 5"),
            connection,
        ).to_dict(orient="records")
        beam_preview = pd.read_sql(
            text("SELECT window_start_utc, cell_id, beam_id, avg_sinr_db, avg_bler_dl_pct, prb_utilization_pct FROM beam_kpis ORDER BY window_start_utc DESC LIMIT 5"),
            connection,
        ).to_dict(orient="records")
    return {"status": "ok", "database": MySQLConfig().database, "summary": summary, "ue_preview": ue_preview, "beam_preview": beam_preview}
