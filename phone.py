import os
from dotenv import load_dotenv

# ADD THE PARENTHESES BELOW
load_dotenv() 

import subprocess
import audioop
from deepgram import DeepgramClient
from deepgram.core.events import EventType

print("DEBUG DG KEY:", repr(os.getenv("DEEPGRAM_API_KEY")))

# Now this will actually find the key
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")


INPUT_RATE = 44100        # arecord -f cd = 44.1kHz
DG_RATE = 16000
SAMPLE_WIDTH = 2          # 16-bit
CHANNELS = 2              # cd = stereo
CHUNK = 4096

client = DeepgramClient(api_key=DEEPGRAM_API_KEY)

with client.listen.v1.connect(
    model="nova-2",
    encoding="linear16",
    sample_rate=DG_RATE,
    channels=1,
    punctuate=True,
    interim_results=True
) as connection:

    def on_message(result):
        channel = getattr(result, "channel", None)
        if channel and channel.alternatives:
            text = channel.alternatives[0].transcript
            if text:
                print(text)

    connection.on(EventType.MESSAGE, on_message)

    print("🎧 Transcribing ONLY iPad audio (YouTube, videos, etc.)")

    # Start arecord exactly like your working command
    proc = subprocess.Popen(
        [
            "arecord",
            "-D", "plughw:2,0",
            "-f", "cd",
            "-t", "raw"
        ],
        stdout=subprocess.PIPE
    )

    try:
        while True:
            data = proc.stdout.read(CHUNK)
            if not data:
                break

            # Stereo → mono
            mono = audioop.tomono(data, SAMPLE_WIDTH, 0.5, 0.5)

            # 44.1k → 16k
            data_16k, _ = audioop.ratecv(
                mono,
                SAMPLE_WIDTH,
                1,
                INPUT_RATE,
                DG_RATE,
                None
            )

            connection.send_media(data_16k)

    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()

