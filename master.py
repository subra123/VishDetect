import os
import subprocess
import threading
from dotenv import load_dotenv
from deepgram import DeepgramClient
from deepgram.core.events import EventType

load_dotenv()

# The magic PulseAudio device that captures your speaker output
SPEAKER_DEVICE = "@DEFAULT_SINK@.monitor"
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

client = DeepgramClient(api_key=DEEPGRAM_API_KEY)

# Global variables to manage our 3 parallel streams
active_connections = []
connections_lock = threading.Lock()
ready_count = 0
ready_condition = threading.Condition()

def start_deepgram_stream(language_config, label):
    """Opens a dedicated Deepgram connection for a specific language."""
    global ready_count
    
    with client.listen.v1.connect(
        model="nova-3",          
        language=language_config,
        encoding="linear16",
        sample_rate=16000,
        channels=1
    ) as connection:
        
        def on_open(_):
            global ready_count
            with ready_condition:
                ready_count += 1
                ready_condition.notify_all()
            print(f"✅ Deepgram [{label}] stream is connected!")

        def on_message(result):
            channel = getattr(result, "channel", None)
            if channel and channel.alternatives:
                alt = channel.alternatives[0]
                text = alt.transcript
                confidence = alt.confidence
                
                # Only print if there is actual text
                if text:
                    print(f"[{label}] (conf: {confidence:.2f}): {text}")

        def on_error(err):
            print(f"❌ Error in [{label}]: {err}")

        connection.on(EventType.OPEN, on_open)
        connection.on(EventType.MESSAGE, on_message)
        connection.on(EventType.ERROR, on_error)

        # Safely add this connection to our active list
        with connections_lock:
            active_connections.append(connection)

        # This blocks the thread and keeps the WebSocket open
        connection.start_listening()

def capture_speakers():
    """Captures system audio and broadcasts it to all active Deepgram streams."""
    # Wait until all 3 streams report that they are fully open
    with ready_condition:
        ready_condition.wait_for(lambda: ready_count == 3)
        
    print("\n🔊 All 3 streams ready! Play some audio on your computer...\n")
    print("-" * 50)
    
    # parecord grabs the speaker output directly
    proc = subprocess.Popen(
        [
            "parecord", 
            f"--device={SPEAKER_DEVICE}", 
            "--format=s16le", 
            "--rate=16000", 
            "--channels=1", 
            "--raw"
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL
    )
    
    try:
        while True:
            # Read a chunk of audio from the speakers
            data = proc.stdout.read(2048)
            if not data:
                break
            
            # Broadcast this chunk to every active Deepgram connection
            with connections_lock:
                for conn in active_connections:
                    try:
                        conn.send_media(data)
                    except Exception:
                        pass # Ignore temporary network drops on individual streams
    finally:
        proc.terminate()

# --- MAIN EXECUTION ---

if __name__ == "__main__":
    # Define the 3 streams we want to run in parallel
    stream_configs = [
        ("multi", "EN/HI"),
        ("ta", "TAMIL"),
        ("te", "TELUGU")
    ]

    # Spin up a background thread for each language stream
    for lang, label in stream_configs:
        t = threading.Thread(target=start_deepgram_stream, args=(lang, label), daemon=True)
        t.start()

    # Start capturing audio in the main thread (this will keep the script running)
    try:
        capture_speakers()
    except KeyboardInterrupt:
        print("\n🛑 Exiting cleanly...")
