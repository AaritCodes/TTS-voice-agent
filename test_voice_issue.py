import time
import sys
import os
import wave
import socket
import struct
from pyVoIP.VoIP import VoIPPhone, CallState, PhoneStatus
from pyVoIP.SIP import SIPClient
from dotenv import load_dotenv

# Load env variables for API keys
load_dotenv()

# Setup Monkey Patches for pyVoIP to work with IP Auth NeoX trunk
def mock_register(self) -> bool:
    print("[MOCK] Bypassing REGISTER step to support IP-authenticated NeoX trunk.")
    self.phone._status = PhoneStatus.REGISTERED
    return True

def mock_start(self) -> None:
    if self.NSD:
        raise RuntimeError("Attempted to start already started SIPClient")
    self.NSD = True
    import socket
    from threading import Timer
    self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"[MOCK] Binding local socket to 0.0.0.0:{self.myPort} (Header IP is {self.myIP})")
    self.s.bind(('0.0.0.0', self.myPort))
    self.out = self.s
    self.register()
    t = Timer(1, self.recv_loop)
    t.name = "SIP Recieve"
    t.start()

original_invite = SIPClient.invite

def mock_invite(self, number, ms, sendtype):
    print(f"\n[MOCK INVITE] Preparing INVITE for number: {number}")
    print(f"[MOCK INVITE] Destination: {self.server}:{self.port}")
    self.s.settimeout(5.0)  # 5s socket timeout
    try:
        res = original_invite(self, number, ms, sendtype)
        print("----- SENT SIP INVITE PACKET -----")
        print(res[0].raw.decode('utf-8', errors='ignore').strip())
        print("----------------------------------")
        return res
    except Exception as e:
        print(f"[MOCK INVITE] ERROR or Timeout in original_invite: {e}")
        raise

# Apply monkey patches
SIPClient.register = mock_register
SIPClient.start = mock_start
SIPClient.invite = mock_invite

try:
    import audioop
except ImportError:
    audioop = None

def generate_dummy_issue_audio(text, output_path):
    print("--------------------------------------------------")
    print("Step 1: Generating dummy issue audio using Sarvam TTS...")
    print(f"  Text: '{text}'")
    
    # Import locally from api_clients
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from api_clients import sarvam_tts
    
    success = sarvam_tts(text, "en-IN", output_path)
    if success and os.path.exists(output_path):
        print(f"  [SUCCESS] Generated source audio at: {output_path}")
        return True
    else:
        print("  [ERROR] Failed to generate audio using Sarvam TTS.")
        return False

def convert_wav_to_pyvoip_format(wav_path):
    print("\nStep 2: Converting WAV to pyVoIP format (8kHz, 8-bit signed Mono)...")
    if not os.path.exists(wav_path):
        raise FileNotFoundError(f"Source WAV not found: {wav_path}")
        
    with wave.open(wav_path, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw_data = wf.readframes(n_frames)
        print(f"  Source WAV properties: {n_channels} channels, {sampwidth} bytes/sample, {framerate}Hz, {len(raw_data)} raw bytes")
        
    # 1. Downsample 16kHz -> 8000Hz
    if framerate == 16000:
        if audioop is not None:
            raw_8k_16bit, _ = audioop.ratecv(raw_data, sampwidth, n_channels, 16000, 8000, None)
        else:
            # Numpy downsampling fallback
            import numpy as np
            samples = np.frombuffer(raw_data, dtype='<i2')
            downsampled = samples[::2]
            raw_8k_16bit = downsampled.tobytes()
    elif framerate == 8000:
        raw_8k_16bit = raw_data
    else:
        raise ValueError(f"Unsupported framerate: {framerate}")

    # 2. Convert 16-bit (width 2) to 8-bit signed (width 1)
    if audioop is not None:
        raw_8k_8bit = audioop.lin2lin(raw_8k_16bit, 2, 1)
    else:
        # Numpy scaling fallback
        import numpy as np
        samples_16 = np.frombuffer(raw_8k_16bit, dtype='<i2')
        samples_8 = (samples_16 // 256).astype(np.int8)
        raw_8k_8bit = samples_8.tobytes()
        
    print(f"  [SUCCESS] Converted to pyVoIP format: {len(raw_8k_8bit)} bytes (approx {len(raw_8k_8bit)/8000:.2f} seconds)")
    return raw_8k_8bit

def save_recorded_audio(recorded_data, output_path):
    print(f"\nStep 4: Saving recorded bot response to {output_path}...")
    if not recorded_data:
        print("  [WARNING] No recorded audio data to save.")
        return
        
    if audioop is not None:
        raw_16bit = audioop.lin2lin(recorded_data, 1, 2)
    else:
        # Numpy scaling fallback
        import numpy as np
        samples_8 = np.frombuffer(recorded_data, dtype=np.int8)
        samples_16 = (samples_8.astype(np.int16) * 256).astype('<i2')
        raw_16bit = samples_16.tobytes()
        
    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(8000)  # 8kHz
        wf.writeframes(raw_16bit)
    print(f"  [SUCCESS] Saved WAV file at: {output_path} ({len(recorded_data)} bytes recorded)")

def main():
    print("==================================================")
    print("pyVoIP Audio Testing: Voice Note Injection & Recording")
    print("==================================================")
    
    # Use localhost if running on Linux/VM to bypass NAT/firewalls entirely
    import sys
    if sys.platform == "linux" or sys.platform == "linux2":
        server_ip = "127.0.0.1"
    else:
        server_ip = "34.55.229.163"
    server_port = 5060
    destination = "100"
    
    # Files paths
    dummy_wav = "dummy_issue.wav"
    bot_response_wav = "bot_response.wav"
    
    # 1. Generate Voice Note
    issue_text = "Hello, my name is Arvind. I am calling because my Brother printer is not printing properly. It is showing a paper jam error. The machine serial number is BR987654. Can you please help me register a complaint and send an onsite engineer?"
    if not generate_dummy_issue_audio(issue_text, dummy_wav):
        sys.exit(1)
        
    # 2. Convert Voice Note to pyVoIP Format
    issue_pcm_bytes = convert_wav_to_pyvoip_format(dummy_wav)
    
    # 3. Detect Outbound IP and Allocate Local SIP Port
    def get_local_ip(target_ip, target_port):
        temp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        temp_sock.connect((target_ip, target_port))
        local_ip = temp_sock.getsockname()[0]
        temp_sock.close()
        return local_ip

    def find_free_port():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(('0.0.0.0', 0))
        port = s.getsockname()[1]
        s.close()
        return port

    local_ip = get_local_ip(server_ip, server_port)
    local_sip_port = find_free_port()
    print(f"\nStep 3: Network Initialization")
    print(f"  Detected local outbound IP: {local_ip}")
    print(f"  Allocated free local SIP port: {local_sip_port}")
    
    # Initialize Phone Client
    phone = VoIPPhone(
        server_ip,
        server_port,
        "microsip",
        "secretpassword",
        myIP=local_ip,
        callCallback=None,
        sipPort=local_sip_port
    )
    
    print("\nStarting VoIPPhone service and registering...")
    phone.start()
    
    sip_uri = f"sip:{destination}@{server_ip}:{server_port}"
    print(f"Placing outbound call via pyVoIP to: {sip_uri}")
    
    recorded_audio_buffer = bytearray()
    
    try:
        call = phone.call(destination)
        
        # Wait for answer
        timeout = 15
        start_time = time.time()
        call_answered = False
        
        while time.time() - start_time < timeout:
            if call.state == CallState.ANSWERED:
                print("  [SUCCESS] Call answered by Asterisk voice bot!")
                call_answered = True
                break
            elif call.state == CallState.ENDED:
                print("  [INFO] Call ended before being answered.")
                break
            time.sleep(0.2)
            
        if call_answered:
            # A. STREAM DUMMY ISSUE VOICE NOTE
            print("\nStreaming dummy issue voice note...")
            chunk_size = 160  # 20ms chunks of 8kHz 8-bit audio
            stream_start = time.time()
            
            for i in range(0, len(issue_pcm_bytes), chunk_size):
                if call.state != CallState.ANSWERED:
                    print("  [WARNING] Call ended during streaming.")
                    break
                    
                chunk = issue_pcm_bytes[i:i+chunk_size]
                if len(chunk) < chunk_size:
                    chunk = chunk + b"\x00" * (chunk_size - len(chunk))
                    
                # Send frame
                call.write_audio(chunk)
                
                # Drain/Discard incoming audio while we are speaking (we don't expect the bot to interrupt)
                incoming = call.read_audio(blocking=False)
                if incoming:
                    recorded_audio_buffer.extend(incoming)
                    
                # Wait 20ms to pace G.711 stream
                time.sleep(0.02)
                
            print(f"  [SUCCESS] Voice note streaming complete ({time.time() - stream_start:.2f} seconds elapsed).")
            
            # B. LISTEN FOR BOT RESPONSE
            print("\nListening for Asterisk/AI voice bot response (15 seconds)...")
            listen_start = time.time()
            last_active_time = time.time()
            silent_chunk = b"\x00" * chunk_size
            
            active_packets = 0
            
            # Record for up to 15 seconds or until call ends
            while time.time() - listen_start < 15.0:
                if call.state != CallState.ANSWERED:
                    print("\n  [INFO] Call disconnected by remote party.")
                    break
                    
                # Stream silence so the bot receives silence and can speak
                call.write_audio(silent_chunk)
                
                # Read incoming audio
                incoming = call.read_audio(blocking=False)
                if incoming:
                    recorded_audio_buffer.extend(incoming)
                    
                    # Check if the incoming packet is active audio (non-silent)
                    # For signed 8-bit PCM, 0 is silence. For pyVoIP empty/missing RTP, 0x80 is returned.
                    is_silent = all(b == 0 or b == 0x80 for b in incoming)
                    if not is_silent:
                        active_packets += 1
                        if active_packets % 10 == 0:
                            sys.stdout.write(".")
                            sys.stdout.flush()
                            last_active_time = time.time()
                
                # Pace loop at 20ms
                time.sleep(0.02)
                
            print(f"\n  [INFO] Listening phase finished. Total active packets received: {active_packets}")
            
            print("\nDemanding call hangup...")
            call.hangup()
            
    except Exception as e:
        print(f"  [ERROR] Execution encountered exception: {e}")
    finally:
        print("\nStopping VoIPPhone service...")
        try:
            phone.stop()
        except Exception as stop_error:
            print(f"  [WARNING] Error during phone.stop(): {stop_error}")
            
        # 4. Save response to WAV file
        if len(recorded_audio_buffer) > 0:
            save_recorded_audio(bytes(recorded_audio_buffer), bot_response_wav)
            
        print("==================================================")
        print("Execution Complete. Forcing process exit.")
        print("==================================================")
        import os
        os._exit(0)

if __name__ == "__main__":
    main()
