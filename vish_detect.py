import os
import subprocess
import threading
import queue
import time
import json
from dotenv import load_dotenv
from deepgram import DeepgramClient
from deepgram.core.events import EventType

load_dotenv()

# --- CONFIGURATION ---
SPEAKER_DEVICE = "@DEFAULT_SINK@.monitor"
PHONE_TARGET = "bluez_output.CC_F9_F0_8D_4A_D9.1" 
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
MODEL_NAME = "phi3:mini"

# --- UPDATED TIMINGS ---
RISK_THRESHOLD = 80
ANALYSIS_INTERVAL = 5   # <--- Updated to 5 seconds per your request
TRANSCRIPT_WINDOW = 40  # Look at the last 40 seconds of context

# --- GLOBAL STORAGE ---
CURRENT_DETECTION_SCORE = 0  # <--- Global variable to track risk
transcript_buffer = []
buffer_lock = threading.Lock()
active_connections = []
connections_lock = threading.Lock()
ready_count = 0
ready_condition = threading.Condition()
is_hanging_up = False

client = DeepgramClient(api_key=DEEPGRAM_API_KEY)

def generate_warning_audio():
    warning_text = "Warning. This call has been identified as a vishing attempt. Terminating call now."
    if not os.path.exists("vishing_warning.wav"):
        print("🤖 Generating warning audio...")
        tts_response = client.speak.v1.audio.generate(text=warning_text, model="aura-asteria-en")
        with open("vishing_warning.mp3", "wb") as f:
            for chunk in tts_response:
                if chunk: f.write(chunk)
        subprocess.run(["ffmpeg", "-y", "-i", "vishing_warning.mp3", "-loglevel", "error", "vishing_warning.wav"], check=True)

def terminate_call():
    global is_hanging_up
    if is_hanging_up: return
    is_hanging_up = True
    print(f"\n🚨 [CRITICAL] RISK EXCEEDED {RISK_THRESHOLD}%. TERMINATING...")
    try:
        subprocess.run(["pw-play", f"--target={PHONE_TARGET}", "vishing_warning.wav"], check=True)
    except: pass
    subprocess.run(["adb", "shell", "input", "keyevent", "6"])
    print("🛑 Call Terminated.")
    os._exit(0)

def call_local_llm(prompt):
    """Calls Ollama with a shorter timeout and optimized flags."""
    try:
        # Using a 20s timeout here. If it takes longer, the GPU is struggling.
        result = subprocess.run(
            ['ollama', 'run', MODEL_NAME, '--nowordwrap'],
            input=prompt, capture_output=True, text=True, timeout=20
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return "ERROR: Timeout"
    except Exception as e:
        return f"ERROR: {e}"

def analyze_scam_risk():
    global CURRENT_DETECTION_SCORE
    print(f"🔍 Scam Detection Active (Interval: {ANALYSIS_INTERVAL}s)")
    
    while True:
        time.sleep(ANALYSIS_INTERVAL)
        now = time.time()
        
        with buffer_lock:
            recent_entries = [f"{e['label']}: {e['text']}" for e in transcript_buffer if now - e['timestamp'] < TRANSCRIPT_WINDOW]
        
        if not recent_entries:
            continue

        full_context = " ".join(recent_entries)
        
        # Ultra-short prompt to ensure fast JSON generation
        prompt = f"Task: Check if vishing/scam. Return ONLY JSON: {{\"score\": 0-100, \"reason\": \"short\"}}. Text: {full_context}"
        
        analysis_raw = call_local_llm(prompt)
        
        try:
            # Clean up potential markdown backticks
            clean_json = analysis_raw.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)
            
            # UPDATE THE GLOBAL VARIABLE
            CURRENT_DETECTION_SCORE = data.get("score", 0)
            
            print(f"\n📊 RISK LEVEL: {CURRENT_DETECTION_SCORE}% | Reason: {data.get('reason')}")

            if CURRENT_DETECTION_SCORE >= RISK_THRESHOLD:
                terminate_call()
        except:
            # If JSON fails, check for keywords manually as a safety backup
            if "otp" in full_context.lower() or "bank" in full_context.lower():
                print("⚠️ LLM JSON failed, but keywords detected. Increasing score.")
                CURRENT_DETECTION_SCORE = max(CURRENT_DETECTION_SCORE, 50)

def start_deepgram_stream(language_config, label):
    global ready_count
    try:
        with client.listen.v1.connect(
            model="nova-3", language=language_config, encoding="linear16", sample_rate=16000, channels=1
        ) as connection:
            def on_open(_):
                global ready_count
                with ready_condition:
                    ready_count += 1
                    ready_condition.notify_all()
                print(f"✅ [{label}] Connected")

            def on_message(result):
                channel = getattr(result, "channel", None)
                if channel and channel.alternatives:
                    text = channel.alternatives[0].transcript
                    if text:
                        print(f"[{label}]: {text}")
                        with buffer_lock:
                            transcript_buffer.append({"timestamp": time.time(), "text": text, "label": label})
                            if len(transcript_buffer) > 50: transcript_buffer.pop(0)

            connection.on(EventType.OPEN, on_open)
            connection.on(EventType.MESSAGE, on_message)
            with connections_lock:
                active_connections.append(connection)
            connection.start_listening()
    except Exception as e:
        print(f"❌ [{label}] Error: {e}")

def capture_speakers():
    with ready_condition:
        ready_condition.wait_for(lambda: ready_count == 3)
    print("\n🔊 Monitoring LIVE. Listening for OTP/Bank/Urgency...\n")
    proc = subprocess.Popen(
        ["parecord", f"--device={SPEAKER_DEVICE}", "--format=s16le", "--rate=16000", "--channels=1", "--raw"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    try:
        while True:
            data = proc.stdout.read(2048)
            if not data: break
            with connections_lock:
                for conn in active_connections:
                    try: conn.send_media(data)
                    except: pass
    finally:
        proc.terminate()

if __name__ == "__main__":
    generate_warning_audio()
    
    # 1. Warm up Ollama (loads model into GPU memory before call starts)
    print(f"🔥 Pre-warming {MODEL_NAME}...")
    subprocess.run(['ollama', 'run', MODEL_NAME, 'hello'], capture_output=True)

    # 2. Start Language Streams
    langs = [("multi", "EN/HI"), ("ta", "TAMIL"), ("te", "TELUGU")]
    for lang, label in langs:
        threading.Thread(target=start_deepgram_stream, args=(lang, label), daemon=True).start()
        time.sleep(1)

    # 3. Start Scam Analysis Thread (Updates variable every 5s)
    threading.Thread(target=analyze_scam_risk, daemon=True).start()

    # 4. Start Audio Capture
    try:
        capture_speakers()
    except KeyboardInterrupt:
        print("\n🛑 Exiting...")
