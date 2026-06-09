"""
UDP Voice Assistant Server
==========================
This server listens for incoming audio over UDP (simulating a VoIP call),
processes it through the STT → Gemini → TTS pipeline, and streams the
response audio back to the caller over UDP.

Protocol:
  Client → Server:
    b'CALL_START'           → Signals a new call
    b'AUDIO:<seq>:<data>'   → Audio chunk with sequence number
    b'CALL_END'             → Signals end of audio / user done speaking

  Server → Client:
    b'TEXT:<json>'           → JSON with transcript + answer
    b'RESP_AUDIO:<seq>:<data>' → Response audio chunk
    b'RESP_DONE'             → All audio chunks sent

Usage:
    python udp_server.py
    (Listens on 0.0.0.0:5000 by default)
"""

import socket
import os
import json
import wave
import struct
import base64
import tempfile
import threading
import time
import psutil
from dotenv import load_dotenv
from api_clients import setup_gemini, get_gemini_response, sarvam_stt, sarvam_tts

# ─── CONFIG ──────────────────────────────────────────
HOST = "0.0.0.0"       # Listen on all interfaces
PORT = 8000             # UDP port
CHUNK_SIZE = 4096       # Max audio bytes per UDP packet
SAMPLE_RATE = 16000     # Expected sample rate from client
CHANNELS = 1            # Mono audio
SAMPLE_WIDTH = 2        # 16-bit PCM

# ─── INIT ────────────────────────────────────────────
load_dotenv()
setup_gemini()

# Load knowledge base
def load_knowledge_base():
    try:
        with open("knowledge_base.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

kb = load_knowledge_base()
chat_histories = {}  # Per-caller chat history, keyed by (ip, port)

LANGUAGE_MAP = {
    "en-IN": "en-IN", "hi-IN": "hi-IN", "kn-IN": "kn-IN",
    "ta-IN": "ta-IN", "te-IN": "te-IN", "ml-IN": "ml-IN",
    "mr-IN": "mr-IN", "bn-IN": "bn-IN", "gu-IN": "gu-IN",
    "pa-IN": "pa-IN", "or-IN": "or-IN"
}


def save_chunks_to_wav(chunks, filepath):
    """Reassemble received audio chunks into a proper WAV file."""
    # Sort by sequence number
    chunks.sort(key=lambda x: x[0])
    raw_audio = b"".join([c[1] for c in chunks])
    
    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(raw_audio)
    
    return filepath


def process_call(sock, caller_addr, audio_chunks):
    """Process a complete call: STT → Gemini → TTS → send response back."""
    start_time = time.time()
    caller_id = f"{caller_addr[0]}:{caller_addr[1]}"
    print(f"\n[CALL] Processing call from {caller_id} ({len(audio_chunks)} chunks received)")
    
    # Get or create chat history for this caller
    if caller_addr not in chat_histories:
        chat_histories[caller_addr] = []
    history = chat_histories[caller_addr]
    
    # Save audio chunks to a temporary WAV file
    input_path = os.path.join(tempfile.gettempdir(), f"udp_input_{caller_id.replace(':', '_')}.wav")
    output_path = os.path.join(tempfile.gettempdir(), f"udp_output_{caller_id.replace(':', '_')}.wav")
    
    try:
        # ── STEP 1: Reassemble WAV ──
        save_chunks_to_wav(audio_chunks, input_path)
        print(f"[CALL] Audio saved ({os.path.getsize(input_path)} bytes)")
        
        # ── STEP 2: Speech-to-Text ──
        print(f"[CALL] Running STT...")
        transcript, lang_code = sarvam_stt(input_path)
        if not transcript:
            error_msg = json.dumps({"error": "Could not understand audio"})
            sock.sendto(b"TEXT:" + error_msg.encode(), caller_addr)
            sock.sendto(b"RESP_DONE", caller_addr)
            return
        
        print(f"[CALL] User said: '{transcript}' (Language: {lang_code})")
        
        # ── STEP 3: Gemini LLM ──
        mapped_lang = LANGUAGE_MAP.get(lang_code, "en-IN")
        print(f"[CALL] Querying Gemini...")
        answer = get_gemini_response(transcript, history, mapped_lang, kb)
        print(f"[CALL] Gemini says: '{answer}'")
        
        # Update conversation memory
        history.append({"role": "user", "content": transcript})
        history.append({"role": "assistant", "content": answer})
        
        # ── STEP 4: Send text response ──
        text_response = json.dumps({
            "transcript": transcript,
            "detected_language": lang_code,
            "answer_text": answer
        }, ensure_ascii=False)
        sock.sendto(b"TEXT:" + text_response.encode("utf-8"), caller_addr)
        
        # ── STEP 5: Text-to-Speech ──
        print(f"[CALL] Generating TTS audio...")
        if sarvam_tts(answer, mapped_lang, output_path):
            # Read the generated audio and send it back in chunks
            with open(output_path, "rb") as f:
                audio_data = f.read()
            
            # Send audio in chunks
            seq = 0
            for i in range(0, len(audio_data), CHUNK_SIZE):
                chunk = audio_data[i:i + CHUNK_SIZE]
                packet = b"RESP_AUDIO:" + str(seq).encode() + b":" + chunk
                sock.sendto(packet, caller_addr)
                seq += 1
            
            print(f"[CALL] Sent {seq} audio chunks back to {caller_id}")
        else:
            print(f"[CALL] TTS failed")
        
        # Signal end of response
        sock.sendto(b"RESP_DONE", caller_addr)
        print(f"[CALL] Call complete for {caller_id}")
        
        # ── STEP 6: Server Metrics ──
        end_time = time.time()
        latency = round(end_time - start_time, 2)
        # Call cpu_percent() without blocking to get current instantaneous usage
        cpu_usage = psutil.cpu_percent(interval=None)
        ram_usage = psutil.virtual_memory().percent
        
        print("\n" + "─" * 50)
        print(f"📊 SERVER METRICS FOR CALL: {caller_id}")
        print(f"   ⏱️  Pipeline Latency: {latency} seconds")
        print(f"   🧠 Server CPU Usage:   {cpu_usage}%")
        print(f"   💾 Server RAM Usage:   {ram_usage}%")
        print("─" * 50 + "\n")
        
    except Exception as e:
        print(f"[ERROR] Processing failed: {e}")
        error_msg = json.dumps({"error": str(e)})
        sock.sendto(b"TEXT:" + error_msg.encode(), caller_addr)
        sock.sendto(b"RESP_DONE", caller_addr)
    finally:
        # Cleanup temp files
        for path in [input_path, output_path]:
            if os.path.exists(path):
                os.remove(path)


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((HOST, PORT))
    print(f"=" * 60)
    print(f"  UDP Voice Assistant Server")
    print(f"  Listening on {HOST}:{PORT}")
    print(f"  Waiting for incoming calls...")
    print(f"=" * 60)
    
    # Track active calls: { caller_addr: [audio_chunks] }
    active_calls = {}
    
    while True:
        try:
            data, addr = sock.recvfrom(65535)
            
            if data == b"CALL_START":
                print(f"\n[NEW CALL] Incoming call from {addr[0]}:{addr[1]}")
                active_calls[addr] = []
                sock.sendto(b"ACK:CALL_START", addr)
            
            elif data.startswith(b"AUDIO:"):
                if addr in active_calls:
                    # Parse: AUDIO:<seq_number>:<audio_bytes>
                    parts = data.split(b":", 2)  # Split into 3 parts max
                    if len(parts) == 3:
                        seq = int(parts[1])
                        audio_data = parts[2]
                        active_calls[addr].append((seq, audio_data))
            
            elif data == b"CALL_END":
                if addr in active_calls:
                    chunks = active_calls.pop(addr)
                    print(f"[CALL END] {addr[0]}:{addr[1]} sent {len(chunks)} audio chunks")
                    
                    # Process in a separate thread so server stays responsive
                    thread = threading.Thread(
                        target=process_call,
                        args=(sock, addr, chunks)
                    )
                    thread.start()
            
        except KeyboardInterrupt:
            print("\n[SERVER] Shutting down...")
            break
        except Exception as e:
            print(f"[ERROR] {e}")
    
    sock.close()


if __name__ == "__main__":
    main()
