"""Módulo de configuración centralizada del proyecto."""

from pathlib import Path

# Ruta base del proyecto (sube un nivel desde src/)
BASE_DIR = Path(__file__).resolve().parent.parent

# Carpetas del proyecto
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"  # O "raw_14.5.0" cuando manejes versiones de la fuente

# Ruta a la base de datos DuckDB
DB_PATH = DATA_DIR / "db" / "regulondb.duckdb"

# Asegurar que los directorios físicos existan
RAW_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)