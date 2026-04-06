import os
import subprocess
import threading
import queue
import re
from dotenv import load_dotenv
from deepgram import DeepgramClient
from deepgram.core.events import EventType
from google import genai

# ==============================
# LOAD API KEYS
# ==============================
load_dotenv()

# ==============================
# AUTO-EXTRACT BLUETOOTH TARGET
# ==============================
def get_phone_target():
    try:
        result = subprocess.check_output(
            ["pactl", "list", "cards"],
            text=True
        )

        match = re.search(r"bluez_card\.([A-F0-9_]+)", result)

        if not match:
            print("❌ No Bluetooth card found.")
            return None

        mac_underscored = match.group(1)
        phone_target = f"bluez_output.{mac_underscored}.1"

        return phone_target

    except Exception as e:
        print(f"❌ Error detecting Bluetooth device: {e}")
        return None


PHONE_TARGET = get_phone_target()

if not PHONE_TARGET:
    print("❌ Could not generate PHONE_TARGET. Exiting.")
    exit(1)

print(f"🎧 Using PHONE_TARGET: {PHONE_TARGET}")

# ==============================
# HARDWARE ROUTING
# ==============================
LISTENING_DEVICE = "@DEFAULT_SINK@.monitor"

# ==============================
# CLIENTS & QUEUES
# ==============================
dg_client = DeepgramClient(api_key=os.getenv("DEEPGRAM_API_KEY"))
gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

chat_session = gemini_client.chats.create(
    model="gemini-2.5-flash",
    config={
        "system_instruction":
        "You are a highly responsive phone assistant. "
        "Answer iteratively and conversationally. "
        "Keep answers extremely brief, max 1 short sentence."
    }
)

task_queue = queue.Queue()
is_ai_speaking = False

# ==============================
# PLAY WELCOME MESSAGE
# ==============================
def play_welcome():
    if os.path.exists("welcome.wav"):
        print("📢 Playing Welcome Message...")
        subprocess.run(
            ["pw-play", f"--target={PHONE_TARGET}", "welcome.wav"],
            check=True
        )
    else:
        print("⚠️ welcome.wav not found. Skipping intro.")

# ==============================
# AI WORKER THREAD
# ==============================
def ai_worker():
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

            # Generate TTS
            tts_response = dg_client.speak.v1.audio.generate(
                text=ai_reply,
                model="aura-asteria-en"
            )

            with open("reply.mp3", "wb") as f:
                for chunk in tts_response:
                    if chunk:
                        f.write(chunk)

            # Convert to WAV
            subprocess.run(
                ["ffmpeg", "-y", "-i", "reply.mp3",
                 "-loglevel", "error", "reply.wav"],
                check=True
            )

            print("📞 Speaking into phone call...")
            subprocess.run(
                ["pw-play", f"--target={PHONE_TARGET}", "reply.wav"],
                check=True
            )

        except Exception as e:
            print(f"❌ AI Error: {e}")

        finally:
            is_ai_speaking = False
            task_queue.task_done()
            print("\n🎧 Listening to caller...")

# ==============================
# START LISTENING (Deepgram)
# ==============================
def start_listening():
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
                [
                    "parecord",
                    f"--device={LISTENING_DEVICE}",
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
                    data = proc.stdout.read(2048)
                    if not data:
                        break
                    connection.send_media(data)
            finally:
                proc.terminate()

        threading.Thread(target=capture_audio, daemon=True).start()
        connection.start_listening()

# ==============================
# MAIN
# ==============================
if __name__ == "__main__":
    threading.Thread(target=ai_worker, daemon=True).start()
    threading.Thread(target=play_welcome, daemon=True).start()

    try:
        start_listening()
    except KeyboardInterrupt:
        print("\n🛑 Hanging up cleanly...")
