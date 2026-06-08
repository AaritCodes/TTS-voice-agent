"""
UDP Voice Assistant Client (Mock Test)
======================================
This client simulates a VoIP caller. It can either:
  1. Record live audio from your microphone
  2. Send a pre-recorded .wav file

It sends the audio to the UDP server, receives the AI's text + audio response,
and plays the audio response through your speakers.

Usage:
    # Option 1: Record from microphone (speak, then press Enter to stop)
    python udp_client.py

    # Option 2: Send a pre-recorded WAV file
    python udp_client.py --file path/to/audio.wav

    # Option 3: Specify a custom server IP
    python udp_client.py --host 192.168.1.100 --port 5000
"""

import socket
import os
import sys
import json
import wave
import time
import argparse
import threading
import struct

# ─── CONFIG ──────────────────────────────────────────
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5060
CHUNK_SIZE = 4096
RECORD_SECONDS = 7         # Max recording duration
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2


def record_from_mic(output_path, duration=RECORD_SECONDS):
    """Record audio from the microphone using sounddevice."""
    try:
        import sounddevice as sd
        import numpy as np
    except ImportError:
        print("[ERROR] sounddevice not installed. Run: pip install sounddevice")
        return False
    
    print(f"\n🎤  Recording for up to {duration} seconds...")
    print("    (Press Ctrl+C to stop early)\n")
    
    try:
        recording = sd.rec(
            int(duration * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype='int16'
        )
        sd.wait()
    except KeyboardInterrupt:
        sd.stop()
        print("\n    Recording stopped early.")
    
    # Save to WAV
    with wave.open(output_path, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(recording.tobytes())
    
    file_size = os.path.getsize(output_path)
    print(f"    Saved recording ({file_size} bytes)")
    return True


def send_audio_over_udp(sock, server_addr, wav_path):
    """Read a WAV file and send it as UDP packets to the server."""
    
    # Read raw audio bytes (skip WAV header)
    with wave.open(wav_path, 'rb') as wf:
        raw_audio = wf.readframes(wf.getnframes())
    
    print(f"\n📤  Sending {len(raw_audio)} bytes of audio in {CHUNK_SIZE}-byte chunks...")
    
    # Signal call start
    sock.sendto(b"CALL_START", server_addr)
    
    # Wait briefly for ACK
    try:
        sock.settimeout(3)
        data, _ = sock.recvfrom(1024)
        if data == b"ACK:CALL_START":
            print("    Server acknowledged call.")
    except (socket.timeout, ConnectionResetError, OSError):
        print("    [WARNING] No ACK from server. Make sure udp_server.py is running!")
        print("    Continuing anyway...")
    
    # Send audio chunks
    seq = 0
    for i in range(0, len(raw_audio), CHUNK_SIZE):
        chunk = raw_audio[i:i + CHUNK_SIZE]
        packet = b"AUDIO:" + str(seq).encode() + b":" + chunk
        try:
            sock.sendto(packet, server_addr)
        except (ConnectionResetError, OSError):
            pass  # Ignore Windows UDP reset errors
        seq += 1
        time.sleep(0.001)  # Small delay to avoid packet loss
    
    print(f"    Sent {seq} audio chunks.")
    
    # Signal call end
    try:
        sock.sendto(b"CALL_END", server_addr)
    except (ConnectionResetError, OSError):
        pass
    
    print("    Call ended. Waiting for server response...\n")


def receive_response(sock):
    """Receive the server's text and audio response."""
    sock.settimeout(30)  # Wait up to 30 seconds for the full pipeline
    
    text_response = None
    audio_chunks = []
    
    while True:
        try:
            data, _ = sock.recvfrom(65535)
            
            if data.startswith(b"TEXT:"):
                json_str = data[5:].decode("utf-8")
                text_response = json.loads(json_str)
                
                if "error" in text_response:
                    print(f"❌  Server Error: {text_response['error']}")
                    return None, None
                
                print("─" * 50)
                print(f"📝  Transcript:  {text_response['transcript']}")
                print(f"🌐  Language:    {text_response['detected_language']}")
                print(f"🤖  AI Answer:   {text_response['answer_text']}")
                print("─" * 50)
            
            elif data.startswith(b"RESP_AUDIO:"):
                parts = data.split(b":", 2)
                if len(parts) == 3:
                    seq = int(parts[1])
                    audio_data = parts[2]
                    audio_chunks.append((seq, audio_data))
            
            elif data == b"RESP_DONE":
                print(f"\n✅  Response complete! Received {len(audio_chunks)} audio chunks.")
                break
                
        except socket.timeout:
            print("[TIMEOUT] No response from server within 30 seconds.")
            break
    
    # Reassemble audio
    if audio_chunks:
        audio_chunks.sort(key=lambda x: x[0])
        full_audio = b"".join([c[1] for c in audio_chunks])
        return text_response, full_audio
    
    return text_response, None


def play_audio(audio_bytes, output_path="udp_response.wav"):
    """Save and play the response audio."""
    # Save the raw bytes (it's already a WAV file from the server)
    with open(output_path, "wb") as f:
        f.write(audio_bytes)
    
    print(f"🔊  Playing response audio...")
    
    try:
        import sounddevice as sd
        import soundfile as sf
        
        data, samplerate = sf.read(output_path)
        sd.play(data, samplerate)
        sd.wait()
        print("    Playback complete.")
    except Exception as e:
        print(f"    [WARNING] Could not play audio: {e}")
        print(f"    Audio saved to: {output_path}")
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def main():
    parser = argparse.ArgumentParser(description="UDP Voice Assistant Client")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Server IP address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Server UDP port")
    parser.add_argument("--file", help="Path to a .wav file to send (skip mic recording)")
    args = parser.parse_args()
    
    server_addr = (args.host, args.port)
    
    print("=" * 60)
    print("  UDP Voice Assistant Client (Mock Test)")
    print(f"  Server: {args.host}:{args.port}")
    print("=" * 60)
    
    try:
        while True:
            # Create a fresh socket for every call to prevent reading stale packets
            # from previous calls (which causes audio mixing if packets arrived late!)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            print("\n" + "=" * 60)
            print("  [1] Record from microphone and send")
            print("  [2] Send a WAV file")
            print("  [3] Exit")
            print("=" * 60)
            
            choice = input("  Your choice: ").strip()
            
            if choice == "1":
                temp_wav = "temp_recording.wav"
                if record_from_mic(temp_wav):
                    send_audio_over_udp(sock, server_addr, temp_wav)
                    text_resp, audio_data = receive_response(sock)
                    if audio_data:
                        play_audio(audio_data)
                    if os.path.exists(temp_wav):
                        os.remove(temp_wav)
                        
            elif choice == "2":
                filepath = args.file or input("  Enter WAV file path: ").strip()
                if not os.path.exists(filepath):
                    print(f"  [ERROR] File not found: {filepath}")
                    sock.close()
                    continue
                send_audio_over_udp(sock, server_addr, filepath)
                text_resp, audio_data = receive_response(sock)
                if audio_data:
                    play_audio(audio_data)
                    
            elif choice == "3":
                print("\n👋  Goodbye!")
                sock.close()
                break
            else:
                print("  Invalid choice.")
            
            sock.close()
                
    except KeyboardInterrupt:
        print("\n\n👋  Goodbye!")


if __name__ == "__main__":
    main()
