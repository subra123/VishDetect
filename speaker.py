import os
from dotenv import load_dotenv

# ADD THE PARENTHESES BELOW
load_dotenv()

import subprocess
import audioop
import threading
from datetime import datetime
from deepgram import DeepgramClient
from deepgram.core.events import EventType

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

# arecord -f cd → 44.1kHz stereo
INPUT_RATE = 44100
DG_RATE = 16000
SAMPLE_WIDTH = 2
CHUNK = 4096

filename = f"transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

client = DeepgramClient(api_key=DEEPGRAM_API_KEY)

with client.listen.v1.connect(
    model="nova-2",
    encoding="linear16",
    sample_rate=DG_RATE,
    channels=1,
    punctuate=True,
    smart_format=True,
    interim_results=True
) as connection:

    ready = threading.Event()

    def on_open(_):
        print("✅ Deepgram WebSocket OPEN")
        ready.set()

    def on_message(result):
        channel = getattr(result, "channel", None)
        if channel and channel.alternatives:
            text = channel.alternatives[0].transcript
            if text:
                print(text)
                with open(filename, "a") as f:
                    f.write(text + "\n")

    def on_error(err):
        print("❌ Deepgram error:", err)

    connection.on(EventType.OPEN, on_open)
    connection.on(EventType.MESSAGE, on_message)
    connection.on(EventType.ERROR, on_error)

    print("🎧 Transcribing ONLY iPad audio from plughw:2,0")
    print(f"📝 Transcript file: {filename}")

    # Start arecord EXACTLY like your working test
    proc = subprocess.Popen(
        ["arecord", "-D", "plughw:2,0", "-f", "cd", "-t", "raw"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL
    )

    def audio_loop():
        ready.wait()  # wait until Deepgram socket is open
        while True:
            data = proc.stdout.read(CHUNK)
            if not data:
                break

            mono = audioop.tomono(data, SAMPLE_WIDTH, 0.5, 0.5)
            data_16k, _ = audioop.ratecv(
                mono,
                SAMPLE_WIDTH,
                1,
                INPUT_RATE,
                DG_RATE,
                None
            )

            connection.send_media(data_16k)

    threading.Thread(target=audio_loop, daemon=True).start()

    # THIS is what keeps the program alive
    connection.start_listening()

