import assemblyai as aai
import time
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


API_KEY = "YOUR KEY"

CLIENT_FILE = "credentials.json"
DOCUMENT_ID = "DOCUMENT ID"
SCOPES = ["https://www.googleapis.com/auth/documents"]


def update_google_docs(content):
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    try:
        service = build("docs", "v1", credentials=creds)

        requests = [
            {
                'insertText' : {
                    'text' : content,
                    'endOfSegmentLocation' : {}
                }
            }
        ]
        result = service.documents().batchUpdate(
            documentId = DOCUMENT_ID,
            body = {'requests':requests}
        ).execute()

        # Retrieve the documents contents from the Docs service.
        #document = service.documents().get(documentId=DOCUMENT_ID).execute()
    except HttpError as err:
        print(err)




def lemur_call(transcript, prev_responses):
    lemur = aai.Lemur()
    input_text = transcript

    prompt = f"""
    You are a helpful assistant.

    Here is the stuff you've already said:
    {prev_responses}
    Try to avoid, repeating yourself too much.
    Avoid making up information not provided in the transcripts.
    Avoid preamble and remove any text formatting.
    """

    try:
        response = lemur.task(
            prompt=prompt,
            input_text=input_text,
            final_model="default",
            max_output_size=3000
        )
        print(response)
        update_google_docs(response.response)
        return response.response
    except Exception as e:
        print("Error: ", e)
        return "Error"


class TranscriptAccumulator:
    def __init__(self):
        self.transcript = ""
        self.prev_responses = ""
        self.last_update_time = time.time()

    def add_transcript(self, transcript_segment):
        self.transcript += " " + transcript_segment
        current_time = time.time()
        if current_time - self.last_update_time >= 15:
            print("\n CALLING LEMUR\n")
            self.lemur_output = lemur_call(self.transcript, self.prev_responses)
            self.prev_responses = self.lemur_output
            self.transcript = ""
            self.last_update_time= current_time


transcript_accumulator = TranscriptAccumulator()

aai.settings.api_key = API_KEY

def on_open(session_opened: aai.RealtimeSessionOpened):
    print("session opened on ", session_opened)

def on_error(error: aai.RealtimeError):
    print("Error: ", error)

def on_close():
    print("session closed")

def on_data(transcript: aai.RealtimeTranscript):
    if not transcript.text:
        return
    
    if isinstance(transcript, aai.RealtimeFinalTranscript):
        print(transcript.text, end="\r\n")
        transcript_accumulator.add_transcript(transcript.text)


transcriber = aai.RealtimeTranscriber(
    sample_rate=16_000,
    on_data=on_data,
    on_error=on_error,
    on_open=on_open,
    on_close=on_close
)

transcriber.connect()

microphone_stream = aai.extras.MicrophoneStream(sample_rate=16_000)

transcriber.stream(microphone_stream)

transcriber.close()
