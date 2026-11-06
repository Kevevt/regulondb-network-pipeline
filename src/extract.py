"""Módulo de extracción e ingesta de datos crudos de RegulonDB hacia DuckDB."""
from pathlib import Path
import re
import duckdb
from config import DB_PATH

COLUMNAS_SRNA = [
    "srna_id",
    "srna_name",
    "gene_name",
    "regulated_type",
    "pos_left",
    "pos_right",
    "strand",
    "function",
    "sequence",
    "mechanism",
    "evidence",
    "confidence_level",
]


def validar_columnas_archivo(ruta_archivo, columnas_esperadas):
    """Verifica que el archivo declare exactamente el número esperado de columnas.

    Lanza ValueError si el conteo difiere o si no detecta ninguna declaración (# (N)).
    """
    total_declaradas = 0
    with open(ruta_archivo, mode="r", encoding="utf-8") as f:
        for line in f:
            if not line.startswith("#"):
                break
            if re.search(r"^#+\s*\(\d+\)", line):
                total_declaradas += 1

    if total_declaradas != len(columnas_esperadas):
        raise ValueError(
            f"Desajuste en {Path(ruta_archivo).name}: se requerían {len(columnas_esperadas)} "
            f"columnas declaradas en comentarios, pero se encontraron {total_declaradas}."
        )


def extraer_metadatos(archivo_interes):
    """Extrae líneas de encabezado a omitir, release y fecha normalizada en ISO (YYYY-MM-DD)."""
    skip_lines = 0
    fecha_iso = None
    release = None
    esperando_fecha = False

    patron_release = r"release[:\s]+([0-9]+(?:\.[0-9]+)+)"
    patron_fecha = r"([0-9]{2})[/-]([0-9]{2})[/-]([0-9]{4})"

    with open(archivo_interes, mode="r", encoding="utf-8") as f:
        for line in f:
            if not line.startswith("#"):
                break
            skip_lines += 1

            if release is None:
                m_rel = re.search(patron_release, line, re.IGNORECASE)
                if m_rel:
                    release = m_rel.group(1)

            if fecha_iso is None:
                if esperando_fecha:
                    m_fec = re.search(patron_fecha, line)
                    if m_fec:
                        mm, dd, yyyy = m_fec.groups()
                        fecha_iso = f"{yyyy}-{mm}-{dd}"
                        esperando_fecha = False

                elif re.search(r"^#\s*\bdate\b[:\s]*$", line, re.IGNORECASE):
                    esperando_fecha = True

                else:
                    m_inline = re.search(
                        rf"\bdate[:\s]+{patron_fecha}", line, re.IGNORECASE
                    )
                    if m_inline:
                        mm, dd, yyyy = m_inline.groups()
                        fecha_iso = f"{yyyy}-{mm}-{dd}"

    return skip_lines, fecha_iso, release


def cargar_tabla(
    con, ruta_archivo, nombre_tabla, names=None, all_varchar=True
):
    """Carga de forma idempotente una tabla en la base de datos DuckDB proporcionada

    y registra el evento en la bitácora histórica control_cargas.
    """
    ruta = Path(ruta_archivo)

    if names is not None:
        validar_columnas_archivo(ruta, names)

    skip_lines, fecha, release = extraer_metadatos(ruta)

    relacion = con.read_csv(
        str(ruta),
        delimiter="\t",
        header=True if names is None else False,
        skiprows=skip_lines,
        all_varchar=all_varchar,
        names=names,
    )

    con.sql(f"CREATE OR REPLACE TABLE {nombre_tabla} AS SELECT * FROM relacion")

    total_filas = con.sql(
        f"SELECT COUNT(*) FROM {nombre_tabla}"
    ).fetchone()[0]

    con.sql(
        """
        CREATE TABLE IF NOT EXISTS control_cargas (
            tabla VARCHAR,
            archivo VARCHAR,
            release VARCHAR,
            fecha_fuente DATE,
            filas BIGINT,
            fecha_ingesta TIMESTAMP DEFAULT current_timestamp
        )
    """
    )

    con.sql(
        """
        INSERT INTO control_cargas (tabla, archivo, release, fecha_fuente, filas)
        VALUES (?, ?, ?, ?, ?)
    """,
        params=[nombre_tabla, ruta.name, release, fecha, total_filas],
    )


def ejecutar_extraccion(con, data_dir=None):
    """Orquesta la extracción de los 5 archivos del pipeline.

    Resuelve la ruta data/ a partir de la ubicación física de este archivo.
    """
    if data_dir is None:
        base_dir = Path(__file__).resolve().parent.parent
        data_dir = base_dir / "data" / "raw"
    else:
        data_dir = Path(data_dir)

    archivos = [
        (data_dir / "OperonSet.tsv", "raw_operones", None),
        (data_dir / "RegulatorSet.tsv", "raw_reguladores", None),
        (data_dir / "RISet_cropped.txt", "raw_ri", None),
        (data_dir / "NetworkSigmaGene.tsv", "raw_sigmas", None),
        (data_dir / "sRNABindingSiteSet.txt", "raw_srna", COLUMNAS_SRNA),
    ]

    for ruta, tabla, names in archivos:
        cargar_tabla(con, ruta, tabla, names=names)

    return con


if __name__ == "__main__":
    conexion = duckdb.connect(str(DB_PATH))

    try:
        ejecutar_extraccion(conexion)
        print("=== Auditoría de Extracción Finalizada ===")
        conexion.sql("SELECT * FROM control_cargas").show()
    finally:
        conexion.close()