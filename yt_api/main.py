import json
import re
from datetime import datetime, timezone

from search import buscar_videos
from comments import obtener_comentarios


def slugify(texto):
    texto = texto.strip().lower()
    texto = re.sub(r"[^a-z0-9\s-]", "", texto)
    texto = re.sub(r"[\s]+", "_", texto)
    return texto or "query"


def exportar_json(data, nombre_archivo):
    with open(nombre_archivo, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\nExportado a: {nombre_archivo}")


def main():
    query = "rpp elecciones"
    max_videos = 100
    max_comentarios_por_video = 10000

    print(f"Buscando videos para: '{query}'...\n")
    videos = buscar_videos(query, max_resultados=max_videos)

    resultado = {
        "query": query,
        "fecha_extraccion": datetime.now(timezone.utc).isoformat(),
        "cantidad_videos": len(videos),
        "videos": [],
    }

    for video in videos:
        print(f"\n=== {video['titulo']} ({video['video_id']}) ===")
        comentarios = obtener_comentarios(
            video["video_id"], max_resultados=max_comentarios_por_video
        )
        print(f"  {len(comentarios)} comentarios extraidos.")

        resultado["videos"].append(
            {
                "video_id": video["video_id"],
                "titulo": video["titulo"],
                "canal": video["canal"],
                "publicado": video["publicado"],
                "cantidad_comentarios": len(comentarios),
                "comentarios": comentarios,
            }
        )

    nombre_archivo = f"raw_data/{slugify(query)}.json"
    exportar_json(resultado, nombre_archivo)


if __name__ == "__main__":
    main()
