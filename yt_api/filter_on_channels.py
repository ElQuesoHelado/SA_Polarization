"""
Funciones para:
1. Resolver el channel_id a partir de un @handle, username o channel_id directo.
2. Obtener todos los videos de un canal dentro de un rango de fechas,
   usando la uploads playlist (mucho mas barato en cuota que search()).
"""

from googleapiclient.errors import HttpError
from youtube_client import get_youtube_client


def resolver_channel_id(youtube, canal):
    """
    Acepta un channel_id directo (empieza con 'UC'), un @handle, o un username
    legacy, y devuelve el channel_id real.
    """
    canal = canal.strip()

    if canal.startswith("UC"):
        return canal

    if canal.startswith("@"):
        request = youtube.channels().list(part="id", forHandle=canal)
        response = request.execute()
        items = response.get("items", [])
        if items:
            return items[0]["id"]

    # Fallback: intenta como username legacy
    request = youtube.channels().list(part="id", forUsername=canal.lstrip("@"))
    response = request.execute()
    items = response.get("items", [])
    if items:
        return items[0]["id"]

    raise ValueError(f"No se pudo resolver el canal: {canal}")


def obtener_uploads_playlist_id(youtube, channel_id):
    """Devuelve el ID de la playlist 'uploads' (todos los videos subidos) del canal."""
    request = youtube.channels().list(part="contentDetails", id=channel_id)
    response = request.execute()
    items = response.get("items", [])
    if not items:
        raise ValueError(f"Canal no encontrado: {channel_id}")
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def obtener_videos_canal(canal, fecha_inicio, fecha_fin, max_videos=None):
    """
    Obtiene todos los videos de un canal publicados dentro de [fecha_inicio, fecha_fin].

    Args:
        canal (str): channel_id, @handle o username.
        fecha_inicio (str): fecha ISO8601, ej "2026-03-01T00:00:00Z".
        fecha_fin (str): fecha ISO8601, ej "2026-05-01T00:00:00Z".
        max_videos (int|None): limite opcional de videos a traer.

    Returns:
        list[dict]: videos con video_id, titulo, canal, canal_id, publicado.
    """
    youtube = get_youtube_client()
    channel_id = resolver_channel_id(youtube, canal)
    uploads_playlist_id = obtener_uploads_playlist_id(youtube, channel_id)

    videos = []
    next_page_token = None

    try:
        while True:
            request = youtube.playlistItems().list(
                part="snippet",
                playlistId=uploads_playlist_id,
                maxResults=50,
                pageToken=next_page_token,
            )
            response = request.execute()

            for item in response.get("items", []):
                snippet = item["snippet"]
                publicado = snippet["publishedAt"]

                # La uploads playlist viene ordenada del mas reciente al mas antiguo,
                # asi que si ya pasamos la fecha_inicio, podemos cortar la paginacion.
                if publicado < fecha_inicio:
                    return videos

                if fecha_inicio <= publicado <= fecha_fin:
                    videos.append(
                        {
                            "video_id": snippet["resourceId"]["videoId"],
                            "titulo": snippet["title"],
                            "canal": snippet["channelTitle"],
                            "canal_id": channel_id,
                            "publicado": publicado,
                        }
                    )

                    if max_videos and len(videos) >= max_videos:
                        return videos

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

    except HttpError as e:
        print(f"Error al obtener videos del canal {canal}: {e}")

    return videos
