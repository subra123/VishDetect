import asyncio
import os
import subprocess
from dotenv import load_dotenv
from google import genai

load_dotenv()

# --- THE REVERSED ROUTING ---
LISTENING_DEVICE = "@DEFAULT_SINK@.monitor"
PHONE_TARGET = "bluez_output.CC_F9_F0_8D_4A_D9.1" 

async def main():
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    print("🚀 Firing up audio engines...")

    rec_proc = subprocess.Popen(
        ["parecord", f"--device={LISTENING_DEVICE}", "--format=s16le", "--rate=16000", "--channels=1", "--raw"],
        stdout=subprocess.PIPE
    )

    play_proc = subprocess.Popen(
        ["pacat", f"--device={PHONE_TARGET}", "--format=s16le", "--rate=24000", "--channels=1", "--raw"],
        stdin=subprocess.PIPE
    )

    print("⏳ Connecting to Gemini Multimodal Live API...")

    # THE FIX: Using the new, stable Live Audio model
    MODEL_ID = "gemini-2.5-flash"
    
    config = {"response_modalities": ["AUDIO"]}
    
    try:
        async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
            print("✅ LIVE! Start talking on the phone call.")

            # --- UPLOAD THREAD ---
            async def send_audio():
                while True:
                    data = rec_proc.stdout.read(4096)
                    if not data:
                        break
                    await session.send(
                        input={"data": data, "mime_type": "audio/pcm;rate=16000"}, 
                        end_of_turn=False
                    )
                    await asyncio.sleep(0.01)

            # --- DOWNLOAD THREAD ---
            async def receive_audio():
                async for response in session.receive():
                    server_content = response.server_content
                    if server_content and server_content.model_turn:
                        for part in server_content.model_turn.parts:
                            if part.inline_data:
                                try:
                                    play_proc.stdin.write(part.inline_data.data)
                                    play_proc.stdin.flush()
                                except BrokenPipeError:
                                    # Silently handle the broken pipe if the call ends abruptly
                                    pass

            # Run both the upload and download loops at the same time
            asyncio.create_task(send_audio())
            asyncio.create_task(receive_audio())
            
            # Keep the connection open forever!
            await asyncio.Future() 

    except Exception as e:
        print(f"\n❌ Connection Error: {e}")
    finally:
        print("🧹 Cleaning up audio processes...")
        rec_proc.terminate()
        play_proc.terminate()
        # Kill the processes quietly so they don't turn into zombies
        os.system("killall parecord pacat 2>/dev/null")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Hanging up cleanly...")
