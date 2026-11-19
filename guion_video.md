# Guion de video — Prototipo de Visión por Computador para Renovación Urbana en Bogotá

> **Duración estimada:** 4:30 – 5:00 min · **Formato:** narración en off + pantalla (grabación de pantalla del visor y diapositivas) · **Audiencia:** académica.
>
> ⚠️ Antes de grabar: verifica las cifras (19 fachadas / 11-7-1) contra tu informe final y ajústalas si cambiaste algo.

---

## ESCENA 1 — Apertura (0:00 – 0:30)

**[VISUAL]** Título del proyecto sobre una foto de fachadas de Bogotá (por ejemplo, una de tu `banco_img`). Música suave de fondo.

**[NARRACIÓN]**
"¿Qué potencial de renovación urbana tiene un barrio? Responder esa pregunta exige, primero, conocer el estado de sus edificaciones. En Bogotá, ese diagnóstico suele hacerse mediante inspecciones en campo: costosas, lentas y difíciles de escalar. En este proyecto proponemos una alternativa: usar visión por computador para estimar el deterioro de las fachadas a partir de imágenes a nivel de calle."

---

## ESCENA 2 — El problema (0:30 – 1:00)

**[VISUAL]** Mapa de Bogotá con las localidades de Santa Fe y Teusaquillo resaltadas; luego, 2–3 fotos de fachadas en distinto estado (una deteriorada, una en buen estado).

**[NARRACIÓN]**
"El Plan de Ordenamiento Territorial de Bogotá requiere, como insumo, un inventario del estado físico del parque edificado. Sin embargo, recorrer la ciudad inspeccionando fachada por fachada no es viable a escala. La pregunta que guía este trabajo es: ¿podemos automatizar ese diagnóstico con un prototipo rápido, de bajo costo y sin entrenar modelos desde cero?"

---

## ESCENA 3 — Objetivo y enfoque (1:00 – 1:30)

**[VISUAL]** Diagrama simple de los 3 módulos: (1) extracción de imágenes → (2) evaluación con CLIP → (3) visualización en mapa. Flechas entre ellos.

**[NARRACIÓN]**
"Nuestro objetivo fue construir, en una semana, un prototipo académico que clasificara fachadas según su deterioro. La clave técnica fue usar clasificación *zero-shot* con el modelo CLIP: en lugar de entrenar un clasificador, describimos cada nivel de deterioro en lenguaje natural y dejamos que el modelo empareje cada imagen con la descripción más adecuada. El sistema se organiza en tres módulos independientes: extracción, evaluación y visualización."

---

## ESCENA 4 — Metodología: extracción de imágenes (1:30 – 2:00)

**[VISUAL]** Código de `1_extract_facades.py` o un diagrama mostrando coordenadas (lat, lon) + ángulo `heading` perpendicular a la fachada.

**[NARRACIÓN]**
"El primer módulo toma una lista de coordenadas y un ángulo de orientación que apunta perpendicular a la fachada, no a lo largo de la vía. Con esas referencias se obtienen las imágenes, ya sea desde Google Street View o desde Mapillary, y las coordenadas quedan codificadas en el nombre de cada archivo para garantizar su trazabilidad geográfica."

---

## ESCENA 5 — Metodología: evaluación del deterioro (2:00 – 2:45)

**[VISUAL]** La fórmula del índice centrada en pantalla: **D = Σ pᵢ · aᵢ**, con las tres categorías y sus anclas (Consolidado = 15, Mejoramiento = 55, Renovación Prioritaria = 90).

**[NARRACIÓN]**
"El segundo módulo asigna a cada fachada un índice de deterioro entre cero y cien. Para ello, cada categoría se describe con frases en inglés —porque el modelo CLIP es monolingüe— y se calcula la probabilidad de que la imagen corresponda a cada una. El índice es el promedio ponderado de tres valores representativos, o anclas: quince para una fachada consolidada, cincuenta y cinco para un mejoramiento integral y noventa para una renovación prioritaria. Así, el resultado no es solo una etiqueta, sino una medida continua que refleja la confianza y la ambigüedad del modelo."

---

## ESCENA 6 — Metodología: visualización (2:45 – 3:15)

**[VISUAL]** Grabación real del visor: el mapa con los marcadores de colores, y un clic que abre el popup con la foto y el diagnóstico.

**[NARRACIÓN]**
"Finalmente, el tercer módulo despliega los resultados en un mapa interactivo construido con Streamlit y Folium. Cada marcador se colorea según la categoría: rojo para renovación prioritaria, amarillo para mejoramiento integral y verde para consolidado. Al hacer clic, se abre un popup con la fotografía de la fachada y su diagnóstico, lo que permite verificar visualmente cada resultado. El visor puede ejecutarse en local o desde Google Colab."

---

## ESCENA 7 — Resultados (3:15 – 4:00)

**[VISUAL]** Tabla de distribución (11 Consolidado / 7 Mejoramiento / 1 Prioritaria) + el mapa completo con los marcadores.

**[NARRACIÓN]**
"Sobre la muestra piloto de diecinueve fachadas en Santa Fe y Teusaquillo, la distribución obtenida fue: once consolidadas, siete con mejoramiento integral y una de renovación prioritaria. Esta composición es coherente con un tejido urbano mixto, donde conviven edificaciones en buen estado con casos puntuales de deterioro severo. Los resultados demuestran que el enfoque sin entrenamiento es viable para un diagnóstico preliminar."

---

## ESCENA 8 — Conclusiones y trabajo futuro (4:00 – 4:30)

**[VISUAL]** Lista de bullets: viabilidad · limitaciones (cobertura, umbrales) · trabajo futuro (fine-tuning, IDECA).

**[NARRACIÓN]**
"Como conclusión, el prototipo confirma que es factible construir, en una semana y sin entrenar modelos desde cero, una herramienta que estima el potencial de renovación urbana a partir de las fachadas. Entre sus limitaciones están la cobertura irregular de las fuentes de imagen y la sensibilidad de los umbrales de clasificación. Como trabajo futuro se plantea entrenar un clasificador específico del dominio, integrar capas oficiales de catastro y ordenamiento territorial, y validar los resultados en campo."

---

## ESCENA 9 — Cierre (4:30 – 4:45)

**[VISUAL]** Título del proyecto + "Gracias" + nombre y programa.

**[NARRACIÓN]**
"Gracias por su atención."

---

## Tips de grabación

1. **Graba la pantalla del visor** (OBS Studio o la grabadora de Windows, `Win + G`) para la Escena 6: es la parte más demostrativa.
2. **Usa diapositivas** para la fórmula (Escena 5) y la tabla de resultados (Escena 7); se leen mejor que el código.
3. **Narra por secciones** y une después: es más fácil regrabar una escena sola.
4. **Cuidado con los nombres**: pronuncia "CLIP" como /klip/ y "zero-shot" como /síro-shot/.
5. Si tu video debe ser más corto (2–3 min), recorta las Escenas 2 y 8; mantén intactas 1, 5, 6 y 7.
