import socket
import random
import time
import argparse
import sys

def generate_sip_invite(target_ip, target_port, extension, local_ip, local_port):
    """
    Generates a RFC-compliant SIP INVITE packet.
    Using standard headers keeps GCP IDS/firewalls from marking it as a malformed attack vector.
    """
    call_id = f"{random.randint(100000, 999999)}@{local_ip}"
    from_tag = random.randint(10000, 99999)
    branch = f"z9hG4bK{random.randint(1000000, 9999999)}"
    
    sip_invite = (
        f"INVITE sip:{extension}@{target_ip}:{target_port} SIP/2.0\r\n"
        f"Via: SIP/2.0/UDP {local_ip}:{local_port};branch={branch}\r\n"
        f"Max-Forwards: 70\r\n"
        f"To: <sip:{extension}@{target_ip}:{target_port}>\r\n"
        f"From: \"NeoX PBX Test\" <sip:microsip@{local_ip}>;tag={from_tag}\r\n"
        f"Call-ID: {call_id}\r\n"
        f"CSeq: 1 INVITE\r\n"
        f"Contact: <sip:microsip@{local_ip}:{local_port}>\r\n"
        f"Content-Type: application/sdp\r\n"
        f"Content-Length: 0\r\n\r\n"
    )
    return sip_invite

def test_udp_sip_calling(target_ip, target_port, extension, timeout):
    # Establish a UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    
    try:
        # Bind locally to let OS allocate an ephemeral port, then discover it
        sock.bind(('0.0.0.0', 0))
        local_ip = "127.0.0.1"
        try:
            # Quick trick to find out active outbound IP
            temp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            temp_sock.connect((target_ip, target_port))
            local_ip = temp_sock.getsockname()[0]
            temp_sock.close()
        except Exception:
            pass
            
        local_port = sock.getsockname()[1]
        
        print("\n==================================================")
        print(">>> NeoX PBX UDP IP Call Simulator <<<")
        print("==================================================")
        print(f"Local Binding   : {local_ip}:{local_port}")
        print(f"Target Asterisk : {target_ip}:{target_port}")
        print(f"Target Extension: {extension}")
        print("-" * 50)
        
        # 1. Send SIP INVITE
        sip_packet = generate_sip_invite(target_ip, target_port, extension, local_ip, local_port)
        print("Sending SIP INVITE UDP packet...")
        sock.sendto(sip_packet.encode('utf-8'), (target_ip, target_port))
        
        # 2. Wait and process response from Asterisk
        print("Waiting for Asterisk PBX response...")
        start_time = time.time()
        
        while True:
            # Avoid infinite loop
            if time.time() - start_time > timeout:
                print("[-] Testing Timeout: No response within limits.")
                break
                
            try:
                data, addr = sock.recvfrom(4096)
                response_text = data.decode('utf-8', errors='ignore')
                first_line = response_text.splitlines()[0] if response_text else "Empty Response"
                
                print(f"[RECV] from {addr[0]}:{addr[1]} -> {first_line}")
                
                # Check signaling status
                if "SIP/2.0 100 Trying" in response_text:
                    print("[INFO] STATUS: Asterisk received the packet and is ringing/routing the call!")
                elif "SIP/2.0 401 Unauthorized" in response_text:
                    print("[OK] STATUS: Asterisk responded with a password request (401 Unauthorized).")
                    print("   -> SUCCESS! This proves UDP network connectivity on port 5060 is 100% WORKING.")
                    print("      Asterisk is reachable and actively challenging the call signaling.")
                    break
                elif "SIP/2.0 200 OK" in response_text:
                    print("[SUCCESS] STATUS: Asterisk has ANSWERED the call successfully!")
                    print("   -> SUCCESS! UDP calling trunk is working, and the call went through.")
                    break
                elif "SIP/2.0 404 Not Found" in response_text:
                    print("[-] STATUS: Asterisk responded but extension was not found.")
                    print("   -> Network UDP connectivity is WORKING, but check dialplan (extensions.conf) config!")
                    break
                else:
                    # Other codes (e.g. 180 Ringing, 183 Session Progress)
                    pass
                    
            except socket.timeout:
                print("\n[-] Timeout: No UDP packets received from Asterisk.")
                print("Potential Root Causes:")
                print("   1. GCP Firewall Rule: Port 5060 UDP might be blocked for your IP in GCP console.")
                print("   2. Asterisk Service: Asterisk might not be running or not listening on public interface.")
                print("   3. IP Whitelist: Check if your outbound public IP matches 'match' in [neox_identify] of pjsip.conf.")
                break
                
    except Exception as e:
        print(f"[-] Error during socket execution: {e}")
    finally:
        sock.close()
        print("\n==================================================")
        print("NeoX IP Call Simulator Finished.")
        print("==================================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NeoX UDP IP Call Mock testing client")
    parser.add_argument("--host", required=True, help="External IP address of your GCP Asterisk VM")
    parser.add_argument("--port", type=int, default=5060, help="SIP Port of Asterisk (default: 5060)")
    parser.add_argument("--ext", default="100", help="Target extension (default: 100)")
    parser.add_argument("--timeout", type=float, default=6.0, help="Timeout in seconds to wait for replies (default: 6.0)")
    
    args = parser.parse_args()
    test_udp_sip_calling(args.host, args.port, args.ext, args.timeout)
