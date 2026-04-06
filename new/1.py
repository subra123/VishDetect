import os
import time
import queue
import threading
import json
import struct
from collections import deque
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)

SAMPLE_RATE = 16000
CHUNK_DURATION = 3  # seconds
CHUNK_SIZE = SAMPLE_RATE * CHUNK_DURATION * 2  # 16-bit = 2 bytes

audio_queue = queue.Queue()
transcript_buffer = deque(maxlen=100)

# ------------------------------------------------------------------
# WAV HEADER
# ------------------------------------------------------------------
def make_wav_header(data_size, sample_rate=16000, channels=1, bit_depth=16):
    byte_rate = sample_rate * channels * bit_depth // 8
    block_align = channels * bit_depth // 8
    return struct.pack('<4sI4s4sIHHIIHH4sI',
        b'RIFF', 36 + data_size, b'WAVE',
        b'fmt ', 16, 1, channels,
        sample_rate, byte_rate, block_align, bit_depth,
        b'data', data_size
    )

# ------------------------------------------------------------------
# GROQ STT
# ------------------------------------------------------------------
def transcribe_chunk(audio_bytes: bytes):
    with open("temp.wav", "wb") as f:
        f.write(make_wav_header(len(audio_bytes)))
        f.write(audio_bytes)

    with open("temp.wav", "rb") as f:
        result = client.audio.transcriptions.create(
            file=("chunk.wav", f),
            model="whisper-large-v3-turbo",
            response_format="verbose_json",
            temperature=0.0
        )

    return {"text": result.text, "language": result.language}

# ------------------------------------------------------------------
# GROQ LLM (Detection)
# ------------------------------------------------------------------
SYSTEM_PROMPT = "You are a telecom fraud detection system. Return JSON only."

def analyze_risk(text):
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",  # ✅ FIXED
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text}
        ],
        temperature=0.1,
        max_tokens=300,
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

# ------------------------------------------------------------------
# AUDIO CAPTURE (PipeWire)
# ------------------------------------------------------------------
def capture_audio():
    import subprocess

    proc = subprocess.Popen(
        ["parecord", "--format=s16le", "--rate=16000", "--channels=1", "--raw"],
        stdout=subprocess.PIPE
    )

    while True:
        data = proc.stdout.read(2048)
        if not data:
            break
        audio_queue.put(data)

# ------------------------------------------------------------------
# STT LOOP (Groq)
# ------------------------------------------------------------------
def stt_loop():
    buffer = bytearray()

    while True:
        chunk = audio_queue.get()
        buffer.extend(chunk)

        if len(buffer) < CHUNK_SIZE:
            continue

        audio_bytes = bytes(buffer[:CHUNK_SIZE])
        buffer = buffer[CHUNK_SIZE:]

        result = transcribe_chunk(audio_bytes)

        text = result["text"].strip()
        lang = result["language"]

        if text:
            print(f"[{lang}] {text}")
            transcript_buffer.append(text)

# ------------------------------------------------------------------
# ANALYSIS LOOP
# ------------------------------------------------------------------
def analysis_loop():
    while True:
        time.sleep(5)

        if len(transcript_buffer) < 2:
            continue

        combined = "\n".join(transcript_buffer)

        result = analyze_risk(combined)

        print("\n📊 Detection Result:")
        print(result)

# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
if __name__ == "__main__":
    print("🚀 VishDetect (Groq STT + LLM) Starting...")

    threads = [
        threading.Thread(target=capture_audio, daemon=True),
        threading.Thread(target=stt_loop, daemon=True),
        threading.Thread(target=analysis_loop, daemon=True),
    ]

    for t in threads:
        t.start()

    while True:
        time.sleep(1)
