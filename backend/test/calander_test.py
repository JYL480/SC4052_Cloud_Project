import os
import datetime
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# We need the calendar read/write scope to create events!
SCOPES = ['https://www.googleapis.com/auth/calendar',
'https://www.googleapis.com/auth/calendar.events'
]

# Using raw string (r"...") to avoid the SyntaxWarning you got in gmail_test!
CREDENTIALS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../client_secret.json'))
TOKEN_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../token.json'))

def main():
    print("Starting authentication flow for Google Calendar...")
    flow = InstalledAppFlow.from_client_secrets_file(
        CREDENTIALS_PATH, SCOPES)
    
    # Using your working port from the Gmail test!
    creds = flow.run_local_server(port=8080)
    
    # Build the Calendar service
    service = build('calendar', 'v3', credentials=creds)
    
    # Call the Calendar API to get the next 5 upcoming events
    now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
    print("\nFetching the upcoming 5 events...")
    events_result = service.events().list(
        calendarId='primary', 
        timeMin=now,
        maxResults=5, 
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    
    events = events_result.get('items', [])
    
    if not events:
        print('No upcoming events found.')
        return
        
    for event in events:
        # Get start time (could be 'dateTime' or just 'date' for all-day events)
        start = event['start'].get('dateTime', event['start'].get('date'))
        print(f"[{start}] - {event['summary']}")

    # --- NEW: Test Event Creation --- 
    print("\n--- Testing Event Creation ---")
    start_time = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)).isoformat()
    end_time = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1, hours=1)).isoformat()
    
    event_body = {
      'summary': "Dummy Test Event",
      'description': "Testing from python script",
      'start': {
        'dateTime': start_time,
        'timeZone': 'UTC',
      },
      'end': {
        'dateTime': end_time,
        'timeZone': 'UTC',
      },
    }
    
    print("Sending create event request...")
    created_event = service.events().insert(calendarId='primary', body=event_body).execute()
    print(f"Success! Created event link: {created_event.get('htmlLink')}")

if __name__ == '__main__':
    main()
