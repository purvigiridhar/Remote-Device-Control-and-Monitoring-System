import socket
import ssl
import json
import serial
import time

SERVER_IP = "127.0.0.1"
PORT = 5000
AUTH_TOKEN = "MY_SECRET_KEY"

device_id = input("Enter Device ID: ")

# Change COM3 to whatever port your Arduino is on
# Check Device Manager -> Ports (COM & LPT) to find the right port
arduino = serial.Serial('COM5', 9600)
time.sleep(2)  # Wait for Arduino to reset after serial connect

# SSL context — skip cert verification for local/self-signed cert
context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
context.check_hostname = False
context.verify_mode = ssl.CERT_NONE

raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
raw_sock.connect((SERVER_IP, PORT))   # connect FIRST on raw socket
sock = context.wrap_socket(raw_sock)  # THEN wrap with SSL

print("[SSL] Connected securely to server")

# REGISTER
register = {
    "type": "REGISTER",
    "device_id": device_id
}
sock.send(json.dumps(register).encode())

# AUTH
if sock.recv(1024) != b"AUTH_REQUEST":
    exit()

sock.send(AUTH_TOKEN.encode())

if sock.recv(1024) != b"AUTH_SUCCESS":
    print("Auth failed")
    exit()

print(f"[CONNECTED] {device_id}")

# LISTEN FOR COMMANDS
while True:
    data = sock.recv(4096)
    if not data:
        break

    message = json.loads(data.decode())

    if message["type"] == "COMMAND":
        cmd = message["command"]
        print(f"[COMMAND RECEIVED] {cmd}")

        # Forward command to Arduino over Serial
        arduino.write((cmd + "\n").encode())

        # Send ACK back to server with latency info
        ack = {
            "type": "ACK",
            "device_id": device_id,
            "command": cmd,
            "sent_time": message["sent_time"]
        }
        sock.send(json.dumps(ack).encode())
