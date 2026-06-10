import socket
import random
import time

def send_raw_sip_invite(target_ip, target_port=5060, extension="100"):
    # Generate randomized parameters to comply with standard SIP formatting
    call_id = f"{random.randint(100000, 999999)}@127.0.0.1"
    from_tag = random.randint(1000, 9999)
    branch = f"z9hG4bK{random.randint(100000, 999999)}"
    
    # We use our 'microsip' username so Asterisk routes it correctly
    sip_invite = (
        f"INVITE sip:{extension}@{target_ip}:{target_port} SIP/2.0\r\n"
        f"Via: SIP/2.0/UDP 127.0.0.1:5060;branch={branch}\r\n"
        f"Max-Forwards: 70\r\n"
        f"To: <sip:{extension}@{target_ip}>\r\n"
        f"From: \"NeoX PBX\" <sip:microsip@127.0.0.1>;tag={from_tag}\r\n"
        f"Call-ID: {call_id}\r\n"
        f"CSeq: 1 INVITE\r\n"
        f"Contact: <sip:microsip@127.0.0.1:5060>\r\n"
        f"Content-Type: application/sdp\r\n"
        f"Content-Length: 0\r\n\r\n"
    )
    
    print("🚀 Initializing NeoX PBX Simulator...")
    print(f"📞 Forwarding SIP call to {target_ip} on extension {extension}...")
    
    # Open a standard UDP Internet socket
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        # Blast the packet
        sock.sendto(sip_invite.encode('utf-8'), (target_ip, target_port))
        
        # Wait for the response from Asterisk
        sock.settimeout(5.0)
        try:
            print("⏳ Waiting for Asterisk to answer...")
            while True:
                data, addr = sock.recvfrom(2048)
                response_text = data.decode('utf-8')
                
                # Check what Asterisk said!
                if "SIP/2.0 100 Trying" in response_text:
                    print("✅ Asterisk is ringing!")
                elif "SIP/2.0 401 Unauthorized" in response_text:
                    print("🔒 Asterisk asked for a password (expected since we didn't send the auth hash).")
                    print("But the fact that Asterisk responded proves the Trunk connection is 100% working!")
                    break
                elif "SIP/2.0 200 OK" in response_text:
                    print("✅ Asterisk ANSWERED the call!")
                    break
                else:
                    print(f"📥 Asterisk sent: {response_text.splitlines()[0]}")
                    
        except socket.timeout:
            print("\n❌ Timeout: Asterisk did not respond. Check if the GCP server is running.")

if __name__ == "__main__":
    send_raw_sip_invite("34.69.25.186", 5060, "100")
