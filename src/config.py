"""Módulo de configuración centralizada del proyecto."""

from pathlib import Path

# Ruta base del proyecto (sube un nivel desde src/)
BASE_DIR = Path(__file__).resolve().parent.parent

# Ruta única a la base de datos DuckDB
DB_PATH = BASE_DIR / "data" / "db" / "regulondb.duckdb"

# Asegura que la carpeta contenedora (data/db) exista antes de intentar conectar
DB_PATH.parent.mkdir(parents=True, exist_ok=True)