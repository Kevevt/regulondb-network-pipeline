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