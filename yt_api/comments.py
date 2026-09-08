from googleapiclient.errors import HttpError
from youtube_client import get_youtube_client


def obtener_comentarios(video_id, max_resultados=100):
    """
    Obtiene comentarios (top-level) de un video, manejando paginacion.

    Args:
        video_id (str): ID del video de YouTube.
        max_resultados (int): cantidad maxima de comentarios a traer en total.

    Returns:
        list[dict]: lista de comentarios con autor, texto, likes y fecha.
    """
    youtube = get_youtube_client()
    comentarios = []
    next_page_token = None

    try:
        while len(comentarios) < max_resultados:
            request = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=min(100, max_resultados - len(comentarios)),
                pageToken=next_page_token,
                textFormat="plainText",
            )
            response = request.execute()

            for item in response.get("items", []):
                top_comment = item["snippet"]["topLevelComment"]
                snippet = top_comment["snippet"]
                comentarios.append(
                    {
                        "comment_id": top_comment["id"],
                        "autor": snippet["authorDisplayName"],
                        "autor_canal_id": snippet.get("authorChannelId", {}).get(
                            "value"
                        ),
                        "texto": snippet["textDisplay"],
                        "likes": snippet["likeCount"],
                        "fecha_publicacion": snippet["publishedAt"],
                        "fecha_actualizacion": snippet["updatedAt"],
                        "cantidad_respuestas": item["snippet"].get(
                            "totalReplyCount", 0
                        ),
                    }
                )

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

    except HttpError as e:
        print(f"Error al obtener comentarios del video {video_id}: {e}")

    return comentarios


if __name__ == "__main__":
    video_id_ejemplo = "dQw4w9WgXcQ"
    resultados = obtener_comentarios(video_id_ejemplo, max_resultados=20)
    for c in resultados:
        print(f"{c['autor']}: {c['texto']} ({c['likes']} likes)")
