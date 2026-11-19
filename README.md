# Prototipo académico — Renovación urbana en Bogotá por análisis de fachadas

Prototipo de Visión por Computador que evalúa el potencial de renovación urbana
analizando fachadas a nivel de calle, **sin entrenar modelos desde cero**. Usa:

- **Google Street View Static API** o **Mapillary** para obtener las fachadas.
- **CLIP** (`openai/clip-vit-large-patch14`) para clasificación zero-shot del
  deterioro arquitectónico.
- **Streamlit + Folium** para visualizar el diagnóstico sobre un mapa.

## Estructura

| Archivo | Función |
|---|---|
| `1_extract_facades.py` | Descarga fachadas desde Street View o Mapillary (`--provider`) y guarda las coordenadas en el nombre. |
| `2_evaluate_facades.py` | Clasifica cada fachada con CLIP y exporta `diagnostico_facades.csv`. |
| `3_app_visor.py` | Visor web con mapa, marcadores de colores y popups con la foto. |
| `requirements.txt` | Dependencias del proyecto. |
| `puntos_ejemplo.csv` | Puntos de ejemplo (reemplázalos por los de tu estudio). |

## Instalación

### Windows / VS Code

```powershell
python -m venv .venv
.\.venv\Scripts\Activate
pip install -r requirements.txt
```

> En Windows, instala la CPU de PyTorch si no tienes GPU:
> `pip install torch --index-url https://download.pytorch.org/whl/cpu`

### Google Colab

```python
!pip install -r requirements.txt
# torch/transformers suelen estar ya instalados en Colab
```

## Flujo de ejecución (3 pasos)

### 1. Obtener la credencial del proveedor

**Google (Street View Static API):**
1. Entra a [Google Cloud Console](https://console.cloud.google.com/).
2. Habilita la **Street View Static API**.
3. Crea una credencial (API key) y expórtala:
   - Windows: `set GOOGLE_MAPS_API_KEY=TU_API_KEY`
   - Colab/Linux: `os.environ["GOOGLE_MAPS_API_KEY"] = "TU_API_KEY"`

**Mapillary (alternativa libre, CC-BY-SA):**
1. Crea una cuenta gratuita en [mapillary.com/developer](https://www.mapillary.com/developer).
2. Genera un token y expórtalo:
   - Windows: `set MAPILLARY_TOKEN=TU_TOKEN`
   - Colab/Linux: `os.environ["MAPILLARY_TOKEN"] = "TU_TOKEN"`

### 2. Descargar fachadas

```bash
# Google Street View (compone la vista: heading/fov/pitch)
python 1_extract_facades.py --provider google --input puntos_ejemplo.csv --output fachadas

# Mapillary (busca fotos existentes cerca de cada punto)
python 1_extract_facades.py --provider mapillary --input puntos_ejemplo.csv --output fachadas
```

Genera `fachadas/fachada_<lat>_<lon>_<heading>.jpg` y `puntos_descargados.csv`.

> Mapillary **no** permite fijar `size/fov/pitch`: selecciona la foto existente
> más cercana a cada punto y que mejor apunta hacia el `heading`. Ajusta el radio
> con `--radius` (máximo 50 m).

### 3. Evaluar fachadas

```bash
# Modelo grande (mejor precisión)
python 2_evaluate_facades.py --images fachadas

# Modelo base (más rápido en CPU/Colab)
python 2_evaluate_facades.py --images fachadas --model openai/clip-vit-base-patch32
```

Genera `diagnostico_facades.csv` con: `latitud, longitud, categoria, score,
ruta_imagen, clase_clip, confianza`.

### 4. Visualizar

```bash
streamlit run 3_app_visor.py
```

## Índice de deterioro y categorías

El **score (0–100)** es el promedio ponderado de los "anclas" de cada clase
(15 / 55 / 90) según las probabilidades zero-shot de CLIP:

| Categoría | Rango de score | Color en el mapa |
|---|---|---|
| Renovación Prioritaria | ≥ 70 | Rojo |
| Mejoramiento Integral | 40 – 70 | Amarillo |
| Consolidado | < 40 | Verde |

## Usar un banco de imágenes existente (sin coordenadas en el nombre)

La carpeta `banco_img/` contiene 73 fotos de fachadas de Bogotá con nombres
descriptivos (no codifican coordenadas). Para evaluarlas, crea un manifiesto CSV
con columnas `ruta_imagen, lat, lon` y pásalo al paso 2:

```bash
python 2_evaluate_facades.py --images banco_img --manifest manifiesto_banco.csv
```

## Notas

- Los prompts de CLIP están en **inglés** porque `openai/clip-vit-large-patch14`
  es monolingüe; las categorías se entregan en español.
- `heading` debe apuntar **perpendicular a la fachada** (hacia el edificio), no
  a lo largo de la vía.
- El script de extracción detecta imágenes "sin cobertura" de Street View por su
  tamaño (umbral de 5 KB) y las marca como `sin_cobertura`.
- Con `--provider mapillary` el token se lee de `MAPILLARY_TOKEN` y se envía como
  parámetro `access_token` a `graph.mapillary.com` (radio ≤ 50 m). Las imágenes
  de Mapillary son CC-BY-SA: conserva la atribución.
- El polígono de estudio por defecto cubre las localidades de **Santa Fe** y
  **Teusaquillo**; edítalo en `3_app_visor.py` (constante `POLIGONO_ESTUDIO`).
- Para un VLM alternativo, sustituye la carga de CLIP en `2_evaluate_facades.py`
  por un pipeline de `transformers` (p. ej. `Salesforce/blip-image-captioning-base`)
  y mapea la descripción generada a las categorías.

## Reconocimientos

Este proyecto fue desarrollado con el apoyo de un asistente de IA generativa
(DeepSeek / DeepSeek Harness) para la generación y depuración de código y de
documentación. El diseño, la verificación de resultados y las decisiones
finales corresponden al autor.
