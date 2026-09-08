import os
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")

if not API_KEY:
    raise ValueError("No se encontro YOUTUBE_API_KEY")

API_SERVICE_NAME = "youtube"
API_VERSION = "v3"


def get_youtube_client():
    return build(API_SERVICE_NAME, API_VERSION, developerKey=API_KEY)
