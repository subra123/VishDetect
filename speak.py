import pyaudio
import threading
from deepgram import DeepgramClient
from deepgram.core.events import EventType

import os
from dotenv import load_dotenv

# ADD THE PARENTHESES BELOW
load_dotenv()
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

# Audio Recording constants
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000

client = DeepgramClient(api_key=DEEPGRAM_API_KEY)

# Use the context manager as in your example
with client.listen.v1.connect(
    model="nova-2", # Nova-2 is the most stable for live voice
    language="en",
    encoding="linear16",
    sample_rate=RATE
) as connection:
    ready = threading.Event()

    def on_message(result):
        # Accessing nested channel/alternatives exactly like your script
        channel = getattr(result, "channel", None)
        if channel and hasattr(channel, "alternatives"):
            transcript = channel.alternatives[0].transcript
            if transcript:
                print(f"✔ {transcript}")

    # Set up event listeners
    connection.on(EventType.OPEN, lambda _: ready.set())
    connection.on(EventType.MESSAGE, on_message)

    def mic_stream():
        """Captures local microphone and sends to Deepgram"""
        audio = pyaudio.PyAudio()
        stream = audio.open(format=FORMAT, channels=CHANNELS,
                          rate=RATE, input=True,
                          frames_per_buffer=CHUNK)
        
        ready.wait() # Wait for Deepgram socket to open
        print("🎤 Microphone is LIVE. Start speaking...")
        
        try:
            while True:
                data = stream.read(CHUNK, exception_on_overflow=False)
                connection.send_media(data)
        except Exception as e:
            print(f"Mic error: {e}")
        finally:
            stream.stop_stream()
            stream.close()
            audio.terminate()

    # Start the mic thread
    threading.Thread(target=mic_stream, daemon=True).start()

    print("Connecting to Deepgram...")
    connection.start_listening()
