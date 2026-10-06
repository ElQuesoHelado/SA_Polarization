"""
Extrae videos y comentarios de dos piscinas de canales de YouTube
(pro-izquierda / pro-derecha) dentro del rango de fechas de las
elecciones peruanas 2026 (antes, durante, despues).

Exporta un JSON por piscina, compatible con preprocess.py:
{
    "pool": "izquierda",
    "fecha_extraccion": "...",
    "videos": [
        {
            "video_id": "...",
            "titulo": "...",
            "canal": "...",
            "canal_id": "...",
            "publicado": "...",
            "etapa": "antes" | "durante" | "despues",
            "cantidad_comentarios": N,
            "comentarios": [ ... ]
        }
    ]
}
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from filter_on_channels import obtener_videos_canal
from comments import obtener_comentarios

CANALES = {
    # "izquierda": [
    #     "@pavelyachay",
    #     "@leonmoya",
    #     "@canalYAAAAA",
    #     "@curwen",
    #     "@unanchatvoficial",
    # ],
    "derecha": [
        "@LaRoroNetworkOficial",
        "@todogoodpe",
        "@PaoloBenzaR",
        "@mirinconcitofavorito176",
        "@LibertandoPeru",
    ],
}

# ---------------------------------------------------------------------------
# Fechas de cada etapa electoral (ISO8601, en UTC)
# ---------------------------------------------------------------------------
ETAPAS = {
    "antes": ("2026-01-01T00:00:00Z", "2026-03-31T23:59:59Z"),
    "durante": ("2026-04-01T00:00:00Z", "2026-04-30T23:59:59Z"),
    "despues": ("2026-05-01T00:00:00Z", "2026-06-30T23:59:59Z"),
}

MAX_COMENTARIOS_POR_VIDEO = 5000

OUTPUT_DIR = Path("raw_data")
OUTPUT_DIR.mkdir(exist_ok=True)


def etapa_de_fecha(fecha_publicado):
    """Dado un publishedAt, determina a que etapa electoral pertenece."""
    for etapa, (inicio, fin) in ETAPAS.items():
        if inicio <= fecha_publicado <= fin:
            return etapa
    return None


def procesar_piscina(nombre_piscina, canales):
    rango_global_inicio = min(inicio for inicio, _ in ETAPAS.values())
    rango_global_fin = max(fin for _, fin in ETAPAS.values())

    resultado = {
        "pool": nombre_piscina,
        "fecha_extraccion": datetime.now(timezone.utc).isoformat(),
        "canales": canales,
        "videos": [],
    }

    for canal in canales:
        print(f"\n[{nombre_piscina}] Procesando canal: {canal}")
        try:
            videos = obtener_videos_canal(
                canal, rango_global_inicio, rango_global_fin, 200
            )
        except ValueError as e:
            print(f"  [AVISO] {e} - se omite este canal")
            continue

        print(f"  {len(videos)} videos encontrados en el rango de fechas.")

        for video in videos:
            etapa = etapa_de_fecha(video["publicado"])
            print(f"  - {video['titulo']} ({video['video_id']}) [{etapa}]")

            comentarios = obtener_comentarios(
                video["video_id"], max_resultados=MAX_COMENTARIOS_POR_VIDEO
            )
            print(f"    {len(comentarios)} comentarios extraidos.")

            resultado["videos"].append(
                {
                    "video_id": video["video_id"],
                    "titulo": video["titulo"],
                    "canal": video["canal"],
                    "canal_id": video["canal_id"],
                    "publicado": video["publicado"],
                    "etapa": etapa,
                    "cantidad_comentarios": len(comentarios),
                    "comentarios": comentarios,
                }
            )

    return resultado


def main():
    for nombre_piscina, canales in CANALES.items():
        resultado = procesar_piscina(nombre_piscina, canales)

        nombre_archivo = OUTPUT_DIR / f"{nombre_piscina}.json"
        with open(nombre_archivo, "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)

        print(f"\n[{nombre_piscina}] Exportado a: {nombre_archivo}")
        print(f"[{nombre_piscina}] Total videos: {len(resultado['videos'])}")
        total_comentarios = sum(v["cantidad_comentarios"] for v in resultado["videos"])
        print(f"[{nombre_piscina}] Total comentarios: {total_comentarios}")


if __name__ == "__main__":
    main()
