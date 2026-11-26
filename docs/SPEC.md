# gtc-image-quality: especificación

Estado: borrador v0 (pendiente de revisión)
Fecha: 2026-11-20

## 1. Problema

La calidad de imagen que entrega un telescopio no es la misma que el seeing del sitio. Depende de la masa de aire, de la longitud de onda, del enfoque, del guiado, del faseado de los segmentos y de la térmica de la cúpula. El GTC evalúa la calidad de imagen con la anchura a media altura (FWHM) de las estrellas en las propias imágenes científicas, y una de sus prioridades es llevar el telescopio a su calidad óptica nominal y operar con óptica adaptativa.

Desde el semestre 2025A el GTC entrega productos reducidos automáticamente (ADP) de OSIRIS+ en imagen de banda ancha, generados por su sistema DRAGO. Esos productos, sus cabeceras y los datos crudos son públicos en el archivo del GTC (CAB, INTA-CSIC) un año después de la observación.

`gtc-image-quality` es una herramienta de línea de comandos que mide la calidad de imagen de cada fotograma de OSIRIS+, marca automáticamente los fotogramas dudosos con un motivo explicable y produce un informe que relaciona la calidad medida con las condiciones de la observación.

## 2. Objetivos

1. **Medir** en cada fotograma: FWHM (en píxeles y en segundos de arco), elipticidad, nivel y ruido del fondo del cielo, número de estrellas útiles y fracción de píxeles saturados.
2. **Validar** que las medidas son correctas con imágenes sintéticas de FWHM y elipticidad conocidas.
3. **Marcar** fotogramas dudosos con reglas de control de calidad configurables, cada una con su motivo (por ejemplo, "elipticidad 0,28 > 0,20: posible pérdida de guiado").
4. **Relacionar** la calidad medida con la masa de aire y el filtro, y comprobar si sigue la dependencia esperada por la teoría de la turbulencia (FWHM ∝ masa de aire^0,6 y ∝ λ^−0,2).
5. **Reproducibilidad**: misma entrada, mismo informe. La lista exacta de ficheros usados queda registrada.

## 3. Fuera de alcance (v1)

- Reducción completa con flats. Las medidas se hacen sobre los fotogramas crudos con la resta del nivel de overscan y el recorte de la cabecera (sección 5.0). El flat corrige variaciones de sensibilidad que son muy suaves a la escala de una estrella, así que no cambia la FWHM ni la elipticidad. Sí afecta al nivel absoluto del fondo, que por eso solo se compara dentro de una misma noche y filtro.
- Calibración fotométrica, astrometría y fotometría de ciencia.
- Otros instrumentos (EMIR, MEGARA, HiPERCAM) y espectroscopía.
- Datos de monitores de seeing del sitio. En v1 la calidad solo se relaciona con lo que hay en la cabecera.
- Modelos de machine learning. En v1 el control de calidad son reglas explicables. Si con los datos reales hay suficientes casos, se valorará un clasificador en una versión posterior.
- Tiempo real o integración con sistemas del observatorio.

## 4. Datos

### 4.1 Origen

Archivo Científico Público del GTC: https://gtc.sdc.cab.inta-csic.es/gtc/. La consulta no requiere registro. El archivo no tiene una API documentada, pero el formulario web exporta los resultados a CSV (hasta 5000 filas) y ese CSV incluye un enlace de descarga directa por producto. Comprobado el 2026-11-20:

| Columna del CSV | Qué descarga |
|---|---|
| `Raw Data` | El fotograma crudo (`.fits.gz`, ~7 MB con binning 2×2) |
| `QLA Reduced Data` | Un ZIP con los ADP de DRAGO del bloque: un ADP por fotograma (`ADP_<id>-<fecha>-OSIRIS-IMG.fits.gz`) y los apilados por filtro |
| `Cal. Files` | Un ZIP con los bias y flats de cielo del bloque |
| `QC Files` | Un ZIP con el parte de la noche (PDF), una tabla de metadatos de cada fichero (`qc.dat`) y avisos del pipeline |
| `GTC Reduced Data`, `User Reduced Data` | Vacías en la consulta usada |

La consulta exportada está en `data/archive_query_2025A_osiris_bbi.csv`: OSIRIS, imagen de banda ancha, 1 de febrero a 31 de julio de 2025, solo productos con datos reducidos. Son 371 fotogramas.

El parte de la noche indica los requisitos del bloque (seeing, nubes, Luna) y si el observatorio consideró buena la calidad de imagen, pero ni el parte ni `qc.dat` incluyen una FWHM medida. No hay, por tanto, una referencia del observatorio contra la que comparar las medidas; la validación se hace con imágenes sintéticas (sección 7).

### 4.2 Selección para v1

Bloque principal: programa `GTCMULTIPLE7B-25A`, bloque `0037`, objeto `GRB250702B-E`, noche del 19 al 20 de julio de 2025.

- 54 ADP por fotograma en Sloan i y Sloan z, con 50 y 100 s de exposición.
- Masa de aire de 1,26 a 1,47 a lo largo de la noche.
- Es un seguimiento de un estallido de rayos gamma en el plano galáctico: campo con muchas estrellas, bueno para medir la FWHM.

Para ampliar el rango de masa de aire en el análisis 5.5 se añadieron en el paso 5 tres bloques de otras noches del mismo CSV:

| Programa y bloque | Objeto | Noche | Fotogramas | Filtros | Masa de aire |
|---|---|---|---|---|---|
| `GTCMULTIPLE7B-25A` 0001 | `250215A` | 9-10 de marzo de 2025 | 30 | Sloan i (120 s) y z (50 s) | 1,85 a 2,03 |
| `GTCMULTIPLE4G-25A` 0004 | `GRB250314A` | 14-15 de marzo de 2025 | 31 | Sloan z (30 s) | 1,51 a 1,71 |
| `GTCMULTIPLE7B-25A` 0038 | `250704a` | 28-29 de julio de 2025 | 19 | Sloan i (90 y 10 s) | 1,04 a 1,05 |

Son campos fuera del plano galáctico, con muchas menos estrellas que el bloque 0037 (de 5 a 90 por fotograma en los de marzo). Con ellos el manifiesto tiene 132 productos de cuatro noches.

### 4.3 Manifiesto y descarga

Los FITS no se versionan. `data/manifest.csv` lista cada producto usado con su identificador, su URL de descarga (tomada del CSV del archivo), filtro, fecha y hash SHA-256. El comando `fetch` descarga lo que esté en el manifiesto y comprueba los hashes; `index` verifica que los ficheros locales coinciden antes de medir. Así cualquiera puede reproducir los mismos datos sin usar el formulario.

### 4.4 Metadatos de cabecera

Claves comprobadas en un fotograma crudo y en su ADP (producto 5456875):

| Dato | Clave | Ejemplo |
|---|---|---|
| Filtro | `FILTER2` (las demás ruedas en `OPEN`) | `Sloan_i` |
| Exposición | `EXPTIME` | 100 s |
| Masa de aire | `AIRMASS` | 1,468 |
| Binning | `CCDSUM` | `2 2` |
| Escala de placa | matriz `CD1_1`, `CD1_2`, … del WCS | 7,066 × 10⁻⁵ grados = 0,254″ por píxel con binning 2×2 |
| Ganancia y ruido de lectura | `GAIN`, `RDNOISE` | 1,9 e⁻/ADU; 4,3 e⁻ |
| Meteorología | `HUMIDITY`, `WINDSPEE`, `WINDDIRE`, `PRESSURE` | 5,6 %; 7,7 m/s; 54°; 780 hPa |
| Telescopio | `ELEVAT`, `AZIMUTH`, `ROTANG`, `AG1FOCUS` | 42,9°; −134,9°; −90,6°; 12,12 |
| Detector | `CCDTEMP` | 160 K |

Diferencias entre crudo y ADP: el crudo es entero de 16 bits (2073 × 2056) y el ADP es de coma flotante (2032 × 1796), recortado y sin las zonas de overscan.

No hay una clave de nivel de saturación ni claves de FWHM o seeing. Cómo detectar estrellas saturadas queda como decisión pendiente (sección 12).

Ningún valor instrumental se escribe a mano en el código si está en la cabecera. Si falta una clave necesaria, el fotograma se marca como "no medible" con el motivo.

## 5. Medidas

### 5.0 Preparación del fotograma crudo

1. Se lee la imagen entera de 16 bits.
2. Se marcan como saturados los píxeles con el valor máximo del conversor (65535 ADU).
3. Se resta la mediana de la región de overscan (`BIASSEC`).
4. Se recorta a `TRIMSEC`, la zona útil del detector. Sus dimensiones coinciden con las del ADP (comprobado en el producto 5456875: `TRIMSEC = [28:2060,230:2026]`, 2033 × 1797 píxeles, frente a 2032 × 1796 del ADP).

Las regiones se leen de la cabecera y se convierten de la notación FITS (base 1, extremos incluidos, x antes que y) a índices de numpy.

**Comprobación cruzada con DRAGO:** en al menos dos fotogramas se medirá también el ADP correspondiente. La FWHM y la elipticidad medianas deben coincidir dentro del 5 % y de 0,02. Si no coinciden, se investiga antes de seguir.

### 5.1 Selección de estrellas

Las medidas se hacen sobre estrellas que cumplan todo lo siguiente:

- Detectadas por encima de 10 σ sobre el fondo.
- Sin píxeles saturados ni marcados como malos.
- Aisladas: ninguna otra fuente detectada a menos de 5 FWHM.
- Lejos del borde: al menos 20 píxeles.
- Compactas: se descartan galaxias y objetos extensos con un criterio de concentración.

El número de estrellas que pasan el filtro se guarda siempre. Si hay menos de 5, el fotograma se marca como "pocas estrellas" y su FWHM no se usa en los agregados.

### 5.2 FWHM

Para cada estrella se ajusta un perfil de Moffat 2D (más realista que una gaussiana para estrellas reales, porque tiene alas más anchas). La FWHM del fotograma es la mediana de las estrellas seleccionadas, con su dispersión robusta (MAD). Se convierte a segundos de arco con la escala de placa de la cabecera, teniendo en cuenta el binning.

### 5.3 Elipticidad

e = 1 − b/a, a partir de los momentos de segundo orden de cada estrella. Mediana por fotograma. Una elipticidad alta y con orientación común en todo el campo suele indicar problemas de seguimiento o guiado; si cambia de una zona a otra, puede indicar problemas ópticos.

### 5.4 Fondo y saturación

- Fondo: mediana con sigma clipping (3 σ) en una rejilla de 8 × 8 zonas y mediana de las zonas, para que el gradiente del viñeteo (no hay flat) no se cuente como ruido. El ruido es la mediana de las desviaciones de las zonas. En campos muy poblados incluye la contribución de estrellas débiles no resueltas (sección 11) y no se usa en ninguna regla.
- Fracción de píxeles por encima del nivel de saturación de la cabecera.

### 5.5 Dependencia con la masa de aire y el filtro

Con todos los fotogramas válidos (los marcados por el control de calidad no entran) se ajusta log(FWHM) frente a log(masa de aire) por filtro, con mínimos cuadrados, y se compara la pendiente con el valor teórico 0,6. Se dan dos ajustes con su intervalo de confianza del 95 %:

- **Todas las noches juntas.** Usa todo el rango de masa de aire, pero mezcla la masa de aire con la turbulencia de cada noche.
- **Dentro de cada noche.** Cada noche tiene su propio nivel y solo cuenta cómo cambia la FWHM con la masa de aire durante la noche. No le afectan las diferencias entre noches, pero sí la evolución de la turbulencia a lo largo de cada una.

No se espera un ajuste perfecto: el objetivo es comprobar si los datos se comportan como predice la física y documentar las desviaciones.

**Longitud de onda.** El cociente de FWHM entre Sloan z y Sloan i se mide con parejas de fotogramas tomados con menos de 10 minutos de diferencia y corregidos al cénit con el exponente 0,6. Así se quita casi todo el cambio de la turbulencia durante la noche, que es mucho mayor que el efecto buscado (un 5 %). El cociente esperado es (λz/λi)^−0,2 con las longitudes de onda centrales de la tabla de imagen de banda ancha de OSIRIS+ en la web del GTC (https://www.gtc.iac.es/instruments/osiris+/osiris+.php, consultada el 2026-11-26): 770,5 nm para Sloan i y 969,5 nm para Sloan z. No están en la cabecera.

Como las cabeceras incluyen la meteorología y el estado del telescopio en cada exposición, el informe muestra también la FWHM corregida al cénit frente a la velocidad y la dirección del viento, la elevación, la posición de foco (`AG1FOCUS`) y la humedad, con la correlación de rangos de Spearman. Junto a cada una se da la correlación de la misma variable con la hora de la noche: si la variable deriva durante la noche, su correlación con la FWHM puede deberse a cualquier otra cosa que también cambie con la hora. Es un análisis exploratorio: con pocas noches no permite separar causas, pero muestra cómo se haría con el histórico completo del telescopio.

## 6. Control de calidad

Reglas configurables en `config.yaml`, con valores iniciales que se ajustarán al ver los datos reales:

| Regla | Condición inicial | Motivo que se registra |
|---|---|---|
| `few_stars` | menos de 5 estrellas útiles | Nubes, desenfoque o campo pobre |
| `high_ellipticity` | elipticidad mediana > 0,20 | Posible problema de guiado o seguimiento |
| `fwhm_outlier` | FWHM > mediana del mismo filtro y noche + 3 MAD | Calidad anómala respecto al resto de la noche |
| `bright_background` | fondo > mediana del filtro + 3 MAD | Luna, crepúsculo o nubes iluminadas |
| `saturation` | más del 2 % de píxeles saturados (0,5 % en el borrador; ver sección 12, punto 9) | Exposición demasiado larga para el campo |
| `unmeasurable` | falta una clave necesaria o falla el ajuste | Motivo técnico concreto |

Cada fotograma recibe una lista de marcas, nunca una nota opaca. Las reglas comparan con la propia noche (mediana y MAD) en lugar de usar solo umbrales fijos, porque las condiciones cambian de una noche a otra.

## 7. Validación

- **Imágenes sintéticas**: estrellas de Moffat con FWHM, elipticidad y fondo conocidos, ruido de Poisson y de lectura. Criterio de aceptación: FWHM recuperada con error menor del 5 % y elipticidad con error menor de 0,02 en el rango habitual (FWHM de 2 a 8 píxeles).
- **Casos límite**: imagen sin estrellas, estrellas saturadas, estrellas en el borde, pares de estrellas muy cercanas.
- **Datos reales**: inspección visual de los fotogramas marcados y de una muestra de los no marcados. Se documenta en el informe cuántos marcados eran problemas reales.

## 8. CLI

```
gtc-iq manifest --archive-csv data/archive_query_2025A_osiris_bbi.csv --program GTCMULTIPLE7B-25A --block 0037 --out data/manifest.csv
gtc-iq manifest ... --block 0001 --out data/manifest.csv --append   # añade otro bloque y conserva los hashes
gtc-iq fetch   --manifest data/manifest.csv --data data/raw      # descarga y comprueba hashes
gtc-iq index   --manifest data/manifest.csv --data data/raw --out results/index.csv  # lee cabeceras
gtc-iq measure --manifest data/manifest.csv --data data/raw --out results/frames.csv \
               --stars results/stars.csv --jobs 8              # medidas por fotograma y por estrella
gtc-iq qc      --frames results/frames.csv --config config.yaml --out results/qc.csv
gtc-iq report  --frames results/frames.csv --qc results/qc.csv --config config.yaml \
               --manifest data/manifest.csv --data data/raw --out reports/
```

El informe (Markdown con gráficos PNG) incluye: tabla por fotograma, FWHM frente a masa de aire por filtro con el ajuste, FWHM y masa de aire a lo largo de cada noche, cociente entre filtros, FWHM frente a las condiciones de la cabecera, histograma de elipticidad, fotogramas marcados con sus motivos y miniaturas, configuración usada, versión del paquete y hash del manifiesto. No lleva la fecha de generación y los PNG se guardan sin metadatos variables: con la misma entrada, los ficheros son idénticos.

## 9. Stack

- Python 3.12, gestionado con `uv`.
- `astropy` (FITS, WCS, estadística robusta, modelado) y `photutils` (detección y momentos).
- `numpy`, `scipy` y `matplotlib`.
- `pydantic` para la configuración y los formatos de resultados; `typer` para la CLI.
- `httpx` para descargar los productos del archivo.
- `pytest`, `ruff` y `mypy` en CI.

## 10. Plan de trabajo

Cada paso termina con tests en verde, se revisa antes de subirse y se anota en `docs/bitacora.md`.

| Paso | Contenido |
|---|---|
| 1 | Especificación, guía de desarrollo (`CONTRIBUTING.md`) y bitácora (sin código) |
| 2 | Estructura, CI, manifiesto a partir del CSV del archivo, comandos `fetch` e `index`, lectura de cabeceras y preparación del crudo (5.0) |
| 3 | Generador de imágenes sintéticas, selección de estrellas y medidas (FWHM, elipticidad, fondo), validadas con sintéticos |
| 4 | Medidas sobre los datos reales y reglas de control de calidad |
| 5 | Análisis frente a masa de aire y filtro, informe y README con "Cómo lo construí" |

## 11. Riesgos

- **Pocos datos útiles**: si en 2025A hay pocas noches con ADP o con varias masas de aire, el análisis del punto 5.5 tendrá poca estadística. Se asume y se muestra el intervalo de la pendiente.
- **Claves de cabecera distintas a las esperadas**: se resuelve en el paso 2 leyendo cabeceras reales antes de escribir código de medida.
- **Campos con muchas galaxias o muy poblados**: el filtro de aislamiento y compacidad puede dejar pocas estrellas. Se registra y se elige otra noche si hace falta.
- **Confundir seeing con calidad entregada**: el informe hablará siempre de "FWHM medida en la imagen", no de "seeing".
- **Ruido del fondo en campos poblados**: en el bloque 0037 el ruido medido con la mitad inferior de la distribución es de 1,5 a 3 veces el esperado por Poisson, también en los ADP con flat. Lo dominan las estrellas débiles no resueltas del plano galáctico. Por eso el ruido se registra, pero ninguna regla depende de él.
- **Estrellas mezcladas**: dos estrellas a menos de unas 1,5 FWHM se detectan como una sola y la regla de aislamiento no puede verlas. Lo mitiga usar la mediana de muchas estrellas por fotograma.

## 12. Decisiones tomadas en la revisión

1. **Entrada: fotogramas crudos, validados contra los ADP.** La primera propuesta era medir sobre los ADP. Al probar la descarga se vio que el archivo solo entrega los ADP en un ZIP por fotograma que incluye además los apilados del bloque: unos 133 MB por fotograma, 7 GB para el bloque. Los crudos pesan 7 MB, traen en la cabecera las regiones de overscan y de recorte, y permiten detectar la saturación directamente. Los ADP se usan para la comprobación cruzada de la sección 5.0.
2. **Perfil de ajuste: Moffat**, guardando también la FWHM gaussiana para comparar.
3. **Noches:** bloque 0037 del 19-20 de julio de 2025 como principal (sección 4.2).
4. **Saturación:** píxeles a 65535 ADU en el crudo (sección 5.0). Se resuelve con la decisión 1.

### Decisiones del paso 3

5. **Elipticidad: del ajuste en lugar de por momentos.** *Decisión tomada: se adopta la propuesta.* La sección 5.3 define la elipticidad por momentos de segundo orden. Medido con estrellas sintéticas, los momentos con ventana gaussiana redonda la subestiman mucho (error de hasta 0,23 para una elipticidad real de 0,3) y no cumplen el criterio de la sección 7 (error < 0,02). La elipticidad del ajuste de Moffat sí lo cumple (error ≤ 0,011 en todo el rango). La del ajuste es la medida principal; la de momentos se guarda solo como referencia.
6. **Límites físicos del ajuste:** alpha de Moffat entre 0,5 y 30 px, beta entre 1,2 y 10, centro a menos de 3 px de la detección y recorte de como mucho 81 × 81 px. Un ajuste que termina en un límite se descarta como `fit_failed`. Motivo: con datos reales, ajustes sin límites divergían (FWHM de 29 px o de 0,05 px) y el recorte crecía sin fin.

### Decisiones del paso 4

7. **Ajuste centrado en la detección y con las vecinas enmascaradas.** *Corrección de un error, no cambia la SPEC.* El punto de partida del ajuste se calculaba con el píxel más brillante del recorte. En el campo del bloque 0037 ese píxel era otra estrella en el 42 % de los recortes, y el ajuste acababa en un límite o, en sintéticos, midiendo la vecina. Ahora el centro inicial y la tolerancia de 3 px (punto 6) se toman de la detección, y se excluyen del ajuste los píxeles a menos de 3 FWHM de otra fuente detectada. De las estrellas que llegan al ajuste, las descartadas bajaron del 71 % al 24 % (medianas de los 52 fotogramas), con 2,5 veces más estrellas por fotograma. La FWHM mediana de cada fotograma cambió como mucho un 1,3 %.
8. **Límite de beta.** *Decisión tomada: se mantiene.* La mayoría de los ajustes que siguen descartándose terminan en beta = 10 (perfil casi gaussiano). Ampliar el límite a 100 en dos fotogramas recuperaría unas 60 a 75 estrellas por fotograma y movería la FWHM mediana un +0,3 %. Por ser un efecto tan pequeño, el punto 6 no cambia.
9. **Umbral de saturación: del 0,5 % al 2 %.** *Decisión tomada.* Con 0,5 % (sección 6) la regla `saturation` marcaba los 18 fotogramas de Sloan i de 100 s (0,92 a 1,03 % de píxeles saturados) y ninguno de Sloan z de 50 s (0,33 a 0,39 %). Es una propiedad del campo (plano galáctico) con esa exposición, no un fallo de los fotogramas: su FWHM y su elipticidad son normales. Una regla que marca todos los fotogramas de un filtro no ayuda a encontrar los dudosos. Se descartaron mantenerlo y convertir la regla en un aviso, porque eso habría añadido un nivel de gravedad que la sección 6 no define. Con el 2 % la regla queda para casos anómalos, como una exposición muy larga o un objeto muy brillante en el campo.

### Decisiones del paso 5

10. **Dos ajustes frente a la masa de aire.** *Decisión tomada.* Con varias noches, un único ajuste mezcla la masa de aire con la turbulencia de cada noche, y uno por noche no tiene rango de masa de aire (como mucho 1,26 a 1,47). Se dan los dos, con su intervalo (sección 5.5). Ninguno separa por sí solo la masa de aire de la turbulencia; con el histórico del telescopio el ajuste dentro de cada noche sería el bueno.
11. **Opciones nuevas en la CLI.** *Decisión tomada.* `manifest --append` para juntar varios bloques en un manifiesto. `report` lleva además `--config` y `--manifest`, porque el informe copia la configuración y el hash del manifiesto (sección 8), y `--data`, opcional, para las miniaturas de los fotogramas marcados.
12. **Longitudes de onda de los filtros.** *Decisión tomada.* No están en la cabecera. Se toman de la tabla de OSIRIS+ de la web del GTC (sección 5.5). El texto de esa página da también valores nominales redondeados (7800 Å y 9250 Å); se usan los de la tabla. Con los nominales el cociente esperado sería 0,967 en vez de 0,955, y no cambia la conclusión.
