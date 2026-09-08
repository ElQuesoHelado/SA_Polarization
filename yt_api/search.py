from googleapiclient.errors import HttpError
from youtube_client import get_youtube_client


def buscar_videos(query, max_resultados=10):
    """
    Busca videos en YouTube con keyword.

    Args:
        query (str): termino de busqueda.
        max_resultados (int): cantidad maxima de resultados (max 50 por request).

    Returns:
        list[dict]: lista de videos con video_id, titulo y canal.
    """
    youtube = get_youtube_client()
    videos = []

    try:
        request = youtube.search().list(
            part="snippet",
            q=query,
            type="video",
            maxResults=max_resultados,
        )
        response = request.execute()

        for item in response.get("items", []):
            videos.append(
                {
                    "video_id": item["id"]["videoId"],
                    "titulo": item["snippet"]["title"],
                    "canal": item["snippet"]["channelTitle"],
                    "publicado": item["snippet"]["publishedAt"],
                }
            )

    except HttpError as e:
        print(f"Error al buscar videos: {e}")

    return videos


if __name__ == "__main__":
    resultados = buscar_videos("rpp elecciones", max_resultados=20)
    for v in resultados:
        print(f"{v['titulo']} ({v['video_id']}) - {v['canal']}")
