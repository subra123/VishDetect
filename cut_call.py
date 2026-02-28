import subprocess

def cut_call_adb():
    # Keycode 6 is the global Android code for "End Call"
    subprocess.run(["adb", "shell", "input", "keyevent", "6"])
    print("🛑 Call Terminated via ADB.")

cut_call_adb()
