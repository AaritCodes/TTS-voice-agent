import socket
import struct
import uuid
import time
import argparse
import sys
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    print("[ERROR] sounddevice is required. Run: pip install sounddevice numpy")
    sys.exit(1)

def record_audio(duration=5, fs=8000):
    print(f"\n🎤 Recording for {duration} seconds... Speak now!")
    recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='int16')
    sd.wait()
    print("✅ Recording finished.")
    return recording.tobytes()

def main():
    parser = argparse.ArgumentParser(description="Mock Asterisk AudioSocket Client")
    parser.add_argument("--host", required=True, help="GCP Server IP Address")
    parser.add_argument("--port", type=int, default=9090, help="GCP Server Port (default 9090)")
    args = parser.parse_args()

    print(f"=====================================")
    print(f" Mock Asterisk Client")
    print(f" Connecting to: {args.host}:{args.port}")
    print(f"=====================================")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((args.host, args.port))
    except Exception as e:
        print(f"❌ Could not connect: {e}")
        print("Make sure Arvind has opened TCP port 9090 on the GCP firewall!")
        return

    # 1. Send Asterisk UUID Header (0x01)
    call_id = uuid.uuid4().bytes
    sock.sendall(struct.pack(">BH", 0x01, len(call_id)) + call_id)
    print("📞 Connected to Python Server! Sent Asterisk Call ID.")

    # 2. Record Speech
    audio_bytes = record_audio(duration=5)

    # 3. Stream Speech over AudioSocket
    print("📤 Streaming audio bytes over TCP...")
    for i in range(0, len(audio_bytes), 320):
        chunk = audio_bytes[i:i+320]
        # Pad to exactly 320 bytes if it's the last chunk
        if len(chunk) < 320:
            chunk += b'\x00' * (320 - len(chunk))
        sock.sendall(struct.pack(">BH", 0x10, len(chunk)) + chunk)
        time.sleep(0.015) # Pace the audio streaming to simulate real-time Asterisk

    # 4. Stream Silence (to trigger the server's Voice Activity Detection)
    print("🤫 Sending silence to trigger the server's AI processing...")
    silence_chunk = b'\x00' * 320
    for _ in range(100): # 100 chunks * 20ms = 2.0 seconds of silence
        sock.sendall(struct.pack(">BH", 0x10, len(silence_chunk)) + silence_chunk)
        time.sleep(0.015)

    # 5. Receive AI Response
    print("⏳ Waiting for AI voice response...")
    response_audio = bytearray()
    sock.settimeout(15.0) # Wait up to 15 seconds for Sarvam/Gemini
    
    try:
        while True:
            header = sock.recv(3)
            if not header: break
            kind, length = struct.unpack(">BH", header)
            
            if kind == 0x10:
                payload = sock.recv(length)
                response_audio.extend(payload)
            elif kind == 0x00:
                print("Server sent hangup command.")
                break
    except socket.timeout:
        print("✅ Finished receiving audio stream.")

    # 6. Play Response
    if response_audio:
        print("🔊 Playing AI response...")
        audio_array = np.frombuffer(response_audio, dtype=np.int16)
        sd.play(audio_array, samplerate=8000)
        sd.wait()
        print("✅ Playback finished.")
    else:
        print("❌ Received no audio from server.")

    # Send hangup and close
    try:
        sock.sendall(struct.pack(">BH", 0x00, 0))
    except:
        pass
    sock.close()
    print("\n👋 Goodbye!")

if __name__ == "__main__":
    main()
