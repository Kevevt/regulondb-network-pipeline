# regulondb-network-pipeline

Pipeline en Python y DuckDB que ingesta los datos de regulación transcripcional de *E. coli* K-12 publicados por RegulonDB, para construir a partir de ellos su red de regulación.

**Estado actual:** la etapa de extracción funciona. La transformación (limpieza, llaves y modelo de la red) está en desarrollo.

<!-- TODO: cuando definas la transformación, di qué produce exactamente (lista de aristas, tablas de nodos y aristas, archivo de grafo, etc.) -->

## Contexto

- **RegulonDB** es la base de datos de referencia sobre regulación transcripcional en *E. coli* K-12, curada a partir de literatura experimental. Describe qué reguladores (factores de transcripción, factores sigma, sRNAs) controlan qué genes y operones.
- **Una red de regulación** representa esas relaciones como un grafo: los nodos son genes y reguladores; las aristas indican quién regula a quién y con qué efecto.
- **Método:** la construcción de la red seguirá la metodología publicada de Abasy Atlas ([Ibarra-Arellano et al., 2016](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4885605/)).

<!-- TODO: añade 2-3 líneas en tus palabras sobre por qué importa esta red (qué pregunta biológica permite responder). Aquí es donde se nota tu formación como biotecnólogo. -->

## Estado del proyecto

| Etapa | Estado | Archivo |
|---|---|---|
| Extracción a DuckDB con bitácora de cargas | Funciona | `src/extract.py` |
| Transformación: limpieza, llaves y modelo relacional | En desarrollo | `src/transform.py` (pendiente) |
| Pruebas automatizadas | Pendiente | `tests/` (pendiente) |

## Datos de origen

Los archivos no se incluyen en el repositorio. Se descargan de RegulonDB y se colocan en `data/raw/`.

<!-- TODO: link exacto de descarga, release y fecha de descarga -->

| Archivo | Tabla en DuckDB | Notas |
|---|---|---|
| `OperonSet.tsv` | `raw_operones` | |
| `RegulatorSet.tsv` | `raw_reguladores` | |
| `RISet_cropped.txt` | `raw_ri` | Versión recortada del original; ver nota abajo |
| `NetworkSigmaGene.tsv` | `raw_sigmas` | |
| `sRNABindingSiteSet.txt` | `raw_srna` | Sin encabezado tabular; columnas definidas en `COLUMNAS_SRNA` |

<!-- TODO: documenta cómo se generó RISet_cropped.txt a partir del original (qué se recortó y por qué). Sin esto, nadie puede reproducir la ingesta. Lo ideal es que sea un script. -->

## Requisitos

- Python 3.13
- DuckDB 1.5.6 (en `requirements.txt`)

## Quickstart

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
mkdir data\raw
```

**Linux / macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p data/raw
```

Después, coloca los 5 archivos fuente en `data/raw/` y ejecuta desde la raíz del repositorio:

```bash
python src/extract.py
```

Para trabajar con notebooks, instala también las dependencias de desarrollo: `pip install -r requirements-dev.txt`.

### Salida esperada

Al terminar, el script imprime la bitácora de cargas:

<!-- TODO: pega aquí la salida real de una corrida -->

```text
=== Auditoría de Extracción Finalizada ===
```

## Decisiones de diseño

**DuckDB como almacén local.** Los 5 archivos se van a cruzar con SQL en la etapa de transformación. DuckDB corre dentro del proceso de Python, sin servidor, lee TSV directamente con `read_csv` y está optimizado para consultas analíticas.
- Frente a SQLite: también es embebida, pero almacena por filas y está pensada para cargas transaccionales, no analíticas. Además, desde Python no ofrece un lector de CSV/TSV integrado como `read_csv`.
- Frente a pandas: DuckDB persiste los datos en un archivo y permite expresar las transformaciones en SQL.

<!-- TODO: ajusta si tus razones reales fueron otras -->

**Rutas ancladas al archivo, no al directorio de trabajo.** Las rutas se construyen a partir de `Path(__file__).resolve()`, así que el script encuentra `data/` sin importar desde dónde se ejecute. `ejecutar_extraccion()` acepta además un `data_dir` opcional, lo que permite apuntar a otra carpeta (por ejemplo, datos de prueba).

**Carga cruda sin conversión de tipos.** Todas las columnas se cargan como texto (`all_varchar=True`). La conversión de tipos se deja para la transformación, donde se puede validar explícitamente, en lugar de que el lector de CSV adivine tipos y pierda datos en silencio.

**Encabezados leídos del archivo, no fijos en el código.** Los archivos de RegulonDB empiezan con líneas de comentario (`#`). `extraer_metadatos()` cuenta esas líneas para saltarlas al leer, y extrae de ellas el número de release y la fecha de publicación. Si RegulonDB cambia la longitud del encabezado, la lectura no se desfasa.

**Validación de columnas para el archivo de sRNA.** `sRNABindingSiteSet.txt` no tiene una fila de encabezado: declara sus columnas en comentarios con el formato `# (N)`. Antes de cargarlo, `validar_columnas_archivo()` cuenta esas declaraciones y detiene la ejecución con `ValueError` si no coinciden con las 12 columnas esperadas.

**Bitácora de cargas (`control_cargas`).** Cada carga registra tabla, archivo, release, fecha de la fuente, número de filas y momento de ingesta. Las tablas `raw_*` se reemplazan en cada corrida (`CREATE OR REPLACE`), así que repetir la extracción deja los mismos datos. `control_cargas`, en cambio, acumula una fila por carga a propósito: es el historial de ejecuciones.

## Limitaciones conocidas

- La fecha de los encabezados se interpreta como MM/DD/AAAA. <!-- TODO: verifica el formato en los archivos reales -->
- Las cargas no van dentro de una transacción: si falla un archivo a mitad de la extracción, los anteriores ya quedaron reemplazados.
- Solo el archivo de sRNA tiene validación de columnas; los otros 4 se leen con su propio encabezado.

## Estructura

```text
regulondb-network-pipeline/
├── data/                  # No versionado
│   ├── raw/               # Archivos fuente de RegulonDB
│   └── db/                # regulondb.duckdb
├── src/
│   └── extract.py         # Extracción a DuckDB y bitácora de cargas
├── requirements.txt
└── requirements-dev.txt
```

`data/` y `notebooks/` están excluidos de Git. <!-- TODO: aclara el motivo (licencia de RegulonDB, tamaño de los archivos o ambos) -->

## Fuente de los datos

Datos de RegulonDB. <!-- TODO: añade la cita que RegulonDB pide en sus términos de uso -->