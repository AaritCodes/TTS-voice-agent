import socket
import struct
import audioop
import wave
import json
import time
import os

from api_clients import setup_gemini, get_gemini_response, sarvam_stt, sarvam_tts

setup_gemini()

HOST = '0.0.0.0'
PORT = 9090

def recvall(sock, n):
    data = bytearray()
    while len(data) < n:
        try:
            packet = sock.recv(n - len(data))
            if not packet:
                return None
            data.extend(packet)
        except Exception:
            return None
    return data

def process_call(conn, addr):
    print(f"==========================================")
    print(f"📞  Asterisk AudioSocket Connected: {addr}")
    print(f"==========================================")
    
    # Read the initial UUID packet (type 0x01)
    header = recvall(conn, 3)
    if not header: return
    kind, length = struct.unpack(">BH", header)
    if kind == 0x01:
        call_id_bytes = recvall(conn, length)
        # Asterisk sends 16-byte UUID
        call_id = call_id_bytes.hex()
        print(f"    Call ID: {call_id}")
    
    frames = bytearray()
    silence_frames = 0
    is_recording = False
    
    SILENCE_THRESHOLD_RMS = 500  # Minimum energy to count as speech
    MAX_SILENCE_CHUNKS = 75      # 75 chunks of 20ms = 1.5 seconds of silence
    
    print("\n🎧  Listening for audio...")
    
    while True:
        header = recvall(conn, 3)
        if not header: break
        
        kind, length = struct.unpack(">BH", header)
        
        if kind == 0x00:
            print("\n❌  Call hung up by Asterisk.")
            break
            
        elif kind == 0x10:
            # Incoming Audio
            payload = recvall(conn, length)
            if not payload: break
            
            # Measure volume
            rms = audioop.rms(payload, 2)
            
            if rms > SILENCE_THRESHOLD_RMS:
                if not is_recording:
                    print("\n🗣️  Speech detected! Recording...")
                is_recording = True
                silence_frames = 0
            else:
                if is_recording:
                    silence_frames += 1
            
            if is_recording:
                frames.extend(payload)
                
            # If we were recording and silence has lasted for 1.5 seconds, process it
            if is_recording and silence_frames > MAX_SILENCE_CHUNKS:
                print(f"    Silence detected. Processing {len(frames)} bytes of audio...")
                
                # 1. Save to WAV (8kHz, 16-bit, Mono)
                wav_path = "incoming.wav"
                with wave.open(wav_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(8000)
                    wf.writeframes(frames)
                
                # 2. STT via Sarvam
                transcript, lang_code = sarvam_stt(wav_path)
                print("─" * 50)
                print(f"📝  User: {transcript}")
                
                if transcript:
                    # 3. LLM via Gemini
                    kb_path = "knowledge_base.json"
                    kb = {}
                    if os.path.exists(kb_path):
                        with open(kb_path, "r") as f:
                            kb = json.load(f)
                            
                    answer = get_gemini_response(transcript, [], lang_code, kb)
                    print(f"🤖  AI:   {answer}")
                    print("─" * 50)
                    
                    # 4. TTS via Sarvam
                    out_path = "outgoing.wav"
                    print("    Generating speech...")
                    if sarvam_tts(answer, lang_code, out_path):
                        # 5. Downsample and Stream Back to Asterisk
                        print("    Streaming AI response back to the phone call...")
                        with wave.open(out_path, "rb") as wf:
                            raw_16k = wf.readframes(wf.getnframes())
                            # Convert Sarvam's 16kHz to Asterisk's 8kHz requirement
                            raw_8k, _ = audioop.ratecv(raw_16k, 2, 1, 16000, 8000, None)
                            
                            # Stream in small 320-byte chunks to prevent buffering issues
                            for i in range(0, len(raw_8k), 320):
                                chunk = raw_8k[i:i+320]
                                out_header = struct.pack(">BH", 0x10, len(chunk))
                                try:
                                    conn.sendall(out_header + chunk)
                                except Exception as e:
                                    print(f"    [ERROR] Connection lost while streaming: {e}")
                                    break
                                time.sleep(0.015) # Pace the audio slightly to match real-time
                
                # Reset for the next sentence
                print("\n🎧  Listening for audio...")
                frames.clear()
                is_recording = False
                silence_frames = 0
                
        elif kind == 0xff:
            print(f"\n❌  Asterisk Error Code: {recvall(conn, length)}")
            break

def main():
    print(f"Starting Asterisk AudioSocket Server on {HOST}:{PORT}")
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    
    try:
        while True:
            conn, addr = server.accept()
            process_call(conn, addr)
            conn.close()
    except KeyboardInterrupt:
        print("\nShutting down server.")
    finally:
        server.close()

if __name__ == "__main__":
    main()
