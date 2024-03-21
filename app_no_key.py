import assemblyai as aai
import time

API_KEY = "API KEY"

def lemur_call(transcript, prev_responses):
    lemur = aai.Lemur
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
    #else:
     #   print(transcript.text, end="\r")


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