## 001 · 2026-11-18 · transform.py

**Contexto:** `raw_ri` nombra al TF a veces por su nombre oficial y a veces por un sinónimo, así que `silver_reguladores_lookup` tiene que resolver ambos a un solo `regulador_id`.

**Decisión:** El lookup carga los nombres oficiales (`2)regulatorName`) con `prioridad = 1` y los sinónimos (`3)regulatorSynonyms`, separados por `;`, desanidados y limpios con `TRIM`) con `prioridad = 2`; si una clave aparece en ambos niveles gana el menor. Si varios `regulador_id` comparten `tf_buscado` en el mismo nivel, un `QUALIFY` conserva un solo representante (el de menor `regulador_id`) y lo marca `es_ambiguo = TRUE`, para que `tf_buscado` sea una clave única. En `stg_ri`, el `CASE` descarta con motivo `'TF ambiguo'` toda interacción que cruce con una clave marcada, sin usar el representante arbitrario.

**Alternativa:**
- Un diccionario en Python (oficial → sinónimos) recorrido en bucle. Descartada: va contra el patrón del repo (SQL limpia, Python orquesta) y resuelve fila por fila lo que un JOIN resuelve por conjuntos.
- Ignorar los sinónimos y usar solo el nombre oficial. Descartada: los TF que `raw_ri` nombra por sinónimo quedarían sin `regulador_id`.
- Dejar a todos los competidores en el lookup. Descartada: rompe la unicidad de `tf_buscado` y duplica filas (fan-out) en el LEFT JOIN con `raw_ri`.

**Gano:** El nombre oficial gana sobre un sinónimo ajeno y, con una sola fila por clave, el LEFT JOIN no duplica interacciones. Como las claves ambiguas se descartan en `stg_ri`, el representante arbitrario nunca llega a la red; el riesgo queda cubierto para futuras versiones.

**Pierdo:** (1) Las interacciones con una clave ambigua salen de la red aunque uno de los competidores fuera el correcto, y los ids de los competidores (MarR, OmrA) no se pueden recuperar desde el lookup. (2) Un sinónimo de B que coincide con el nombre oficial de A se atribuye a A sin marca; en la corrida A pasa con 1 clave (DicA) y afecta a 3 RIs, atribuidas al oficial sin verificar que sea la lectura correcta.

**Validación:** `COUNT(*) = COUNT(DISTINCT tf_buscado)` en el lookup, o `raise ValueError`. Corrida A: 4 claves ambiguas (SoxQ, InaR, CfxB, T59) con 0 RIs afectadas en `raw_ri`, y el `CASE` de `stg_ri` sobre `es_ambiguo` las descartaría si las hubiera.

## 002 · 2026-11-21 · transform.py

**Contexto:** `raw_ri` es la tabla de hechos y hay que enriquecerla con regulador y operón sin perder ni duplicar filas, dejando el motivo cuando algo no cruza.

**Decisión:** Una vista `stg_ri` con dos LEFT JOIN (a `silver_reguladores_lookup` y a `silver_gen_operon`) en la que cada RI sale con un solo `motivo` (NULL = válida). El `CASE` audita primero el TF y después el gen, y se queda con la primera condición que se cumple. La vista también trae `gene_coding`, que se usará para armar las aristas al final del pipeline.

**Alternativa:** Mandar las filas defectuosas a descartes sin motivo. Descartada: sin el motivo no se puede rastrear por qué se descartó cada fila.

**Gano:** Ninguna fila inválida se elimina en silencio: la vista conserva las 5,281 interacciones y cada una lleva su `motivo`, listo para que el paso siguiente separe válidas y descartes.

**Pierdo:** Una fila con varios defectos solo se reporta por el primero que encuentra el `CASE` (TF antes que gen); el segundo queda oculto hasta corregir el primero. En la corrida A pasa con 0 filas: las 10 descartadas pasan los chequeos de TF y fallan solo en el gen.

**Validación:** `COUNT(DISTINCT identificador) = COUNT(*)` en `stg_ri`, o `raise ValueError` (un fan-out repetiría identificadores). Corrida A: 5,281 = 5,271 válidas + 7 firstGene sin operón + 3 firstGene vacío o guion.

## 003 · 2026-11-21 · transform.py

**Contexto:** `raw_ri`  no viene con identificador único para cada fila.

**Decisión:** Asignar un identificador único con `CAST(rowid AS VARCHAR)`.

**Alternativa:** concatenar las columnas: TF + sitio + unidad para ser el id compuesto. Descartada: No comprobada su unicidad y `rowid` era más simple.

**Gano:** Todas las filas traen identificadores únicos, los cuales sirven para verificar cuando ocurre un fan-out cuando toque enriquecer dicha tabla.

**Pierdo:** No me garantiza que el mismo id apunte a la misma fila en corridas posteriores.

**Validación:** No se puede verificar que un id no esté apuntando a diferentes filas en diferentes corridas

## 004 · 2026-11-24 · transform.py

**Estado:** Propuesta

**Contexto:** Cada RI registra la interacción entre un TF y un `firstGene`, que es el primer gen de la unidad que arranca en su promotor y no siempre el primero del operón: a veces quedan genes antes del promotor. La red necesita una arista por cada gen regulado.

**Decisión:** Expandir cada RI válida de `silver_ri` a todos los genes de su operón (`silver_gen_operon`, por `operon_id`), incluidos los que quedan antes del promotor, igual que el script viejo, para poder reconciliar contra sus ~7,180 aristas de TFs.

**Alternativa:** Expandir solo desde `firstGene` hacia adelante (los genes que sí transcribe ese promotor). Descartada: `silver_gen_operon` no guarda la posición del gen en el operón, y la salida ya no se podría reconciliar contra la del script viejo.

**Gano:** --

**Pierdo:** --

**Validación:** --
