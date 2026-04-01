from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
CREDENTIALS_PATH = ".\client_secret_381149349918-pb1frrplsajjhohm1o9o9pd9bcq7udhq.apps.googleusercontent.com.json"
import os


# Point to the actual client secret JSON file in the root folder


flow = InstalledAppFlow.from_client_secrets_file(
    CREDENTIALS_PATH, SCOPES)

creds = flow.run_local_server(port=8080)

service = build('gmail', 'v1', credentials=creds)

results = service.users().messages().list(userId='me').execute()
messages = results.get('messages', [])

print(messages[:5])