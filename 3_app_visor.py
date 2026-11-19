"""
3_app_visor.py
==============
Visor web (Streamlit + Folium) del diagnóstico de fachadas.

Lee `diagnostico_facades.csv`, dibuja un mapa centrado en el polígono de
estudio en Bogotá y coloca marcadores de colores según la categoría:
  * Rojo    -> Renovación Prioritaria
  * Amarillo-> Mejoramiento Integral
  * Verde   -> Consolidado
  * Gris    -> No evaluable

Al hacer clic en un marcador se muestra un popup con la foto de la fachada y
su diagnóstico.

Uso
---
  streamlit run 3_app_visor.py
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #
# Polígono de estudio (caja envolvente) que cubre las localidades de
# Santa Fe y Teusaquillo, Bogotá. Reemplázalo por el polígono real de tu
# análisis si necesitas el límite administrativo exacto.
POLIGONO_ESTUDIO = [
    [4.6600, -74.0800],  # NW - Teusaquillo norte (Calle 63 x Av. 68)
    [4.6600, -74.0400],  # NE - límite oriental (Cerros Orientales)
    [4.5700, -74.0400],  # SE - Santa Fe sur (Cerros Orientales)
    [4.5700, -74.0800],  # SW - Santa Fe occidente
]

COLORES = {
    "Renovación Prioritaria": "#e45756",  # rojo
    "Mejoramiento Integral": "#f5c542",   # amarillo
    "Consolidado": "#54a24b",             # verde
    "No evaluable": "#8c8c8c",            # gris
}

COLUMNAS_REQUERIDAS = {"latitud", "longitud", "categoria", "score", "ruta_imagen"}


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def cargar_datos(ruta_csv: str, archivo_subido) -> tuple[pd.DataFrame, Path]:
    """Carga el CSV (desde subida o desde disco) y valida sus columnas."""
    if archivo_subido is not None:
        df = pd.read_csv(archivo_subido)
        directorio = Path.cwd()
    else:
        ruta = Path(ruta_csv)
        if not ruta.exists():
            st.error(
                f"No se encontró `{ruta_csv}`. Ejecuta primero "
                "`2_evaluate_facades.py` para generarlo."
            )
            st.stop()
        df = pd.read_csv(ruta)
        directorio = ruta.parent

    if not COLUMNAS_REQUERIDAS.issubset(df.columns):
        st.error(
            f"El CSV debe contener las columnas {sorted(COLUMNAS_REQUERIDAS)}. "
            f"Columnas encontradas: {sorted(df.columns)}"
        )
        st.stop()
    return df, directorio


def resolver_ruta_imagen(ruta: str, directorio: Path) -> Path:
    """Resuelve la ruta de la imagen probando varios puntos de partida."""
    p = Path(ruta)
    candidatos = [p]
    if not p.is_absolute():
        candidatos += [Path.cwd() / p, directorio / p]
    for c in candidatos:
        if c.exists():
            return c
    return p


def imagen_a_base64(ruta: Path) -> str | None:
    """Codifica la imagen (reducida) en base64 para aligerar el mapa."""
    if not ruta.exists():
        return None
    from PIL import Image

    img = Image.open(ruta).convert("RGB")
    img.thumbnail((320, 320))  # miniaturas ligeras para los popups
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def formatear_score(score) -> str:
    if pd.isna(score):
        return "N/D"
    return f"{float(score):.0f}/100"


def html_popup(fila, directorio: Path) -> str:
    """Construye el HTML del popup con la foto y el diagnóstico."""
    ruta = resolver_ruta_imagen(fila["ruta_imagen"], directorio)
    img = imagen_a_base64(ruta)
    color = COLORES.get(fila["categoria"], "#8c8c8c")

    if img:
        bloque_imagen = f'<img src="{img}" style="width:100%;border-radius:6px;"/>'
    else:
        bloque_imagen = (
            f'<p style="color:#888;">No se encontró la imagen:<br>'
            f'{fila["ruta_imagen"]}</p>'
        )

    return f"""
    <div style="width:320px;font-family:'Segoe UI',Arial,sans-serif;">
      {bloque_imagen}
      <h4 style="margin:8px 0 4px;color:{color};">{fila['categoria']}</h4>
      <p style="margin:2px 0;">Deterioro: <b>{formatear_score(fila['score'])}</b></p>
      <p style="margin:2px 0;color:#555;">
        ({fila['latitud']:.5f}, {fila['longitud']:.5f})
      </p>
    </div>
    """


def construir_mapa(df: pd.DataFrame, directorio: Path, mostrar_poligono: bool = True) -> folium.Map:
    """Construye el mapa con el polígono de estudio y los marcadores."""
    centro = [float(df["latitud"].mean()), float(df["longitud"].mean())]
    mapa = folium.Map(location=centro, zoom_start=12, tiles="OpenStreetMap")

    if mostrar_poligono:
        folium.Polygon(
            POLIGONO_ESTUDIO,
            color="#1f77b4",
            weight=2,
            fill=True,
            fill_opacity=0.08,
            tooltip="Polígono de estudio (Santa Fe + Teusaquillo)",
        ).add_to(mapa)

    for _, fila in df.iterrows():
        color = COLORES.get(fila["categoria"], "#8c8c8c")
        folium.CircleMarker(
            location=[float(fila["latitud"]), float(fila["longitud"])],
            radius=7,
            color="#333333",
            weight=1,
            fill=True,
            fill_color=color,
            fill_opacity=0.9,
            popup=folium.Popup(html_popup(fila, directorio), max_width=340),
            tooltip=fila["categoria"],
        ).add_to(mapa)

    mapa.fit_bounds(mapa.get_bounds())
    return mapa


def leyenda_html() -> str:
    filas = "".join(
        f'<div style="margin:2px 0;">'
        f'<span style="display:inline-block;width:12px;height:12px;'
        f'border-radius:50%;background:{color};"></span> {nombre}'
        f'</div>'
        for nombre, color in COLORES.items()
    )
    return (
        '<div style="position:fixed;bottom:40px;left:12px;z-index:9999;'
        'background:rgba(255,255,255,0.92);padding:8px 12px;border-radius:8px;'
        'font-family:\'Segoe UI\',Arial,sans-serif;font-size:13px;'
        'box-shadow:0 1px 4px rgba(0,0,0,0.3);">'
        f'<b>Leyenda</b>{filas}</div>'
    )


# --------------------------------------------------------------------------- #
# Aplicación
# --------------------------------------------------------------------------- #
def main() -> None:
    st.set_page_config(page_title="Visor de fachadas - Bogotá", layout="wide")
    st.title("Visor de renovación urbana — fachadas de Bogotá")
    st.caption(
        "Prototipo académico de Visión por Computador. Marcadores: "
        "rojo = Renovación Prioritaria, amarillo = Mejoramiento Integral, "
        "verde = Consolidado."
    )

    with st.sidebar:
        st.header("Datos")
        archivo_subido = st.file_uploader("Subir diagnóstico CSV", type=["csv"])
        ruta_csv = st.text_input(
            "Ruta del CSV (si no subes archivo)", value="diagnostico_facades.csv"
        )
        mostrar_poligono = st.checkbox("Mostrar polígono de estudio", value=True)

    df, directorio = cargar_datos(ruta_csv, archivo_subido)

    # Métricas resumidas.
    total = len(df)
    conteos = df["categoria"].value_counts()
    cols = st.columns(4)
    cols[0].metric("Fachadas evaluadas", total)
    cols[1].metric("Renovación Prioritaria", int(conteos.get("Renovación Prioritaria", 0)))
    cols[2].metric("Mejoramiento Integral", int(conteos.get("Mejoramiento Integral", 0)))
    cols[3].metric("Consolidado", int(conteos.get("Consolidado", 0)))

    mapa = construir_mapa(df, directorio, mostrar_poligono=mostrar_poligono)
    mapa.get_root().html.add_child(folium.Element(leyenda_html()))

    datos_clic = st_folium(
        mapa,
        width=1100,
        height=700,
        key="mapa_fachadas",
        returned_objects=["last_object_clicked"],
    )

    # Detalle en la barra lateral al hacer clic (además del popup del mapa).
    if datos_clic and datos_clic.get("last_object_clicked"):
        clic = datos_clic["last_object_clicked"]
        lat_c = clic.get("lat")
        lon_c = clic.get("lng")
        if lat_c is not None and lon_c is not None:
            dist = (df["latitud"] - lat_c) ** 2 + (df["longitud"] - lon_c) ** 2
            fila = df.loc[dist.idxmin()]
            with st.sidebar:
                st.subheader("Fachada seleccionada")
                ruta = resolver_ruta_imagen(fila["ruta_imagen"], directorio)
                if ruta.exists():
                    st.image(str(ruta), use_container_width=True)
                st.markdown(f"**Categoría:** {fila['categoria']}")
                st.markdown(f"**Deterioro:** {formatear_score(fila['score'])}")
                st.markdown(
                    f"**Coordenadas:** ({fila['latitud']:.5f}, {fila['longitud']:.5f})"
                )


if __name__ == "__main__":
    main()
