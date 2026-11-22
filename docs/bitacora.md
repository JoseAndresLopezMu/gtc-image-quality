# Bitácora

Registro de cada paso: qué hizo el agente, qué revisé y qué decidí. Es la fuente de la sección "Cómo lo construí" del README.

## Paso 0 - Elección del proyecto (2026-11-20)

**Contexto:** el GTC busca un perfil de ciencia de datos para dos líneas: observaciones con límite de difracción (óptica adaptativa, calidad óptica del telescopio) y transformación digital (mantenimiento, gemelo digital). Al revisar mi portfolio, todos mis proyectos de astronomía usaban datos sintéticos y ninguno trataba la calidad óptica.

**Agente:** propuso tres proyectos (calidad de imagen con datos reales del GTC, simulación de óptica adaptativa y gemelo digital) y comprobó que el archivo público del GTC permite consultar y descargar sin registro, aunque solo mediante un formulario web.

**Decisión:** empezar por la calidad de imagen con datos reales, porque cubre a la vez el trabajo con datos del observatorio y la calidad óptica. Mismo método que `rag-eval`: especificación antes del código, bitácora, tests y CI.

## Paso 1 - Especificación y CLAUDE.md (2026-11-20)

**Agente:** redactó `docs/SPEC.md` (borrador v0) y `CLAUDE.md`. Dejó tres decisiones abiertas en la SPEC (sección 12): usar ADP de DRAGO o datos crudos, perfil Moffat o gaussiano, y qué noches usar.

**Revisión:** pendiente.

**Decisión:** pendiente.

## Exploración de datos (2026-11-20)

**Yo:** consulté el archivo del GTC desde el formulario web (OSIRIS, imagen de banda ancha, febrero a julio de 2025, solo productos con datos reducidos) y exporté los resultados a CSV. La primera consulta, sin ese filtro, devolvió 8976 productos y superaba el límite de exportación de 5000 filas.

**Agente:**
- Analizó el CSV (371 fotogramas) agrupando por programa, bloque, objeto y noche, y propuso el bloque `GTCMULTIPLE7B-25A` 0037 (54 fotogramas en Sloan i y z, masa de aire de 1,26 a 1,47).
- Descargó un único producto de prueba y comprobó qué contiene cada enlace del CSV. La columna "QLA Reduced Data" contiene los ADP de DRAGO, aunque en el formulario no lo parece. Los ficheros de QC incluyen el parte de la noche, pero ninguna FWHM medida por el observatorio.
- Leyó las cabeceras reales y documentó las claves en la SPEC (sección 4.4). Encontró que cada exposición lleva la humedad, el viento, la elevación y el foco, y propuso añadir un análisis exploratorio con ellos (sección 5.5).
- Detectó que no hay clave de saturación y lo dejó como decisión pendiente (sección 12).

**Cambio de plan:** el CSV trae enlaces de descarga directa, así que la descarga se automatiza con un comando `fetch` basado en un manifiesto, en lugar de hacerla a mano.

## Paso 2 - Estructura, CI, descarga e índice (2026-11-20)

**Revisión del paso 1:** di el visto bueno al plan. Acepté medir sobre ADP, perfil Moffat y el bloque 0037 como noche principal.

**Agente:**
- Al preparar la descarga comprobó que los ADP solo se pueden bajar en un ZIP por fotograma que incluye también los apilados del bloque (unos 133 MB por fotograma, 7 GB en total). Propuso medir sobre los crudos (7 MB cada uno), cuya cabecera trae las regiones de overscan (`BIASSEC`) y de recorte (`TRIMSEC`), y usar los ADP solo para una comprobación cruzada. Con eso la saturación se detecta directamente (65535 ADU en el crudo). Lo justificó en la SPEC: el flat no cambia la FWHM a la escala de una estrella. Actualizó las secciones 3, 5.0, 8, 9 y 12.
- Creó el proyecto con uv y los módulos `archive`, `manifest`, `fetch`, `headers`, `preprocess` y `cli` (comandos `manifest`, `fetch` e `index`), y el workflow de CI.
- Los tests usan una fila del CSV real copiada literalmente y los valores reales de la cabecera del producto 5456875. Al escribirlos, el agente supuso los valores de `CD2_1` y `CD2_2`, que no había leído; después los comprobó en el fichero real y sustituyó la suposición por los valores reales.
- La descarga simulada (`httpx.MockTransport`) comprueba que el primer `fetch` congela el SHA-256 en el manifiesto, que una segunda ejecución no vuelve a descargar y que un hash distinto no deja ningún fichero.

**Resultado:** 32 tests en verde, sin red. Lint, formato y tipos en verde. El manifiesto del bloque 0037 tiene 52 productos: el parte de la noche habla de 54 ADP, pero la consulta exportada solo incluye 52 fotogramas de ese bloque. Queda anotado para revisarlo.

**Revisión:** pendiente.

## Paso 3 - Estrellas sintéticas y medidas (2026-11-21 y 22)

**Agente:**
- Escribió `synthetic.py` (estrellas de Moffat elípticas con FWHM, elipticidad y ángulo conocidos, ruido de Poisson y de lectura con la ganancia y el ruido de la cabecera de OSIRIS+), `stars.py` (detección con DAOStarFinder y selección: más de 10 σ, sin saturar, aisladas a 5 FWHM, a 20 px del borde y compactas) y `measure.py` (ajuste de Moffat elíptico y gaussiano, elipticidad por ajuste y por momentos, fondo con sigma clipping, mediana y MAD por fotograma).
- Primera medida con sintéticos: cumplía con FWHM de 2 a 5 px, pero con estrellas de 8 px y alargadas el error llegaba al 16 %: el recorte era pequeño. Lo corrigió con un recorte que crece con la estrella y un punto de partida del ajuste a partir de la forma del núcleo. Después: error de FWHM ≤ 1,7 % y de elipticidad ≤ 0,011 en todo el rango (FWHM de 2 a 8 px, elipticidad de 0 a 0,3).
- Encontró que la elipticidad por momentos, la que pide la SPEC, la subestima mucho (error de hasta 0,23). No cambió la definición: lo planteó como decisión del autor (SPEC, sección 12, punto 5).
- Había puesto un filtro que descartaba estrellas poco redondas. Lo quitó antes de probarlo, porque escondería justo los problemas de guiado que el proyecto quiere detectar.
- El test de estrellas demasiado juntas falló: una pareja a 1,5 FWHM se detecta como una sola estrella. Es una limitación real del detector; cambió el test a una pareja separable (3 FWHM) y documentó la limitación en la SPEC.
- Adaptó el código a photutils 3, que renombró las columnas de centroides.

**Prueba con datos reales (no es el paso 4, solo comprobar que funciona):**
- La primera ejecución con una foto real no terminaba: algunos ajustes divergían (FWHM de 29 px o de 0,05 px) y el recorte crecía sin límite. Añadió límites físicos al ajuste y un tamaño máximo de recorte (SPEC, sección 12, punto 6).
- Resultados: producto 5456875 (Sloan i, 100 s, masa de aire 1,47): 120 estrellas usadas, FWHM 1,11″ (MAD 0,24 px), elipticidad 0,098, 31 s. Producto 5456824 (Sloan z, 50 s, masa de aire 1,26): 317 estrellas, FWHM 1,14″ (MAD 0,23 px), elipticidad 0,056, 37 s.
- Comprobó que las 1.258 detecciones descartadas por saturación son reales: 39.616 píxeles a 65535 en 2.374 zonas. Es un campo del plano galáctico con 100 s de exposición.

**Para el paso 4:** entre el 33 y el 40 % de las candidatas acaban como `fit_failed`, hay que ver por qué; el ruido del fondo está inflado por el viñeteo (sin flat), así que el fondo debe medirse por zonas.

**Resultado:** 54 tests en verde. Lint, formato y tipos en verde.

**Revisión:** pendiente (en especial, la decisión 5 de la SPEC).
