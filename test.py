import os

# This hides the ALSA warnings you saw in your terminal
os.environ['PYAUDIO_IGNORE_ALSA_ERRORS'] = '1'

def mic_stream():
    audio = pyaudio.PyAudio()
    
    # Using Index 2 based on your terminal output
    INPUT_DEVICE_INDEX = 2 

    try:
        stream = audio.open(
            format=FORMAT, 
            channels=CHANNELS,
            rate=RATE, 
            input=True,
            input_device_index=INPUT_DEVICE_INDEX,
            frames_per_buffer=CHUNK
        )
        
        ready.wait() 
        print(f"🎤 Intercepting Audio from Index {INPUT_DEVICE_INDEX}...")

        while True:
            data = stream.read(CHUNK, exception_on_overflow=False)
            connection.send_media(data)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()
