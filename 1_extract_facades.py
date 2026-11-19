"""
1_extract_facades.py
====================
Descarga imágenes de fachadas a nivel de calle desde un proveedor de
imágenes callejeras: Google Street View Static API o Mapillary.

Proveedores
-----------
  * google     (por defecto) Google Street View Static API.
               Requiere GOOGLE_MAPS_API_KEY. Compone la vista exacta:
               size=640x640, fov=80, pitch=10 y heading perpendicular.

  * mapillary  Imágenes colaborativas (CC-BY-SA). Requiere un token gratuito
               (MAPILLARY_TOKEN) de https://www.mapillary.com/developer.
               Busca las fotos ya existentes cerca de cada coordenada y elige
               la que mejor apunta hacia el `heading` solicitado. NO permite
               fijar size/fov/pitch (descarga la miniatura 2048/1024).

Entrada
-------
CSV con columnas `lat`, `lon`, `heading`.
  * lat, lon : coordenadas WGS84 del punto de captura.
  * heading  : orientación en grados (0=N, 90=E, 180=S, 270=O) que apunta
               PERPENDICULAR a la fachada (hacia el edificio).

Salida
------
  * Imágenes `fachada_<lat>_<lon>_<heading>.jpg`.
  * `puntos_descargados.csv`: manifiesto con el estado de cada descarga.

Uso
---
  Google:
      set GOOGLE_MAPS_API_KEY=TU_API_KEY
      python 1_extract_facades.py --provider google --input puntos_ejemplo.csv

  Mapillary:
      set MAPILLARY_TOKEN=TU_TOKEN
      python 1_extract_facades.py --provider mapillary --input puntos_ejemplo.csv

  (También puedes pasar la clave con --api-key)
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

GOOGLE_API_URL = "https://maps.googleapis.com/maps/api/streetview"
MAPILLARY_API_URL = "https://graph.mapillary.com/images"

# Parámetros fijados por el enunciado del prototipo (solo aplican a Google).
DEFAULT_SIZE = "640x640"
DEFAULT_FOV = 80
DEFAULT_PITCH = 10

# Límites de la API de Mapillary (búsqueda por cercanía).
MAPILLARY_RADIO_MAX_M = 50.0
MAPILLARY_LIMIT_MAX = 100

# Google devuelve un JPEG diminuto ("sin cobertura") cuando no existe
# panorámica. Una foto real de 640x640 casi siempre supera este umbral.
MIN_VALID_IMAGE_BYTES = 5_000


def leer_puntos(ruta_csv: Path) -> list[dict]:
    """Lee el CSV de puntos y normaliza los nombres de columna (sin tildes)."""
    puntos: list[dict] = []
    with ruta_csv.open("r", encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        if lector.fieldnames is None:
            raise ValueError(f"No se pudieron leer las columnas de {ruta_csv}")

        columnas = {c.strip().lower(): c for c in lector.fieldnames}
        requeridas = {"lat", "lon", "heading"}
        faltantes = requeridas - set(columnas)
        if faltantes:
            raise ValueError(
                f"El CSV requiere las columnas {sorted(requeridas)}. "
                f"Faltan: {sorted(faltantes)}. "
                f"Columnas encontradas: {sorted(columnas)}"
            )

        for fila in lector:
            try:
                lat = float(fila[columnas["lat"]])
                lon = float(fila[columnas["lon"]])
                heading = float(fila[columnas["heading"]])
            except (TypeError, ValueError, KeyError) as exc:
                print(f"[advertencia] Fila ignorada por valor inválido: {fila} ({exc})")
                continue

            punto = {
                "lat": lat,
                "lon": lon,
                "heading": heading,
                "id": fila.get(columnas.get("id", ""), "") if "id" in columnas else "",
            }
            puntos.append(punto)

    if not puntos:
        raise ValueError(f"No se encontraron puntos válidos en {ruta_csv}")
    return puntos


def nombre_archivo(lat: float, lon: float, heading: float) -> str:
    """Codifica las coordenadas en el nombre de la imagen."""
    return f"fachada_{lat:.6f}_{lon:.6f}_{heading:.0f}.jpg"


# --------------------------------------------------------------------------- #
# Google Street View
# --------------------------------------------------------------------------- #
def descargar_fachada_google(
    api_key: str,
    punto: dict,
    carpeta_salida: Path,
    size: str,
    fov: int,
    pitch: int,
    reintentos: int,
    demora: float,
) -> tuple[str, str, str]:
    """
    Descarga una imagen compuesta de Google Street View.

    Devuelve (ruta_archivo, estado, detalle) con estado en
    'ok', 'sin_cobertura' o 'error'.
    """
    params = {
        "location": f"{punto['lat']},{punto['lon']}",
        "heading": int(round(punto["heading"])) % 360,
        "size": size,
        "fov": fov,
        "pitch": pitch,
        "key": api_key,
    }
    url = f"{GOOGLE_API_URL}?{urlencode(params)}"
    archivo = carpeta_salida / nombre_archivo(punto["lat"], punto["lon"], punto["heading"])

    ultimo_error = ""
    for intento in range(1, reintentos + 1):
        try:
            respuesta = requests.get(url, timeout=30)
            if respuesta.status_code == 200:
                contenido = respuesta.content
                if len(contenido) < MIN_VALID_IMAGE_BYTES:
                    return str(archivo), "sin_cobertura", "posible imagen sin cobertura Street View"
                archivo.write_bytes(contenido)
                return str(archivo), "ok", f"{len(contenido)} bytes"

            ultimo_error = f"HTTP {respuesta.status_code}"
            if respuesta.status_code in (403, 429):
                break  # errores de credenciales/cuota no se reintentan

        except requests.RequestException as exc:
            ultimo_error = str(exc)

        if intento < reintentos:
            time.sleep(demora)

    return str(archivo), "error", ultimo_error


# --------------------------------------------------------------------------- #
# Mapillary
# --------------------------------------------------------------------------- #
def _diff_angular(a: float, b: float) -> float:
    """Diferencia circular entre dos ángulos en grados (0-180)."""
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def _distancia_cuadrada(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia euclidiana aproximada en grados (suficiente para desempatar)."""
    return (lat1 - lat2) ** 2 + (lon1 - lon2) ** 2


def _seleccionar_imagen(datos: list[dict], lat: float, lon: float, heading: float) -> dict:
    """Elige la imagen que mejor apunta hacia `heading` y está más cerca del punto."""
    def clave(item: dict) -> tuple[float, float]:
        geom = item.get("geometry") or {}
        coords = geom.get("coordinates") or [None, None]
        try:
            ilon, ilat = float(coords[0]), float(coords[1])
        except (TypeError, ValueError, IndexError):
            ilon, ilat = lon, lat

        try:
            ang = float(item.get("compass_angle"))
        except (TypeError, ValueError):
            ang = None

        diff = _diff_angular(ang, heading) if ang is not None else 180.0
        return (diff, _distancia_cuadrada(lat, lon, ilat, ilon))

    return min(datos, key=clave)


def descargar_fachada_mapillary(
    token: str,
    punto: dict,
    carpeta_salida: Path,
    radio_m: float,
    max_results: int,
    reintentos: int,
    demora: float,
) -> tuple[str, str, str]:
    """
    Busca y descarga la imagen de Mapillary más adecuada para el punto.

    Devuelve (ruta_archivo, estado, detalle) con estado en
    'ok', 'sin_cobertura' o 'error'.
    """
    lat, lon, heading = punto["lat"], punto["lon"], punto["heading"]
    radio_m = min(max(radio_m, 1.0), MAPILLARY_RADIO_MAX_M)
    max_results = min(max(max_results, 1), MAPILLARY_LIMIT_MAX)

    params = {
        "access_token": token,
        "fields": "id,geometry,compass_angle,thumb_1024_url,thumb_2048_url",
        "lat": f"{lat:.7f}",
        "lng": f"{lon:.7f}",
        "radius": radio_m,
        "limit": max_results,
    }
    url = f"{MAPILLARY_API_URL}?{urlencode(params)}"
    archivo = carpeta_salida / nombre_archivo(lat, lon, heading)

    ultimo_error = ""
    for intento in range(1, reintentos + 1):
        try:
            respuesta = requests.get(url, timeout=30)
            if respuesta.status_code == 200:
                datos = respuesta.json().get("data", [])
                if not datos:
                    return str(archivo), "sin_cobertura", f"sin imágenes en {radio_m:.0f} m"

                mejor = _seleccionar_imagen(datos, lat, lon, heading)
                img_url = mejor.get("thumb_2048_url") or mejor.get("thumb_1024_url")
                if not img_url:
                    return str(archivo), "error", "sin URL de miniatura en el resultado"

                img = requests.get(img_url, timeout=60)
                if img.status_code != 200:
                    return str(archivo), "error", f"HTTP {img.status_code} al bajar la miniatura"
                if len(img.content) < MIN_VALID_IMAGE_BYTES:
                    return str(archivo), "sin_cobertura", "miniatura vacía"

                archivo.write_bytes(img.content)
                detalle = f"mapillary:{mejor.get('id')} compass={mejor.get('compass_angle')}"
                return str(archivo), "ok", detalle

            ultimo_error = f"HTTP {respuesta.status_code}"
            if respuesta.status_code in (401, 403):
                return str(archivo), "error", f"HTTP {respuesta.status_code} (token inválido o sin permiso)"

        except requests.RequestException as exc:
            ultimo_error = str(exc)

        if intento < reintentos:
            time.sleep(demora)

    return str(archivo), "error", ultimo_error


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Descarga fachadas desde Google Street View o Mapillary."
    )
    parser.add_argument("--provider", choices=["google", "mapillary"], default="google",
                        help="Proveedor de imágenes callejeras (default: google).")
    parser.add_argument("--input", type=Path, default="puntos_ejemplo.csv",
                        help="CSV con columnas lat, lon, heading (y opcional id).")
    parser.add_argument("--output", type=Path, default="fachadas",
                        help="Carpeta donde se guardan las imágenes.")
    parser.add_argument("--api-key", default=None,
                        help="Clave/token del proveedor (si no, usa variable de entorno).")
    # Solo Google
    parser.add_argument("--size", default=DEFAULT_SIZE, help="Tamaño de la imagen (640x640).")
    parser.add_argument("--fov", type=int, default=DEFAULT_FOV, help="Campo de visión horizontal.")
    parser.add_argument("--pitch", type=int, default=DEFAULT_PITCH, help="Elevación de la cámara.")
    # Solo Mapillary
    parser.add_argument("--radius", type=float, default=25.0,
                        help="Radio de búsqueda en metros (Mapillary, máx. 50).")
    parser.add_argument("--max-results", type=int, default=20,
                        help="Máximo de imágenes por consulta (Mapillary, máx. 100).")
    parser.add_argument("--retries", type=int, default=2, help="Reintentos por descarga fallida.")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Segundos de espera entre descargas (cortesía de cuota).")
    args = parser.parse_args()

    env_var = "GOOGLE_MAPS_API_KEY" if args.provider == "google" else "MAPILLARY_TOKEN"
    clave = args.api_key or os.environ.get(env_var)
    if not clave:
        print(f"[error] Falta la credencial del proveedor '{args.provider}'.")
        if args.provider == "google":
            print("  Windows: set GOOGLE_MAPS_API_KEY=TU_API_KEY")
            print("  Linux/Colab: export GOOGLE_MAPS_API_KEY=TU_API_KEY")
        else:
            print("  Obtén un token gratuito en https://www.mapillary.com/developer")
            print("  Windows: set MAPILLARY_TOKEN=TU_TOKEN")
            print("  Linux/Colab: export MAPILLARY_TOKEN=TU_TOKEN")
        print("  O pásala con: --api-key")
        sys.exit(1)

    if not args.input.exists():
        print(f"[error] No existe el archivo de puntos: {args.input}")
        sys.exit(1)

    args.output.mkdir(parents=True, exist_ok=True)
    puntos = leer_puntos(args.input)
    print(f"[info] Proveedor: {args.provider} | {len(puntos)} punto(s) -> {args.output.resolve()}")

    manifiesto: list[dict] = []
    total_ok = 0
    for i, punto in enumerate(puntos, 1):
        if args.provider == "google":
            ruta, estado, detalle = descargar_fachada_google(
                api_key=clave, punto=punto, carpeta_salida=args.output,
                size=args.size, fov=args.fov, pitch=args.pitch,
                reintentos=args.retries, demora=args.delay,
            )
        else:
            ruta, estado, detalle = descargar_fachada_mapillary(
                token=clave, punto=punto, carpeta_salida=args.output,
                radio_m=args.radius, max_results=args.max_results,
                reintentos=args.retries, demora=args.delay,
            )

        etiqueta = punto.get("id") or f"punto_{i}"
        print(f"[{i}/{len(puntos)}] {etiqueta} ({punto['lat']},{punto['lon']}) -> {estado}: {detalle}")
        if estado == "ok":
            total_ok += 1

        manifiesto.append({
            "id": etiqueta,
            "lat": punto["lat"],
            "lon": punto["lon"],
            "heading": punto["heading"],
            "provider": args.provider,
            "ruta_imagen": ruta,
            "estado": estado,
            "detalle": detalle,
        })

        if i < len(puntos):
            time.sleep(args.delay)

    ruta_manifiesto = Path("puntos_descargados.csv")
    with ruta_manifiesto.open("w", encoding="utf-8", newline="") as f:
        campos = ["id", "lat", "lon", "heading", "provider", "ruta_imagen", "estado", "detalle"]
        escritor = csv.DictWriter(f, fieldnames=campos)
        escritor.writeheader()
        escritor.writerows(manifiesto)

    print(f"[info] Descarga finalizada: {total_ok}/{len(puntos)} imágenes válidas.")
    print(f"[info] Manifiesto guardado en {ruta_manifiesto}")


if __name__ == "__main__":
    main()
