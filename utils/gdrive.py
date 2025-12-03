import io
import json
from typing import List, Dict, Optional

import pandas as pd
import streamlit as st

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload


# -----------------------------------------------------------
# Google Drive Client
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
# Basis-Download-Helfer
# -----------------------------------------------------------

def _download_bytes(file_id: str) -> bytes:
    service = get_drive_service()
    request = service.files().get_media(fileId=file_id)

    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False

    while not done:
        status, done = downloader.next_chunk()

    fh.seek(0)
    return fh.read()


# -----------------------------------------------------------
# JSON LADEN/SPEICHERN (per ID)
# -----------------------------------------------------------

def load_json_from_drive(file_id: str) -> dict:
    data = _download_bytes(file_id)
    return json.loads(data.decode("utf-8"))


def save_json_to_drive(data: dict, file_id: str):
    service = get_drive_service()

    buf = io.BytesIO(json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))
    media = MediaIoBaseUpload(buf, mimetype="application/json", resumable=True)

    service.files().update(
        fileId=file_id,
        media_body=media,
    ).execute()


# -----------------------------------------------------------
# CSV LADEN/SPEICHERN (per ID)
# -----------------------------------------------------------

def load_csv_from_drive(file_id: str) -> pd.DataFrame:
    data = _download_bytes(file_id)
    return pd.read_csv(io.BytesIO(data))


def save_csv_to_drive(df: pd.DataFrame, file_id: str):
    service = get_drive_service()

    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    media = MediaIoBaseUpload(buf, mimetype="text/csv", resumable=True)

    service.files().update(
        fileId=file_id,
        media_body=media,
    ).execute()


# -----------------------------------------------------------
# TEXT LADEN (per ID)
# -----------------------------------------------------------

def load_text_from_drive(file_id: str, encoding: str = "utf-8") -> str:
    data = _download_bytes(file_id)
    return data.decode(encoding, errors="ignore")


# -----------------------------------------------------------
# Ordner-Funktionen
# -----------------------------------------------------------

def list_files_in_folder(folder_id: str, mime_type: Optional[str] = None) -> List[Dict]:
    """
    Listet alle Dateien in einem Ordner (nicht rekursiv).
    Optional nach MIME-Type filtern (z. B. 'application/vnd.google-apps.folder').
    """
    service = get_drive_service()
    files: List[Dict] = []
    page_token = None

    while True:
        q = f"'{folder_id}' in parents and trashed = false"
        if mime_type:
            q += f" and mimeType = '{mime_type}'"

        response = service.files().list(
            q=q,
            spaces="drive",
            fields="nextPageToken, files(id, name, mimeType)",
            pageToken=page_token,
        ).execute()

        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return files


def load_csv_from_drive_by_name(folder_id: str, filename: str) -> pd.DataFrame:
    """
    Lädt eine CSV-Datei aus einem Ordner anhand ihres Dateinamens.
    Falls die Datei nicht existiert, wird ein leeres DataFrame zurückgegeben.
    """
    service = get_drive_service()

    q = (
        f"'{folder_id}' in parents and trashed = false "
        f"and name = '{filename}'"
    )

    response = service.files().list(
        q=q,
        spaces="drive",
        fields="files(id, name)",
    ).execute()

    files = response.get("files", [])
    if not files:
        return pd.DataFrame()

    file_id = files[0]["id"]
    return load_csv_from_drive(file_id)


def save_csv_to_drive_by_name(df: pd.DataFrame, folder_id: str, filename: str):
    """
    Speichert ein DataFrame als CSV in einen Ordner.
    Falls eine Datei mit `filename` existiert, wird sie überschrieben.
    Sonst wird sie neu erstellt.
    """
    service = get_drive_service()

    # Erst prüfen, ob es die Datei schon gibt
    q = (
        f"'{folder_id}' in parents and trashed = false "
        f"and name = '{filename}'"
    )
    response = service.files().list(
        q=q,
        spaces="drive",
        fields="files(id, name)",
    ).execute()

    files = response.get("files", [])
    existing_id: Optional[str] = files[0]["id"] if files else None

    # Inhalt vorbereiten
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    media = MediaIoBaseUpload(buf, mimetype="text/csv", resumable=True)

    if existing_id:
        # Update
        service.files().update(
            fileId=existing_id,
            media_body=media,
        ).execute()
    else:
        # Neu anlegen
        file_metadata = {
            "name": filename,
            "parents": [folder_id],
            "mimeType": "text/csv",
        }
        service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id",
        ).execute()