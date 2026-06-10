import socket
import struct
import wave
import json
import time
import os
import threading
import uuid
import tempfile

try:
    import audioop
except ImportError:
    audioop = None

from api_clients import setup_gemini, get_gemini_response, sarvam_stt, sarvam_tts

setup_gemini()

# Host and Port Configuration
# Bind to 127.0.0.1 for security, as Asterisk resides on the same VM and connects locally.
HOST = '127.0.0.1'
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

def get_rms(payload):
    """
    Calculate the Root Mean Square (RMS) of a 16-bit signed PCM payload.
    Provides a PEP 594 compliant fallback when audioop is deprecated/removed (Python 3.13+).
    """
    if audioop is not None:
        try:
            return audioop.rms(payload, 2)
        except Exception:
            pass

    # Fast numpy-based fallback
    try:
        import numpy as np
        samples = np.frombuffer(payload, dtype='>i2') # AudioSocket PCM is 16-bit big-endian
        return int(np.sqrt(np.mean(samples.astype(np.float64)**2)))
    except Exception:
        # Pure Python fallback
        count = len(payload) // 2
        if count == 0:
            return 0
        samples = struct.unpack(f">{count}h", payload)
        sum_squares = sum(s * s for s in samples)
        return int((sum_squares / count) ** 0.5)

def downsample_16k_to_8k(raw_16k):
    """
    Downsamples 16kHz 16-bit Mono PCM audio to 8kHz.
    Provides a PEP 594 compliant fallback when audioop is deprecated/removed (Python 3.13+).
    """
    if audioop is not None:
        try:
            raw_8k, _ = audioop.ratecv(raw_16k, 2, 1, 16000, 8000, None)
            return raw_8k
        except Exception:
            pass

    # Fast numpy-based fallback
    try:
        import numpy as np
        samples = np.frombuffer(raw_16k, dtype='<i2') # WAV standard is little-endian
        downsampled = samples[::2]
        return downsampled.tobytes()
    except Exception:
        # Extremely fast pure-Python slicing fallback
        out = bytearray(len(raw_16k) // 2)
        out[0::2] = raw_16k[0::4]
        out[1::2] = raw_16k[1::4]
        return bytes(out)

def process_call(conn, addr):
    print(f"==========================================")
    print(f"📞  Asterisk AudioSocket Connected: {addr}")
    print(f"==========================================")
    
    # Generate unique paths for session WAV files to prevent multi-threaded data collisions/overwrites
    session_id = str(uuid.uuid4())
    wav_path = os.path.join(tempfile.gettempdir(), f"incoming_{session_id}.wav")
    out_path = os.path.join(tempfile.gettempdir(), f"outgoing_{session_id}.wav")
    
    try:
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
                
                # Measure volume using our robust fallback wrapper
                rms = get_rms(payload)
                
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
                    
                    try:
                        # 1. Save to unique WAV (8kHz, 16-bit, Mono)
                        with wave.open(wav_path, "wb") as wf:
                            wf.setnchannels(1)
                            wf.setsampwidth(2)
                            wf.setframerate(8000)
                            wf.writeframes(frames)
                        
                        # 2. STT via Sarvam
                        transcript, lang_code = sarvam_stt(wav_path)
                    finally:
                        # Immediately remove temp incoming file
                        if os.path.exists(wav_path):
                            try:
                                os.remove(wav_path)
                            except Exception:
                                pass
                                
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
                        print("    Generating speech...")
                        try:
                            if sarvam_tts(answer, lang_code, out_path):
                                # 5. Downsample and Stream Back to Asterisk
                                print("    Streaming AI response back to the phone call...")
                                with wave.open(out_path, "rb") as wf:
                                    raw_16k = wf.readframes(wf.getnframes())
                                    
                                    # Downsample from 16kHz to 8kHz with our robust fallback Downsampler
                                    raw_8k = downsample_16k_to_8k(raw_16k)
                                    
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
                        finally:
                            # Immediately remove temp outgoing file
                            if os.path.exists(out_path):
                                try:
                                    os.remove(out_path)
                                except Exception:
                                    pass
                    
                    # Reset for the next sentence
                    print("\n🎧  Listening for audio...")
                    frames.clear()
                    is_recording = False
                    silence_frames = 0
                    
            elif kind == 0xff:
                print(f"\n❌  Asterisk Error Code: {recvall(conn, length)}")
                break
    except Exception as e:
        print(f"    [ERROR] Exception in call processing: {e}")
    finally:
        # Guarantee resource cleanup and socket closure
        try:
            conn.close()
        except Exception:
            pass
        print(f"🔌  Connection closed for {addr}")

def main():
    print(f"Starting Asterisk AudioSocket Server on {HOST}:{PORT}")
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(10) # Backlog up to 10 connections
    
    try:
        while True:
            conn, addr = server.accept()
            # Handle each connection in a separate thread for full concurrent calling
            client_thread = threading.Thread(target=process_call, args=(conn, addr))
            client_thread.daemon = True
            client_thread.start()
    except KeyboardInterrupt:
        print("\nShutting down server.")
    finally:
        server.close()

if __name__ == "__main__":
    main()
