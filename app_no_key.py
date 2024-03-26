import assemblyai as aai
import time
import os
import re
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


API_KEY = "KEY"

CLIENT_FILE = "credentials.json"
DOCUMENT_ID = "DOC_ID"

SCOPES = ["https://www.googleapis.com/auth/documents"]
start_time = 0



def get_doc_info():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    try:
        service = build("docs", "v1", credentials=creds)
        current_document = service.documents().get(documentId=DOCUMENT_ID).execute()
        current_content = current_document.get('body').get('content', [])
        transcript_accumulator.set_last_line(len(current_content))
    except HttpError as err:
        print(err)

def update_google_docs(content, index):
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

        # Retrieve the current content of the document
        current_document = service.documents().get(documentId=DOCUMENT_ID).execute()
        current_content = current_document.get('body').get('content', [])
        transcript_accumulator.set_last_line(len(current_content))

        if index >= 0 and index < len(current_content):
            index = current_content[index]['startIndex']
            requests = [
                {
                    'insertText' : {
                        'text' : content,
                        'location' : {
                            'index' : index - 1
                        }
                    }
                }
            ]
        else:
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




def lemur_call(transcript, prev_responses, index):
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

    prompt = f"""
    You are a helpful, diligent and succinct assistant that is going to take notes based on what I tell you.

    All I want you to do is repeat back what I say to you but to fix any spelling or grammatical mistakes you may suspect exist in the input.
    I am writing notes to you and I want you to format it in bullet point form, I have clearly indicated each bullet point by starting it with a * symbol.

    Avoid making up information not provided in the transcripts.
    Avoid preamble and remove any text formatting.
    I dont want you to say anything like "here are the bullet points", just repeat back what I said in the formatted bullet point form that I've described to you.
    """

    try:
        response = lemur.task(
            prompt=prompt,
            input_text=input_text,
            final_model="default",
            max_output_size=3000
        )
        print(response)
        update_google_docs(response.response, index)
        return response.response
    except Exception as e:
        print("Error: ", e)
        return "Error"


class TranscriptAccumulator:
    def __init__(self):
        self.transcript = ""
        self.prev_responses = ""
        self.last_update_time = time.time()
        self.index = -1
        self.last_line = 0

    def add_transcript(self, transcript_segment):
        my_input = ("" + transcript_segment).lower()
        if "move" in my_input and "cursor" in my_input:
            if "line" in my_input:
                line_no = extract_number_from_string(my_input)
                if line_no >= 0:
                    self.index = line_no
            elif "end" in my_input:
                self.index = -1
            else:
                amount = extract_number_from_string(my_input)
                if amount < 0:
                    amount = 1
                if "up" in my_input:
                    if self.index < 0:
                        self.index = max(self.last_line - amount, 0)
                    else:
                        self.index = max(self.index - amount, 0)
                elif "down" in my_input:
                    if self.index >= 0:
                        self.index += amount
                    if self.index > self.last_line:
                        self.index = -1

            print("\nCursor is at line", self.index)
            
        elif "new bullet point" in my_input:
            self.transcript += "\n*"
        elif "update" in my_input and "notes" in my_input:
            print("\n CALLING LEMUR\n")
            self.lemur_output = lemur_call(self.transcript, self.prev_responses, self.index)
            self.prev_responses = self.lemur_output
            self.transcript = ""
        else:
            self.transcript += " " + transcript_segment

    def set_last_line(self, last_line):
        self.last_line = last_line


transcript_accumulator = TranscriptAccumulator()

aai.settings.api_key = API_KEY

def on_open(session_opened: aai.RealtimeSessionOpened):
    global start_time
    start_time = time.time()
    print("session opened on ", session_opened)

def on_error(error: aai.RealtimeError):
    print("Error: ", error)

def on_close():
    print("session closed")
    seconds = time.time() - start_time
    print("time elapsed: " + format_time(seconds))
    os._exit(0)

def on_data(transcript: aai.RealtimeTranscript):
    if not transcript.text:
        return
    
    if isinstance(transcript, aai.RealtimeFinalTranscript):
        print(transcript.text, end="\r\n")
        if "end session" in transcript.text.lower():
            transcriber.close()
        transcript_accumulator.add_transcript(transcript.text)

def format_time(seconds):
    return "%02d:%02d:%02d" % (seconds // 3600, (seconds % 3600) // 60, seconds % 60)

def extract_number_from_string(input_string):
    number_mapping = {
        "zero": "0",
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
        "ten": "10",
        "eleven": "11",
        "twelve": "12"
    }

    pattern = r'\b(?:\d+|' + '|'.join(number_mapping.keys()) + r')\b'
    
    numbers = re.findall(pattern, input_string)
    if numbers:
        number = numbers[0]
        if number in number_mapping:
            return int(number_mapping[number])
        else:
            return int(number)
    else:
        return -1


transcriber = aai.RealtimeTranscriber(
    sample_rate=16_000,
    on_data=on_data,
    on_error=on_error,
    on_open=on_open,
    on_close=on_close
)

transcriber.connect()
get_doc_info()

microphone_stream = aai.extras.MicrophoneStream(sample_rate=16_000)

transcriber.stream(microphone_stream)

print("\n\nAAAAAAAAAAA\n\n")
transcriber.close()
