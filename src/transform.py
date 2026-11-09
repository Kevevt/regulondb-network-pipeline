"""Módulo para la transformación de datos crudos (Raw) a la Capa Silver en DuckDB."""

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


def crear_silver_reguladores_lookup(con):
    """ Materializa la tabla 'silver_reguladores_lookup' y audita su llave primaria.
    """

    con.sql("""
        CREATE OR REPLACE VIEW stg_reguladores_lookup AS
        WITH todos_los_nombres AS (
            SELECT 
                "1)regulatorId" AS regulador_id,
                "2)regulatorName" AS regulador_name,
                TRIM("2)regulatorName") AS tf_buscado,
                "5)geneCodingForRegulator" AS gene_coding,
                1 AS prioridad
            FROM raw_reguladores

            UNION ALL

            SELECT 
                "1)regulatorId" AS regulador_id,
                "2)regulatorName" AS regulador_name,
                TRIM(unnest(string_split("3)regulatorSynonyms", ';'))) AS tf_buscado,
                "5)geneCodingForRegulator" AS gene_coding,
                        2 AS prioridad
            FROM raw_reguladores
        ),
        calcular_ambiguedad AS (
            SELECT 
                tf_buscado,
                prioridad,
                COUNT(DISTINCT(regulador_id)) AS n_reguladores
                FROM todos_los_nombres
                WHERE tf_buscado IS NOT NULL AND tf_buscado != '' AND tf_buscado != '-'
                GROUP BY tf_buscado, prioridad
        )
        SELECT 
            t.regulador_id,
            t.regulador_name,
            t.tf_buscado,
            t.gene_coding,
            t.prioridad,
            (c.n_reguladores > 1) AS es_ambiguo
        FROM todos_los_nombres t
        INNER JOIN calcular_ambiguedad c
            ON t.tf_buscado = c.tf_buscado 
            AND t.prioridad = c.prioridad
        QUALIFY ROW_NUMBER() OVER (PARTITION BY t.tf_buscado ORDER BY t.prioridad ASC, t.regulador_id ASC) = 1;
        """)

    # Validación: Aserción de Llave Primaria (tf_buscado)
    con.sql("""
        CREATE OR REPLACE TABLE silver_reguladores_lookup AS
        SELECT
            regulador_id,
            regulador_name,
            tf_buscado,
            gene_coding,
            prioridad,
            es_ambiguo
        FROM stg_reguladores_lookup;
    """)

def ejecutar_transformacion(con):
    """Orquesta la ejecución modular de las tablas Silver."""
    crear_silver_gen_operon(con)
    crear_silver_reguladores_lookup(con)


if __name__ == "__main__":
    conexion = duckdb.connect(str(DB_PATH))

    try:
        ejecutar_transformacion(conexion)
        print("\n¡Transformación ejecutada con éxito!")
    finally:
        conexion.close()