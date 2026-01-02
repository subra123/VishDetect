# VishDetect: AI Conference Bot for Universal Vishing Protection

## 🛡️ The Vision
VishDetect is a device-agnostic, real-time vishing (voice phishing) detection system. Unlike traditional apps, VishDetect lives at the network level, allowing it to protect any device—from the latest 5G smartphones to legacy feature phones like the Nokia 3110.

### The "Grandfather" Problem
Most modern security relies on 5G, high-speed internet, and on-device LLMs. This leaves vulnerable populations (like the elderly using simple feature phones) completely unprotected. VishDetect solves this by making the AI a **third participant** in every call.

## ⚙️ How It Works
1. **Network Integration:** A module at the service-provider level triggers an AI Conference Bot.
2. **The 3-Way Call:** Every call becomes a trio: User + Caller + AI Bot.
3. **Passive Monitoring:** The AI performs sub-second Live Speech-to-Text (STT) and Multimodal analysis.
4. **Intervention:** If a scam pattern is detected, the AI disconnects the call and blocks the number instantly.

## 🛠️ Hardware Simulation (The "Listener" Setup)
To replicate this network-level intelligence in a lab environment, we use a physical "man-in-the-middle" audio bridge:
- **Input Device:** A "listener" phone connected via **Aux-to-Aux cable** to the Linux Server.
- **Signal Processing:** We use `arecord` to capture the phone's audio output directly into the ALSA sound buffer.
- **Command:** `arecord -f cd -D plughw:2,0 -t raw`



## 📂 Project Structure
| File | Description |
| :--- | :--- |
| `phone.py` | **Core Engine.** Captures raw audio via `arecord`, converts Stereo to Mono, downsamples to 16kHz, and streams to Deepgram Nova-2. |
| `speaker.py` | Handles iPad/External audio transcription and logs conversations to dated text files. |
| `speak.py` | Local microphone testing script to verify Deepgram connectivity. |
| `check.py` | Utility to list available Pyaudio device indices (used to find `plughw:2,0`). |
| `test.py` | Audio interception tester with ALSA error suppression. |

## 🚀 Setup & Installation
1. **Clone the repo:** `git clone ...`
2. **Install Dependencies:**
   ```bash
   pip install deepgram-sdk python-dotenv pyaudio
   sudo apt-get install alsa-utils
