# Guía de desarrollo

Normas para trabajar en este repositorio.

## Qué es

`gtc-image-quality` mide la calidad de imagen de los fotogramas de OSIRIS+ del Gran Telescopio Canarias (GTC): FWHM, elipticidad, fondo del cielo y saturación. Marca los fotogramas dudosos con reglas explicables y relaciona la calidad con la masa de aire y el filtro. La especificación completa está en `docs/SPEC.md`. Léela antes de proponer cambios y no implementes nada que no esté ahí sin preguntar.

## Arquitectura

Hecho en los pasos 2 y 3:

```
src/gtc_iq/
  archive.py     # Lee el CSV exportado por el formulario del archivo y selecciona un bloque
  manifest.py    # Manifiesto de productos (URL y SHA-256) y cálculo de hashes
  fetch.py       # Descarga con httpx; congela el hash en la primera descarga
  headers.py     # Claves de cabecera de SPEC 4.4 y secciones FITS -> índices numpy
  preprocess.py  # Resta de overscan, recorte a TRIMSEC y máscara de saturación (SPEC 5.0)
  synthetic.py   # Estrellas de Moffat con FWHM y elipticidad conocidas (paso 3)
  stars.py       # Detección y selección de estrellas útiles (paso 3)
  measure.py     # Ajuste de Moffat, elipticidad, fondo; resumen por fotograma (paso 3)
  cli.py         # Typer: manifest, fetch, index
```

Previsto en los pasos siguientes:

```
src/gtc_iq/
  config.py      # Configuración pydantic (umbrales de QC, selección de estrellas)
  qc.py          # Reglas de control de calidad con motivos (SPEC 6)
  analysis.py    # Ajuste FWHM frente a masa de aire y filtro (SPEC 5.5)
  report.py      # Informe Markdown y gráficos
tests/
data/            # CSV del archivo y manifest.csv versionados; los FITS (raw/, sample/) no
```

Las medidas y las reglas son funciones puras sobre arrays de numpy y modelos pydantic. Toda la E/S (FITS, CSV, red, gráficos) vive en `archive.py`, `manifest.py`, `fetch.py`, `report.py` y `cli.py`.

## Comandos

```bash
uv sync                       # instalar dependencias
uv run pytest                 # tests
uv run ruff check .           # lint
uv run ruff format .          # formato
uv run mypy src tests         # tipos (modo estricto)
uv run gtc-iq --help          # CLI
```

Antes de dar un paso por terminado deben pasar los cuatro: pytest, ruff check, ruff format --check y mypy. Son los mismos que ejecuta CI.

## Convenciones

- Código, nombres, tests y mensajes de commit en inglés. Documentación (`docs/`, README) en español.
- Type hints en todo el código de `src/`.
- Comentarios solo cuando explican un porqué que no se deduce del código.
- Sin emojis en código, commits ni documentación.
- Unidades explícitas en los nombres cuando haya ambigüedad: `fwhm_px`, `fwhm_arcsec`, `background_adu`.

## Datos y dominio

- Ningún valor instrumental (escala de placa, saturación, binning, ganancia) se escribe a mano si está en la cabecera FITS. Si falta, el fotograma se marca como `unmeasurable` con el motivo.
- Los FITS de `data/raw/` son de solo lectura: nunca se modifican ni se sobrescriben.
- Se habla de "FWHM medida en la imagen", nunca de "seeing", salvo al citar la teoría.
- Cualquier dato del GTC o del archivo citado en la documentación debe venir de una fuente comprobable (web del GTC, cabeceras reales). Nunca de memoria.

## Tests

- Los tests no hacen llamadas de red ni dependen de los FITS reales: usan imágenes sintéticas de `synthetic.py` o FITS mínimos creados en el propio test.
- Cada medida se valida con casos de respuesta conocida (SPEC 7), incluidos los bordes: sin estrellas, saturadas, en el borde y pares cercanos.
- Si corriges un bug, añade primero un test que lo reproduzca.
- No cambies una tolerancia de test para que pase. Si la medida no cumple el criterio de la SPEC, dilo y espera una decisión.

## Commits

- Pequeños y de un solo propósito, con Conventional Commits: `feat:`, `fix:`, `test:`, `docs:`, `ci:`, `refactor:`, `chore:`.
- No añadas líneas de coautoría ni de herramientas generadoras en los mensajes.
- No hagas `git push` ni crees el repositorio remoto: lo hace el autor después de revisar.

## Límites

- No añadas dependencias que no estén en la SPEC (sección 9) sin preguntar.
- No cambies la definición de una medida o de una regla para que un test pase.
- No descargues datos fuera del manifiesto: la selección de datos la decide el autor y queda en `data/manifest.csv`.
