"""Módulo para la transformación de datos crudos (Raw) a la Capa Silver en DuckDB."""

from pathlib import Path
import duckdb
from config import DB_PATH

def crear_silver_gen_operon(con):
    """Crea la vista staging y la tabla 'silver_gen_operon' (gen -> operón).

    Registra los genes defectuosos en 'silver_descartes' de forma idempotente
    y ejecuta comprobaciones de calidad y del invariante real.
    """
    # 1. Vista Staging: Desanidar, TRIM() y clasificar con CASE WHEN
    con.sql("""
        CREATE OR REPLACE VIEW stg_operones_desanidados AS
        WITH desanidado AS (
            SELECT 
                TRIM(unnest(string_split(COALESCE("7)operonGenes", ''), ';'))) AS gen,
                "1)operonId" AS operon_id,
                "2)operonName" AS operon_name
            FROM raw_operones
        )
        SELECT 
            gen,
            operon_id,
            operon_name,
            CASE 
                WHEN gen IS NULL OR gen IN ('', '-') THEN 'gen vacío o guion en OperonSet'
                ELSE NULL
            END AS motivo
        FROM desanidado;
    """)

    # 2. Tabla Plata (silver_gen_operon)
    con.sql("""
        CREATE OR REPLACE TABLE silver_gen_operon AS
        SELECT 
            gen,
            operon_id,
            operon_name
        FROM stg_operones_desanidados
        WHERE motivo IS NULL;
    """)

    # 3. Idempotencia en Descartes: Crear tabla si no existe, borrar previos e insertar
    con.sql("""
        CREATE TABLE IF NOT EXISTS silver_descartes (
            fuente VARCHAR,
            identificador VARCHAR,
            valor VARCHAR,
            motivo VARCHAR
        );
    """)

    con.sql("DELETE FROM silver_descartes WHERE fuente = 'OperonSet';")

    con.sql("""
        INSERT INTO silver_descartes (fuente, identificador, valor, motivo)
        SELECT 
            'OperonSet' AS fuente,
            operon_id AS identificador,
            gen AS valor,
            motivo
        FROM stg_operones_desanidados
        WHERE motivo IS NOT NULL;
    """)

    # Validación 1: Aserción de Llave Primaria (Gen Único en Plata)
    unicos_plata, total_plata = con.sql(
        "SELECT COUNT(DISTINCT gen), COUNT(*) FROM silver_gen_operon"
    ).fetchone()

    if unicos_plata != total_plata:
        raise ValueError(
            f"Falla de Llave Primaria en silver_gen_operon: "
            f"{unicos_plata} genes únicos != {total_plata} filas totales."
        )

    # Validación 2: Invariante Real contra la fuente raw_operones
    operones_raw = con.sql(
        'SELECT COUNT(DISTINCT "1)operonId") FROM raw_operones'
    ).fetchone()[0]

    operones_stg = con.sql(
        "SELECT COUNT(DISTINCT operon_id) FROM stg_operones_desanidados"
    ).fetchone()[0]

    total_descartes = con.sql(
        "SELECT COUNT(*) FROM silver_descartes WHERE fuente = 'OperonSet'"
    ).fetchone()[0]

    print("=== Auditoría: silver_gen_operon ===")
    print(f"Operones Únicos en Raw:       {operones_raw}")
    print(f"Operones Únicos en Staging:   {operones_stg}")
    print(f"Genes Válidos en Plata:        {total_plata}")
    print(f"Descartes de OperonSet:        {total_descartes}")

    if operones_raw != operones_stg:
        raise ValueError(
            f"Falla de Invariante Fuente: {operones_raw} operones en raw_operones "
            f"!= {operones_stg} operones procesados en Staging."
        )


def ejecutar_transformacion(con):
    """Orquesta la ejecución modular de las tablas Silver."""
    crear_silver_gen_operon(con)


if __name__ == "__main__":
    conexion = duckdb.connect(str(DB_PATH))

    try:
        ejecutar_transformacion(conexion)
        print("\n¡Transformación ejecutada con éxito!")
    finally:
        conexion.close()