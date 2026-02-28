import subprocess
from gtts import gTTS

PHONE_TARGET = "bluez_output.CC_F9_F0_8D_4A_D9.1"
AI_TEXT = "Hi, my name is A I. I am a virtual assistant operating on a Linux machine. How can I help you today?"

def generate_and_play_audio():
    mp3_filename = "ai_response.mp3"
    wav_filename = "ai_response.wav"
    
    print("🤖 Generating AI voice via Google TTS...")
    
    # 1. Generate the MP3
    tts = gTTS(text=AI_TEXT, lang='en', tld='co.in')
    tts.save(mp3_filename)
    print("✅ MP3 Audio generated!")

    # 2. Convert MP3 to WAV natively so pw-play can read it
    print("🔄 Converting to WAV format...")
    subprocess.run(
        ["ffmpeg", "-y", "-i", mp3_filename, "-loglevel", "error", wav_filename],
        check=True
    )

    print(f"📞 Injecting AI voice directly into the phone stream...")
    
    # 3. Play the WAV file into the Bluetooth stream
    subprocess.run(
        [
            "pw-play", 
            f"--target={PHONE_TARGET}", 
            wav_filename
        ],
        check=True
    )
    
    print("🗣️ Done speaking!")

if __name__ == "__main__":
    generate_and_play_audio()
