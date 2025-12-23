import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# =========================
# CẤU HÌNH
# =========================
SCOPES = ['https://www.googleapis.com/auth/drive.file']

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

OAUTH_CLIENT_FILE = os.path.join(BASE_DIR, 'oauth_client.json')
TOKEN_FILE = os.path.join(BASE_DIR, 'token.json')

PARENT_FOLDER_ID = '1tmoIEEcozT5KZkUN_uBmGDwnF5U1-YHf'


def get_drive_service():
    """
    BE dùng token.json để upload tự động.
    Token hết hạn sẽ tự refresh bằng refresh_token.
    """
    if not os.path.exists(TOKEN_FILE):
        raise Exception(
            "Chưa có token.json. Hãy chạy generate_token.py để OAuth 1 lần."
        )

    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
        else:
            raise Exception("Token không hợp lệ, cần OAuth lại.")

    return build('drive', 'v3', credentials=creds)


def upload_file_to_drive(file_obj):
    service = get_drive_service()

    file_metadata = {
        'name': getattr(file_obj, "name", "upload_file"),
        'parents': [PARENT_FOLDER_ID],
    }

    media = MediaIoBaseUpload(
        file_obj,
        mimetype=getattr(file_obj, "content_type", "application/octet-stream"),
        resumable=True
    )

    # 1) Upload
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()

    file_id = file.get('id')

    # 2) Public read
    try:
        service.permissions().create(
            fileId=file_id,
            body={'type': 'anyone', 'role': 'reader'},
            fields='id'
        ).execute()
    except Exception as e:
        print(f"Lỗi khi cấp quyền public: {e}")

    return file.get('webViewLink')

def delete_file_from_drive(file_id):
    """
    Hàm xóa file trên Google Drive dựa vào File ID
    """
    try:
        service = get_drive_service()
        service.files().delete(fileId=file_id).execute()
        return True
    except Exception as e:
        print(f"Lỗi khi xóa file trên Drive: {e}")
        return False