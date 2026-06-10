import socket
import struct
import wave
import json
import os
import uuid
import tempfile
import asyncio

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

async def recvall_async(reader, n):
    """
    Asynchronously and safely read exactly n bytes from the stream reader.
    """
    try:
        data = await reader.readexactly(n)
        return data
    except Exception:
        return None

def get_rms(payload):
    """
    Calculate the Root Mean Square (RMS) of a 16-bit signed PCM payload (little-endian).
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
        samples = np.frombuffer(payload, dtype='<i2') # Swapped to little-endian natively
        return int(np.sqrt(np.mean(samples.astype(np.float64)**2)))
    except Exception:
        # Pure Python fallback
        count = len(payload) // 2
        if count == 0:
            return 0
        samples = struct.unpack(f"<{count}h", payload)
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

async def process_call_async(reader, writer):
    """
    Asynchronous connection handler for Asterisk AudioSocket connections.
    Uses cooperative task scheduling, eliminating heavy thread structures.
    """
    addr = writer.get_extra_info('peername')
    print(f"==========================================")
    print(f"📞  Asterisk AudioSocket Connected (Async): {addr}")
    print(f"==========================================")
    
    # Generate unique paths for session WAV files to prevent data collisions/overwrites
    session_id = str(uuid.uuid4())
    wav_path = os.path.join(tempfile.gettempdir(), f"incoming_{session_id}.wav")
    out_path = os.path.join(tempfile.gettempdir(), f"outgoing_{session_id}.wav")
    
    try:
        # Read the initial UUID packet (type 0x01)
        header = await recvall_async(reader, 3)
        if not header: return
        kind, length = struct.unpack(">BH", header)
        if kind == 0x01:
            call_id_bytes = await recvall_async(reader, length)
            if not call_id_bytes: return
            # Asterisk sends 16-byte UUID
            call_id = call_id_bytes.hex()
            print(f"    Call ID: {call_id}")
        
        frames = bytearray()
        silence_frames = 0
        frame_count = 0
        is_recording = False
        is_streaming_response = False
        
        # Background keep-alive task to prevent Asterisk 2-second AudioSocket inactivity timeout (app_audiosocket.c)
        async def keep_alive():
            silence_payload = b"\x00" * 320
            silence_header = struct.pack(">BH", 0x10, len(silence_payload))
            silence_packet = silence_header + silence_payload
            try:
                while True:
                    if writer.is_closing():
                        break
                    if not is_streaming_response:
                        writer.write(silence_packet)
                        await writer.drain()
                    await asyncio.sleep(0.1) # comfort keep-alive every 100ms
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"    [keep_alive] Exception: {e}")

        keep_alive_task = asyncio.create_task(keep_alive())
        
        SILENCE_THRESHOLD_RMS = 500  # Minimum energy to count as speech
        MAX_SILENCE_CHUNKS = 75      # 75 chunks of 20ms = 1.5 seconds of silence
        
        print("\n🎧  Listening for audio...")
        
        while True:
            header = await recvall_async(reader, 3)
            if not header: break
            
            kind, length = struct.unpack(">BH", header)
            
            if kind == 0x00:
                print("\n❌  Call hung up by Asterisk.")
                break
                
            elif kind == 0x10:
                # Incoming Audio
                payload = await recvall_async(reader, length)
                if not payload: break
                
                # Swap big-endian AudioSocket PCM to native little-endian (wave/audioop/STT standard)
                if audioop is not None:
                    payload = audioop.byteswap(payload, 2)
                else:
                    import numpy as np
                    samples = np.frombuffer(payload, dtype='>i2')
                    payload = samples.astype('<i2').tobytes()
                
                # Measure volume using our robust fallback wrapper
                rms = get_rms(payload)
                
                frame_count += 1
                if frame_count % 50 == 0:
                    print(f"    [DEBUG] Frame {frame_count}: RMS={rms}, is_recording={is_recording}, silence_frames={silence_frames}")
                
                if rms > SILENCE_THRESHOLD_RMS:
                    if not is_recording:
                        print(f"\n🗣️  Speech detected! (RMS={rms}) Recording...")
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
                        # 1. Save to unique WAV (8kHz, 16-bit, Mono) inside an executor thread
                        def save_wav():
                            with wave.open(wav_path, "wb") as wf:
                                wf.setnchannels(1)
                                wf.setsampwidth(2)
                                wf.setframerate(8000)
                                wf.writeframes(frames)
                                
                        await asyncio.to_thread(save_wav)
                        
                        # 2. STT via Sarvam (blocking network operation offloaded to thread)
                        transcript, lang_code = await asyncio.to_thread(sarvam_stt, wav_path)
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
                        # 3. LLM via Gemini (blocking network operation offloaded to thread)
                        kb_path = "knowledge_base.json"
                        kb = {}
                        if os.path.exists(kb_path):
                            with open(kb_path, "r") as f:
                                kb = json.load(f)
                                
                        answer = await asyncio.to_thread(get_gemini_response, transcript, [], lang_code, kb)
                        print(f"🤖  AI:   {answer}")
                        print("─" * 50)
                        
                        # 4. TTS via Sarvam (blocking network operation offloaded to thread)
                        print("    Generating speech...")
                        try:
                            tts_success = await asyncio.to_thread(sarvam_tts, answer, lang_code, out_path)
                            if tts_success:
                                # 5. Downsample and Stream Back to Asterisk
                                print("    Streaming AI response back to the phone call...")
                                is_streaming_response = True
                                try:
                                    def read_and_downsample():
                                        with wave.open(out_path, "rb") as wf:
                                            raw_16k = wf.readframes(wf.getnframes())
                                            return downsample_16k_to_8k(raw_16k)
                                            
                                    raw_8k = await asyncio.to_thread(read_and_downsample)
                                    
                                    # Stream in small 320-byte chunks to prevent buffering issues
                                    for i in range(0, len(raw_8k), 320):
                                        chunk = raw_8k[i:i+320]
                                        
                                        # Swap little-endian PCM chunk back to big-endian for AudioSocket
                                        if audioop is not None:
                                            chunk_be = audioop.byteswap(chunk, 2)
                                        else:
                                            import numpy as np
                                            samples = np.frombuffer(chunk, dtype='<i2')
                                            chunk_be = samples.astype('>i2').tobytes()
                                            
                                        out_header = struct.pack(">BH", 0x10, len(chunk_be))
                                        try:
                                            writer.write(out_header + chunk_be)
                                            await writer.drain() # Wait for non-blocking socket buffer write
                                        except Exception as e:
                                            print(f"    [ERROR] Connection lost while streaming: {e}")
                                            break
                                        await asyncio.sleep(0.015) # Non-blocking cooperative delay
                                finally:
                                    is_streaming_response = False
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
                err_payload = await recvall_async(reader, length)
                print(f"\n❌  Asterisk Error Code: {err_payload}")
                break
    except Exception as e:
        print(f"    [ERROR] Exception in call processing: {e}")
    finally:
        # Cancel the keep-alive background task
        keep_alive_task.cancel()
        try:
            await keep_alive_task
        except Exception:
            pass
            
        # Guarantee connection shutdown and cleanup
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
        print(f"🔌  Connection closed for {addr}")

async def main():
    print(f"Starting Asterisk AudioSocket Server (Asyncio) on {HOST}:{PORT}")
    # Start the async TCP server
    server = await asyncio.start_server(process_call_async, HOST, PORT)
    
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down server.")
