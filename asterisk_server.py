import socket
import struct
import wave
import json
import os
import uuid
import tempfile
import asyncio
from dotenv import load_dotenv

import random

# Load environment variables (API keys)
load_dotenv()

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

FILLER_AUDIO_8K = None

def load_filler_audio():
    """
    Loads and prepares the filler audio file (8kHz Mono 16-bit signed PCM) at startup.
    """
    global FILLER_AUDIO_8K
    filler_path = "filler.wav"
    if os.path.exists(filler_path):
        try:
            with wave.open(filler_path, "rb") as wf:
                raw_16k = wf.readframes(wf.getnframes())
                FILLER_AUDIO_8K = downsample_16k_to_8k(raw_16k)
            print(f"✅  Loaded and prepared filler audio ({len(FILLER_AUDIO_8K)} bytes, ~{len(FILLER_AUDIO_8K)/16000:.2f}s)")
        except Exception as e:
            print(f"⚠️  Error loading filler audio: {e}")
    else:
        print(f"⚠️  {filler_path} not found. Filler pacing will be disabled.")

async def stream_audio_bytes(raw_8k, writer, write_lock, is_streaming_state):
    """
    Streams raw 8kHz 16-bit signed PCM audio bytes over the AudioSocket.
    Enforces drift-free clock-aligned pacing.
    """
    is_streaming_state[0] = True
    try:
        start_time = asyncio.get_event_loop().time()
        chunk_duration = 0.02  # 20ms of audio per 320-byte chunk
        total_chunks = len(raw_8k) // 320
        
        for idx, i in enumerate(range(0, len(raw_8k), 320)):
            chunk = raw_8k[i:i+320]
            if len(chunk) < 320:
                chunk = chunk + b"\x00" * (320 - len(chunk))
                
            out_header = struct.pack(">BH", 0x10, len(chunk))
            
            async with write_lock:
                try:
                    writer.write(out_header + chunk)
                    await writer.drain()
                except Exception as e:
                    print(f"    [stream_audio_bytes] Connection lost while streaming: {e}")
                    break
                    
            # Calculate expected elapsed time and dynamically sleep to correct any drift/overhead
            expected_elapsed = (idx + 1) * chunk_duration
            actual_elapsed = asyncio.get_event_loop().time() - start_time
            sleep_dur = expected_elapsed - actual_elapsed
            
            if sleep_dur > 0:
                await asyncio.sleep(sleep_dur)
            else:
                # Yield to event loop if lagging, without sleeping
                await asyncio.sleep(0)
    finally:
        is_streaming_state[0] = False

async def run_voice_pipeline(audio_frames, chat_history, lang_code, out_path, wav_path):
    """
    Runs the STT, LLM (Gemini), and TTS (Sarvam) pipeline concurrently.
    """
    try:
        # 1. Save to unique WAV (8kHz, 16-bit, Mono) inside an executor thread
        def save_wav():
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(8000)
                wf.writeframes(audio_frames)
                
        await asyncio.to_thread(save_wav)
        
        # 2. STT via Sarvam
        transcript, detected_lang = await asyncio.to_thread(sarvam_stt, wav_path)
        if not transcript:
            return None, detected_lang
            
        print("─" * 50)
        print(f"📝  User: {transcript}")
        
        # 3. LLM via Gemini
        kb_path = "knowledge_base.json"
        kb = {}
        if os.path.exists(kb_path):
            with open(kb_path, "r") as f:
                kb = json.load(f)
                
        answer = await asyncio.to_thread(get_gemini_response, transcript, chat_history, detected_lang, kb)
        print(f"🤖  AI:   {answer}")
        print("─" * 50)
        
        # Save to history
        chat_history.append({"role": "user", "content": transcript})
        chat_history.append({"role": "assistant", "content": answer})
        
        # 4. TTS via Sarvam
        print("    Generating speech...")
        tts_success = await asyncio.to_thread(sarvam_tts, answer, detected_lang, out_path)
        if tts_success:
            return out_path, detected_lang
    except Exception as e:
        print(f"    [run_voice_pipeline] Error: {e}")
    finally:
        if os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except Exception:
                pass
    return None, lang_code

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
    chat_history = []
    lang_code = "en-IN"
    write_lock = asyncio.Lock()
    
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
        is_streaming_state = [False]
        
        # Background keep-alive task to prevent Asterisk 2-second AudioSocket inactivity timeout (app_audiosocket.c)
        async def keep_alive():
            # Generate pure silence packets (all 0x00) to keep AudioSocket alive
            # while ensuring absolute zero background noise (crystal-clear audio) for the caller.
            comfort_payload = b"\x00" * 320
            comfort_packet = struct.pack(">BH", 0x10, 320) + comfort_payload
            
            try:
                while True:
                    if writer.is_closing():
                        break
                    
                    async with write_lock:
                        if not is_streaming_state[0]:
                            writer.write(comfort_packet)
                            await writer.drain()
                    await asyncio.sleep(0.02) # standard RTP keep-alive every 20ms (50 packets/sec)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"    [keep_alive] Exception: {e}")

        keep_alive_task = asyncio.create_task(keep_alive())
        
        # Continuous background reader task to drain Asterisk's TCP stream.
        # This prevents TCP write buffer saturation on Asterisk during long STT/LLM/TTS operations,
        # completely eliminating premature hangups (connection reset / broken pipe).
        audio_queue = asyncio.Queue()
        
        async def socket_reader():
            try:
                while True:
                    header = await recvall_async(reader, 3)
                    if not header:
                        await audio_queue.put(None)
                        break
                    
                    kind, length = struct.unpack(">BH", header)
                    
                    if kind == 0x00:
                        await audio_queue.put((0x00, b""))
                        break
                    elif kind == 0x10:
                        payload = await recvall_async(reader, length)
                        if not payload:
                            await audio_queue.put(None)
                            break
                        await audio_queue.put((0x10, payload))
                    elif kind == 0xff:
                        payload = await recvall_async(reader, length)
                        if not payload:
                            await audio_queue.put(None)
                            break
                        await audio_queue.put((0xff, payload))
                    else:
                        # Skip unknown frame types safely
                        payload = await recvall_async(reader, length)
            except Exception as e:
                print(f"    [socket_reader] Exception: {e}")
                await audio_queue.put(None)

        reader_task = asyncio.create_task(socket_reader())
        
        SILENCE_THRESHOLD_RMS = 500  # Minimum energy to count as speech (aligned with backup branch)
        MAX_SILENCE_CHUNKS = 75      # 75 chunks of 20ms = 1.5 seconds of silence
        
        print("\n🎧  Listening for audio...")
        
        while True:
            packet = await audio_queue.get()
            if packet is None:
                break
                
            kind, payload = packet
            
            if kind == 0x00:
                print("\n❌  Call hung up by Asterisk.")
                break
                
            elif kind == 0x10:
                # Measure volume using our robust fallback wrapper (removed byteswap to match backup branch)
                rms = get_rms(payload)
                
                frame_count += 1
                if frame_count % 50 == 0:
                    print(f"    [DEBUG] Frame {frame_count}: RMS={rms}, is_recording={is_recording}, silence_frames={silence_frames}, hex={payload[:20].hex()}")
                
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
                    
                    # Store current recorded frames and reset buffers immediately for next turn
                    recorded_frames = bytes(frames)
                    frames.clear()
                    is_recording = False
                    silence_frames = 0
                    
                    # Concurrently launch the voice pipeline task
                    pipeline_task = asyncio.create_task(
                        run_voice_pipeline(recorded_frames, chat_history, lang_code, out_path, wav_path)
                    )
                    
                    # Concurrently stream the filler audio if loaded
                    if FILLER_AUDIO_8K:
                        print("    [Filler] Streaming filler audio concurrently...")
                        await stream_audio_bytes(FILLER_AUDIO_8K, writer, write_lock, is_streaming_state)
                        
                    # Now await the voice pipeline task to finish
                    pipeline_result_path, lang_code = await pipeline_task
                    
                    if pipeline_result_path and os.path.exists(pipeline_result_path):
                        print("    Streaming AI response back to the phone call...")
                        try:
                            def read_and_downsample():
                                with wave.open(pipeline_result_path, "rb") as wf:
                                    raw_16k = wf.readframes(wf.getnframes())
                                    return downsample_16k_to_8k(raw_16k)
                                    
                            raw_8k = await asyncio.to_thread(read_and_downsample)
                            await stream_audio_bytes(raw_8k, writer, write_lock, is_streaming_state)
                        finally:
                            if os.path.exists(pipeline_result_path):
                                try:
                                    os.remove(pipeline_result_path)
                                except Exception:
                                    pass
                    
                    # Reset for the next sentence
                    # Flush any stale audio frames that buffered in the queue while we were thinking/speaking
                    while not audio_queue.empty():
                        try:
                            audio_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                            
                    print("\n🎧  Listening for audio...")
                    frames.clear()
                    is_recording = False
                    silence_frames = 0
                    
            elif kind == 0xff:
                print(f"\n❌  Asterisk Error Code: {payload}")
                break
    except Exception as e:
        print(f"    [ERROR] Exception in call processing: {e}")
    finally:
        # Cancel background tasks cleanly
        reader_task.cancel()
        keep_alive_task.cancel()
        try:
            await asyncio.gather(reader_task, keep_alive_task, return_exceptions=True)
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
    load_filler_audio()
    # Start the async TCP server
    server = await asyncio.start_server(process_call_async, HOST, PORT)
    
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down server.")
