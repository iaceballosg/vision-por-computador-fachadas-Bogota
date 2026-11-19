"""
2_evaluate_facades.py
=====================
Clasificación zero-shot del estado de cada fachada con CLIP y cálculo de un
índice de deterioro (0-100).

Modelo por defecto: openai/clip-vit-large-patch14 (Hugging Face).
Las etiquetas de deterioro se describen con prompts en INGLÉS porque ese CLIP
es monolingüe; la categoría final se entrega en español.

Categorías / umbrales del índice de deterioro (0 = impecable, 100 = ruina):
  * score <  40           -> "Consolidado"
  * 40 <= score < 70      -> "Mejoramiento Integral"
  * score >= 70           -> "Renovación Prioritaria"

Salida
------
  `diagnostico_facades.csv` con: latitud, longitud, categoria, score,
  ruta_imagen, clase_clip, confianza.

Uso
---
  # Modelo grande (mejor precisión, más lento)
  python 2_evaluate_facades.py --images fachadas

  # Modelo base (rápido en CPU / Colab)
  python 2_evaluate_facades.py --model openai/clip-vit-base-patch32

  # Evaluar un banco de imágenes existente SIN coordenadas en el nombre
  # (p.ej. la carpeta banco_img): proporciona un manifiesto CSV con
  # columnas `ruta_imagen, lat, lon`.
  python 2_evaluate_facades.py --images banco_img --manifest manifiesto_banco.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from PIL import Image

# --------------------------------------------------------------------------- #
# Configuración de categorías (prompts en inglés para CLIP monolingüe)
# --------------------------------------------------------------------------- #
CATEGORIAS: list[dict] = [
    {
        "nombre": "Consolidado",
        "anchor": 15,  # deterioro representativo de esta clase
        "prompts": [
            "a well maintained building facade in good condition with fresh paint and no visible damage",
            "a clean renovated building facade without cracks or humidity stains",
        ],
    },
    {
        "nombre": "Mejoramiento Integral",
        "anchor": 55,
        "prompts": [
            "a building facade with moderate deterioration, peeling paint and small cracks, needs maintenance",
            "an aging building facade with faded paint and minor visible damage",
        ],
    },
    {
        "nombre": "Renovación Prioritaria",
        "anchor": 90,
        "prompts": [
            "a severely deteriorated building facade with large cracks, humidity stains and abandonment",
            "a crumbling ruined building facade with structural damage and broken windows",
        ],
    },
]

UMBRAL_MEJORAMIENTO = 40.0
UMBRAL_PRIORITARIA = 70.0

# fachada_<lat>_<lon>_<heading>.jpg  (también .jpeg/.png)
PATRON_ARCHIVO = re.compile(
    r"fachada_(-?\d+(?:\.\d+)?)_(-?\d+(?:\.\d+)?)_(-?\d+)\.(?:jpg|jpeg|png)",
    re.IGNORECASE,
)

EXTENSIONES = ("*.jpg", "*.jpeg", "*.png")


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def detectar_dispositivo(override: str | None) -> str:
    """Selecciona cuda / mps / cpu según disponibilidad."""
    if override:
        return override
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def listar_imagenes(carpeta: Path) -> list[Path]:
    """Devuelve las imágenes de la carpeta, ordenadas y sin duplicados."""
    imagenes = []
    for patron in EXTENSIONES:
        imagenes.extend(carpeta.glob(patron))
    # Deduplica por ruta resuelta conservando el orden.
    vistos = set()
    unicos = []
    for img in sorted(imagenes):
        clave = img.resolve()
        if clave not in vistos:
            vistos.add(clave)
            unicos.append(img)
    return unicos


def extraer_coordenadas(nombre: str) -> tuple[float, float, float] | None:
    """Recupera (lat, lon, heading) del nombre del archivo, o None."""
    m = PATRON_ARCHIVO.search(nombre)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2)), float(m.group(3))


def leer_manifiesto(ruta_csv: Path) -> dict[str, tuple[float, float]]:
    """
    Lee un manifiesto opcional que mapea 'ruta_imagen' -> (lat, lon).
    Útil para bancos de imágenes existentes cuyos nombres no codifican
    coordenadas (por ejemplo, la carpeta banco_img).

    Se indexa por la ruta completa Y por el nombre del archivo, de modo que
    la coincidencia funcione aunque cambie el nombre de la carpeta.
    """
    mapeo: dict[str, tuple[float, float]] = {}
    with ruta_csv.open("r", encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        columnas = {c.strip().lower(): c for c in (lector.fieldnames or [])}
        for fila in lector:
            ruta = fila[columnas.get("ruta_imagen", "ruta_imagen")].strip()
            lat = float(fila[columnas.get("lat", "lat")])
            lon = float(fila[columnas.get("lon", "lon")])
            mapeo[ruta] = (lat, lon)
            mapeo[Path(ruta).name] = (lat, lon)  # fallback por nombre de archivo
    return mapeo


# --------------------------------------------------------------------------- #
# Modelo CLIP
# --------------------------------------------------------------------------- #
def cargar_modelo(nombre_modelo: str, dispositivo: str):
    """Carga CLIP desde Hugging Face y lo pone en modo evaluación."""
    from transformers import CLIPModel, CLIPProcessor

    print(f"[info] Cargando modelo '{nombre_modelo}' en '{dispositivo}' ...")
    modelo = CLIPModel.from_pretrained(nombre_modelo).to(dispositivo)
    modelo.eval()
    procesador = CLIPProcessor.from_pretrained(nombre_modelo)
    return modelo, procesador


def evaluar_imagen(modelo, procesador, dispositivo: str, ruta_imagen: Path) -> dict:
    """
    Devuelve un dict con 'score' (0-100), 'clase_clip' y 'confianza'.
    El score se calcula como el promedio ponderado de los anchors de cada
    categoría usando las probabilidades zero-shot de CLIP.
    """
    imagen = Image.open(ruta_imagen).convert("RGB")

    prompts = [p for cat in CATEGORIAS for p in cat["prompts"]]
    anchors = np.array([cat["anchor"] for cat in CATEGORIAS], dtype=float)
    nombres = [cat["nombre"] for cat in CATEGORIAS]

    entradas = procesador(text=prompts, images=imagen, return_tensors="pt", padding=True)
    entradas = {k: v.to(dispositivo) for k, v in entradas.items()}

    with torch.no_grad():
        salidas = modelo(**entradas)

    probs_todas = salidas.logits_per_image.softmax(dim=-1)[0].cpu().numpy()

    # Agrega por categoría tomando el prompt más probable dentro de cada una.
    probs_cat = []
    inicio = 0
    for cat in CATEGORIAS:
        fin = inicio + len(cat["prompts"])
        probs_cat.append(float(np.max(probs_todas[inicio:fin])))
        inicio = fin
    probs_cat = np.array(probs_cat, dtype=float)
    probs_cat /= probs_cat.sum()  # normaliza a 1

    score = float(np.sum(probs_cat * anchors))
    idx_top = int(np.argmax(probs_cat))

    return {
        "score": score,
        "clase_clip": nombres[idx_top],
        "confianza": float(probs_cat[idx_top]),
    }


def categoria_por_score(score: float) -> str:
    if score >= UMBRAL_PRIORITARIA:
        return "Renovación Prioritaria"
    if score >= UMBRAL_MEJORAMIENTO:
        return "Mejoramiento Integral"
    return "Consolidado"


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evalúa fachadas con CLIP zero-shot y exporta el diagnóstico CSV."
    )
    parser.add_argument("--images", type=Path, default="fachadas",
                        help="Carpeta con las imágenes de fachadas.")
    parser.add_argument("--output", type=Path, default="diagnostico_facades.csv",
                        help="CSV de salida con el diagnóstico.")
    parser.add_argument("--model", default="openai/clip-vit-large-patch14",
                        help="Modelo CLIP de Hugging Face.")
    parser.add_argument("--device", default=None,
                        help="Dispositivo: cuda, mps o cpu (auto por defecto).")
    parser.add_argument("--manifest", type=Path, default=None,
                        help="CSV opcional con columnas ruta_imagen, lat, lon "
                             "para imágenes sin coordenadas en el nombre.")
    args = parser.parse_args()

    if not args.images.exists() or not args.images.is_dir():
        print(f"[error] La carpeta de imágenes no existe: {args.images}")
        sys.exit(1)

    imagenes = listar_imagenes(args.images)
    if not imagenes:
        print(f"[error] No se encontraron imágenes (.jpg/.jpeg/.png) en {args.images}")
        sys.exit(1)

    mapeo_manifesto = leer_manifiesto(args.manifest) if args.manifest else {}

    dispositivo = detectar_dispositivo(args.device)
    modelo, procesador = cargar_modelo(args.model, dispositivo)

    filas: list[dict] = []
    errores = 0
    for i, img in enumerate(imagenes, 1):
        # 1) Coordenadas: manifiesto -> nombre de archivo -> sin dato.
        clave = img.as_posix()
        if clave in mapeo_manifesto:
            lat, lon = mapeo_manifesto[clave]
        elif img.name in mapeo_manifesto:
            lat, lon = mapeo_manifesto[img.name]
        else:
            coords = extraer_coordenadas(img.name)
            if coords is None:
                print(f"[{i}/{len(imagenes)}] {img.name} -> sin coordenadas (se omite).")
                continue
            lat, lon, _heading = coords

        # 2) Evaluación.
        try:
            resultado = evaluar_imagen(modelo, procesador, dispositivo, img)
            score = round(resultado["score"], 1)
            categoria = categoria_por_score(resultado["score"])
            print(
                f"[{i}/{len(imagenes)}] {img.name} -> "
                f"{categoria} (score {score:.1f})"
            )
            filas.append({
                "latitud": lat,
                "longitud": lon,
                "categoria": categoria,
                "score": score,
                "ruta_imagen": img.as_posix(),
                "clase_clip": resultado["clase_clip"],
                "confianza": round(resultado["confianza"], 3),
            })
        except Exception as exc:  # imagen corrupta o fallo de inferencia
            errores += 1
            print(f"[{i}/{len(imagenes)}] {img.name} -> no evaluable: {exc}")
            filas.append({
                "latitud": lat,
                "longitud": lon,
                "categoria": "No evaluable",
                "score": None,
                "ruta_imagen": img.as_posix(),
                "clase_clip": "",
                "confianza": None,
            })

    if not filas:
        print("[error] No se pudo evaluar ninguna imagen.")
        sys.exit(1)

    df = pd.DataFrame(filas)
    df.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"[info] Diagnóstico exportado a {args.output} ({len(df)} filas).")

    resumen = df["categoria"].value_counts()
    print("[info] Resumen por categoría:")
    for cat, n in resumen.items():
        print(f"   - {cat}: {n}")

    if errores:
        print(f"[info] {errores} imagen(es) no evaluables marcadas como 'No evaluable'.")


if __name__ == "__main__":
    main()
