import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/drive.file']

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_FILE = os.path.join(BASE_DIR, 'oauth_client.json')
TOKEN_FILE = os.path.join(BASE_DIR, 'token.json')

flow = InstalledAppFlow.from_client_secrets_file(CLIENT_FILE, SCOPES)
creds = flow.run_local_server(port=0)

with open(TOKEN_FILE, "w", encoding="utf-8") as f:
    f.write(creds.to_json())

print("Done. token.json created!")
