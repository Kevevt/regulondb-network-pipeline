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

    # Validación: Aserción de Llave Primaria (tf_buscado)
    unicos_plata, total_plata = con.sql(
        "SELECT COUNT(DISTINCT tf_buscado), COUNT(*) FROM silver_reguladores_lookup"
    ).fetchone()

    if unicos_plata != total_plata:
        raise ValueError(
            f"Falla de Llave Primaria en silver_reguladores_lookup: "
            f"{unicos_plata} claves únicas != {total_plata} filas totales."
        )
    
def crear_view_ri(con):
    """ Enriquece raw_ri con regulador y operón, y marca el motivo de descarte """
    con.sql("""
        CREATE OR REPLACE VIEW stg_ri AS
        WITH ri_limpio AS (
        SELECT
            CAST(rowid AS VARCHAR) AS identificador,
            TRIM("4)tfName") AS tf,
            TRIM("16)firstGene") AS first_gene,
            "11)riFunction" AS ri_function,
            "20)tfrsEvidence" AS tfrs_evidence,
            "21)riEvidence" AS ri_evidence

        FROM raw_ri
            )
        SELECT
            r.identificador,
            r.tf,
            reguladores.gene_coding,
            r.first_gene,
            r.ri_function,
            r.tfrs_evidence,
            r.ri_evidence,
            reguladores.regulador_id,
            g.operon_id,

        -- Se audita primero el TF antes que el gen
        CASE
            WHEN r.tf IS NULL OR r.tf IN ('', '-') THEN 'TF vacío o guion'
            WHEN reguladores.regulador_id IS NULL OR reguladores.regulador_id IN ('', '-') THEN 'TF no está en el lookup'
            WHEN reguladores.es_ambiguo IS True THEN 'TF ambiguo'
            WHEN r.first_gene IS NULL OR r.first_gene IN ('', '-') THEN 'firstGene vacío o guion'
            WHEN g.gen IS NULL THEN 'firstGene sin operón'
        END AS motivo
        FROM ri_limpio r
        LEFT JOIN silver_reguladores_lookup reguladores ON r.tf = reguladores.tf_buscado
        LEFT JOIN silver_gen_operon g ON r.first_gene = g.gen
    """)

    unicos_plata, total_plata = con.sql(
        "SELECT COUNT(DISTINCT identificador), COUNT(*) FROM stg_ri"
    ).fetchone()

    if unicos_plata != total_plata:
        raise ValueError(
            f"Falla de Llave Primaria en stg_ri: "
            f"{unicos_plata} claves únicas != {total_plata} filas totales."
        )

    total_stg = con.sql("SELECT COUNT(*) FROM stg_ri").fetchone()[0]
    print(f"Filas en stg_ri: {total_stg}")

    con.sql("""
                SELECT 
                    COALESCE(motivo, 'Válido') AS motivo,
                    COUNT(*) AS total
                FROM stg_ri
                GROUP BY motivo
                ORDER BY total DESC
        """).show()

def ejecutar_transformacion(con):
    """Orquesta la ejecución modular de las tablas Silver."""
    crear_silver_gen_operon(con)
    crear_silver_reguladores_lookup(con)
    crear_view_ri(con)


if __name__ == "__main__":
    conexion = duckdb.connect(str(DB_PATH))

    try:
        ejecutar_transformacion(conexion)
        print("\n¡Transformación ejecutada con éxito!")
    finally:
        conexion.close()