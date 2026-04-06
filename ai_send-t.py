import os
import subprocess
import threading
import queue
from dotenv import load_dotenv
from deepgram import DeepgramClient
from deepgram.core.events import EventType
from google import genai

# Load API keys
load_dotenv()

# --- HARDWARE ROUTING ---
LISTENING_DEVICE = "@DEFAULT_SINK@.monitor"
PHONE_TARGET = "bluez_output.BC_F7_30_F6_87_07.1" 

# --- CLIENTS & QUEUES ---
dg_client = DeepgramClient(api_key=os.getenv("DEEPGRAM_API_KEY"))
gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

chat_session = gemini_client.chats.create(
    model="gemini-2.5-flash",
    config={"system_instruction": "You are a highly responsive phone assistant. Answer iteratively and conversationally. Keep answers extremely brief, max 1 short sentence."}
)

task_queue = queue.Queue()
is_ai_speaking = False

def play_welcome():
    """Plays the pre-generated welcome message immediately."""
    if os.path.exists("welcome.wav"):
        print("📢 Playing Welcome Message...")
        subprocess.run(["pw-play", f"--target={PHONE_TARGET}", "welcome.wav"], check=True)
    else:
        print("⚠️ welcome.wav not found. Skipping intro.")

def ai_worker():
    """Background thread for Gemini thinking and TTS speaking."""
    global is_ai_speaking
    while True:
        caller_text = task_queue.get()
        if not caller_text:
            continue
            
        is_ai_speaking = True
        print(f"\n✅ User asked: {caller_text}")
        print("🧠 AI is thinking...")

        try:
            response = chat_session.send_message(caller_text)
            ai_reply = response.text.strip()
            print(f"🤖 AI: {ai_reply}")

            tts_response = dg_client.speak.v1.audio.generate(
                text=ai_reply,
                model="aura-asteria-en"
            )
            
            with open("reply.mp3", "wb") as f:
                for chunk in tts_response:
                    if chunk: f.write(chunk)

            subprocess.run(
                ["ffmpeg", "-y", "-i", "reply.mp3", "-loglevel", "error", "reply.wav"],
                check=True
            )

            print("📞 Speaking into phone call...")
            subprocess.run(["pw-play", f"--target={PHONE_TARGET}", "reply.wav"], check=True)
            
        except Exception as e:
            print(f"❌ AI Error: {e}")
        finally:
            is_ai_speaking = False
            task_queue.task_done()
            print("\n🎧 Listening to caller...")

def start_listening():
    """Connects to Deepgram and captures speaker audio."""
    global is_ai_speaking

    print("⏳ Connecting to Deepgram...")
    
    with dg_client.listen.v1.connect(
        model="nova-3",
        language="en",
        encoding="linear16",
        sample_rate=16000,
        channels=1,
        endpointing=300 
    ) as connection:
        
        ready = threading.Event()
        current_sentence = []

        def on_open(_):
            ready.set()
            print("✅ Agent is LIVE! Deepgram is ready.")

        def on_message(result):
            global is_ai_speaking
            if is_ai_speaking:
                return

            channel = getattr(result, "channel", None)
            if not channel or not channel.alternatives:
                return

            text = channel.alternatives[0].transcript
            if text:
                print(f"👂 Caller: {text}")
                current_sentence.append(text)

            if getattr(result, "speech_final", False) and current_sentence:
                full_text = " ".join(current_sentence).strip()
                if full_text:
                    task_queue.put(full_text)
                current_sentence.clear() 

        def on_error(err):
            print(f"❌ Deepgram Error: {err}")

        connection.on(EventType.OPEN, on_open)
        connection.on(EventType.MESSAGE, on_message)
        connection.on(EventType.ERROR, on_error)

        def capture_audio():
            ready.wait() 
            proc = subprocess.Popen(
                ["parecord", f"--device={LISTENING_DEVICE}", "--format=s16le", "--rate=16000", "--channels=1", "--raw"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )
            try:
                while True:
                    data = proc.stdout.read(2048)
                    if not data: break
                    connection.send_media(data)
            finally:
                proc.terminate()

        # Audio capture starts in background once Deepgram is ready
        threading.Thread(target=capture_audio, daemon=True).start()
        connection.start_listening()

if __name__ == "__main__":
    # 1. Start AI Thinking thread
    threading.Thread(target=ai_worker, daemon=True).start()
    
    # 2. Start Welcome Audio in a thread so it doesn't block Deepgram's connection start
    threading.Thread(target=play_welcome, daemon=True).start()

    # 3. Main thread starts Deepgram connection immediately
    try:
        start_listening()
    except KeyboardInterrupt:
        print("\n🛑 Hanging up cleanly...")

