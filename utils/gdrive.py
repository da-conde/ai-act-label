import io
import json
import pandas as pd
import streamlit as st

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload


# -----------------------------------------------------------
# Google Drive Client (wird aus st.secrets geladen)
# -----------------------------------------------------------

def get_drive_service():
    """
    Initialisiert einen Google Drive API Client mit den
    Service-Account-Credentials aus Streamlit Secrets.
    """
    creds_info = st.secrets["gcp_service_account"]

    creds = Credentials.from_service_account_info(
        creds_info,
        scopes=["https://www.googleapis.com/auth/drive"],
    )

    return build("drive", "v3", credentials=creds)


# -----------------------------------------------------------
# JSON LADEN
# -----------------------------------------------------------

def load_json_from_drive(file_id: str) -> dict:
    """
    Lädt eine JSON-Datei von Google Drive über ihre File-ID.
    Gibt ein Python-Dict zurück.
    """
    service = get_drive_service()
    request = service.files().get_media(fileId=file_id)

    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        status, done = downloader.next_chunk()

    fh.seek(0)
    return json.loads(fh.read().decode("utf-8"))


# -----------------------------------------------------------
# JSON SPEICHERN
# -----------------------------------------------------------

def save_json_to_drive(data: dict, file_id: str):
    """
    Speichert ein Dict als JSON-Datei auf Google Drive.
    Überschreibt die Datei mit der angegebenen File-ID.
    """
    service = get_drive_service()

    buf = io.BytesIO(json.dumps(data, indent=2).encode("utf-8"))
    media = MediaIoBaseUpload(buf, mimetype="application/json", resumable=True)

    service.files().update(
        fileId=file_id,
        media_body=media,
    ).execute()


# -----------------------------------------------------------
# CSV LADEN
# -----------------------------------------------------------

def load_csv_from_drive(file_id: str) -> pd.DataFrame:
    """
    Lädt eine CSV-Datei von Google Drive.
    Gibt ein Pandas DataFrame zurück.
    """
    service = get_drive_service()
    request = service.files().get_media(fileId=file_id)

    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        status, done = downloader.next_chunk()

    fh.seek(0)
    return pd.read_csv(fh)


# -----------------------------------------------------------
# CSV SPEICHERN
# -----------------------------------------------------------

def save_csv_to_drive(df: pd.DataFrame, file_id: str):
    """
    Speichert ein DataFrame als CSV-Datei zurück nach Google Drive.
    """
    service = get_drive_service()

    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    media = MediaIoBaseUpload(buf, mimetype="text/csv", resumable=True)

    service.files().update(
        fileId=file_id,
        media_body=media,
    ).execute()