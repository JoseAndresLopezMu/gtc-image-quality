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

Para ampliar el rango de masa de aire en el análisis 5.5 se añadirán, si el tiempo lo permite, bloques de otras noches del mismo CSV: `GRB250314A` (1,51 a 1,71), `250215A` (1,85 a 2,03) y `250704a` del 29 de julio (1,04 a 1,05).

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

- Fondo: mediana con sigma clipping (3 σ) y ruido como desviación robusta.
- Fracción de píxeles por encima del nivel de saturación de la cabecera.

### 5.5 Dependencia con la masa de aire y el filtro

Con todos los fotogramas válidos se ajusta log(FWHM) frente a log(masa de aire) por filtro y se compara la pendiente con el valor teórico 0,6. No se espera un ajuste perfecto: el objetivo es comprobar si los datos se comportan como predice la física y documentar las desviaciones.

Como las cabeceras incluyen la meteorología y el estado del telescopio en cada exposición, el informe mostrará también la FWHM frente a la velocidad y la dirección del viento, la elevación y la posición de foco (`AG1FOCUS`). Es un análisis exploratorio: con una o pocas noches no permite separar causas, pero muestra cómo se haría con el histórico completo del telescopio.

## 6. Control de calidad

Reglas configurables en `config.yaml`, con valores iniciales que se ajustarán al ver los datos reales:

| Regla | Condición inicial | Motivo que se registra |
|---|---|---|
| `few_stars` | menos de 5 estrellas útiles | Nubes, desenfoque o campo pobre |
| `high_ellipticity` | elipticidad mediana > 0,20 | Posible problema de guiado o seguimiento |
| `fwhm_outlier` | FWHM > mediana del mismo filtro y noche + 3 MAD | Calidad anómala respecto al resto de la noche |
| `bright_background` | fondo > mediana del filtro + 3 MAD | Luna, crepúsculo o nubes iluminadas |
| `saturation` | más del 0,5 % de píxeles saturados | Exposición demasiado larga para el campo |
| `unmeasurable` | falta una clave necesaria o falla el ajuste | Motivo técnico concreto |

Cada fotograma recibe una lista de marcas, nunca una nota opaca. Las reglas comparan con la propia noche (mediana y MAD) en lugar de usar solo umbrales fijos, porque las condiciones cambian de una noche a otra.

## 7. Validación

- **Imágenes sintéticas**: estrellas de Moffat con FWHM, elipticidad y fondo conocidos, ruido de Poisson y de lectura. Criterio de aceptación: FWHM recuperada con error menor del 5 % y elipticidad con error menor de 0,02 en el rango habitual (FWHM de 2 a 8 píxeles).
- **Casos límite**: imagen sin estrellas, estrellas saturadas, estrellas en el borde, pares de estrellas muy cercanas.
- **Datos reales**: inspección visual de los fotogramas marcados y de una muestra de los no marcados. Se documenta en el informe cuántos marcados eran problemas reales.

## 8. CLI

```
gtc-iq manifest --archive-csv data/archive_query_2025A_osiris_bbi.csv --program GTCMULTIPLE7B-25A --block 0037 --out data/manifest.csv
gtc-iq fetch   --manifest data/manifest.csv --data data/raw      # descarga y comprueba hashes
gtc-iq index   --manifest data/manifest.csv --data data/raw --out results/index.csv  # lee cabeceras
gtc-iq measure --data data/raw --out results/frames.csv       # medidas por fotograma
gtc-iq qc      --frames results/frames.csv --config config.yaml --out results/qc.csv
gtc-iq report  --frames results/frames.csv --qc results/qc.csv --out reports/
```

El informe (Markdown con gráficos PNG) incluye: tabla por fotograma, FWHM frente a masa de aire por filtro con el ajuste, histograma de elipticidad, fotogramas marcados con sus motivos y miniaturas, configuración usada, versión del paquete y hash del manifiesto.

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
| 1 | Especificación, `CLAUDE.md` y bitácora (sin código) |
| 2 | Estructura, CI, manifiesto a partir del CSV del archivo, comandos `fetch` e `index`, lectura de cabeceras y preparación del crudo (5.0) |
| 3 | Generador de imágenes sintéticas, selección de estrellas y medidas (FWHM, elipticidad, fondo), validadas con sintéticos |
| 4 | Medidas sobre los datos reales y reglas de control de calidad |
| 5 | Análisis frente a masa de aire y filtro, informe y README con "Cómo lo construí" |

## 11. Riesgos

- **Pocos datos útiles**: si en 2025A hay pocas noches con ADP o con varias masas de aire, el análisis del punto 5.5 tendrá poca estadística. Se asume y se muestra el intervalo de la pendiente.
- **Claves de cabecera distintas a las esperadas**: se resuelve en el paso 2 leyendo cabeceras reales antes de escribir código de medida.
- **Campos con muchas galaxias o muy poblados**: el filtro de aislamiento y compacidad puede dejar pocas estrellas. Se registra y se elige otra noche si hace falta.
- **Confundir seeing con calidad entregada**: el informe hablará siempre de "FWHM medida en la imagen", no de "seeing".
- **Estrellas mezcladas**: dos estrellas a menos de unas 1,5 FWHM se detectan como una sola y la regla de aislamiento no puede verlas. Lo mitiga usar la mediana de muchas estrellas por fotograma.

## 12. Decisiones tomadas en la revisión

1. **Entrada: fotogramas crudos, validados contra los ADP.** La primera propuesta era medir sobre los ADP. Al probar la descarga se vio que el archivo solo entrega los ADP en un ZIP por fotograma que incluye además los apilados del bloque: unos 133 MB por fotograma, 7 GB para el bloque. Los crudos pesan 7 MB, traen en la cabecera las regiones de overscan y de recorte, y permiten detectar la saturación directamente. Los ADP se usan para la comprobación cruzada de la sección 5.0.
2. **Perfil de ajuste: Moffat**, guardando también la FWHM gaussiana para comparar.
3. **Noches:** bloque 0037 del 19-20 de julio de 2025 como principal (sección 4.2).
4. **Saturación:** píxeles a 65535 ADU en el crudo (sección 5.0). Se resuelve con la decisión 1.

### Pendiente de decisión del autor (paso 3)

5. **Elipticidad: del ajuste en lugar de por momentos.** La sección 5.3 define la elipticidad por momentos de segundo orden. Medido con estrellas sintéticas, los momentos con ventana gaussiana redonda la subestiman mucho (error de hasta 0,23 para una elipticidad real de 0,3) y no cumplen el criterio de la sección 7 (error < 0,02). La elipticidad del ajuste de Moffat sí lo cumple (error ≤ 0,011 en todo el rango). Propuesta: usar la del ajuste como medida principal y guardar la de momentos solo como referencia. El código ya lo hace así y es reversible.
6. **Límites físicos del ajuste:** alpha de Moffat entre 0,5 y 30 px, beta entre 1,2 y 10, centro a menos de 3 px de la detección y recorte de como mucho 81 × 81 px. Un ajuste que termina en un límite se descarta como `fit_failed`. Motivo: con datos reales, ajustes sin límites divergían (FWHM de 29 px o de 0,05 px) y el recorte crecía sin fin.
