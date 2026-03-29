import socket
import ssl
import threading
import json
import time

HOST = "0.0.0.0"
PORT = 5000
AUTH_TOKEN = "MY_SECRET_KEY"

CERT_FILE = "server.crt"
KEY_FILE  = "server.key"

clients = {}
lock = threading.Lock()
pause_print = False


def handle_client(conn, addr):

    global pause_print
    device_id = None

    try:
        data = conn.recv(4096).decode()
        msg = json.loads(data)

        # Handle direct COMMAND from web UI (no registration needed)
        if msg["type"] == "COMMAND":
            device_id_target = msg["device_id"]
            with lock:
                if device_id_target in clients:
                    forward_msg = {
                        "type": "COMMAND",
                        "command": msg["command"],
                        "sent_time": msg["sent_time"]
                    }
                    clients[device_id_target].send(json.dumps(forward_msg).encode())
                    print(f"[WEB COMMAND] Forwarded '{msg['command']}' to {device_id_target}")
                else:
                    print(f"[WEB COMMAND] Device '{device_id_target}' not found")
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            conn.close()
            return

        if msg["type"] != "REGISTER":
            conn.close()
            return

        device_id = msg["device_id"]

        conn.send(b"AUTH_REQUEST")

        token = conn.recv(1024).decode()

        if token != AUTH_TOKEN:
            conn.send(b"AUTH_FAILED")
            conn.close()
            return

        conn.send(b"AUTH_SUCCESS")

        with lock:
            clients[device_id] = conn

        print(f"[CONNECTED] {device_id} from {addr}")

        while True:

            data = conn.recv(4096)

            if not data:
                break

            message = json.loads(data.decode())

            if message["type"] == "STATUS":

                if not pause_print:
                    print(
                        f"[STATUS] {device_id} CPU:{message['cpu']} "
                        f"MEM:{message['memory']} DISK:{message['disk']}"
                    )

            elif message["type"] == "ACK":

                latency = time.time() - message["sent_time"]

                print(
                    f"[ACK] {device_id} executed {message['command']} "
                    f"Latency: {latency:.4f} sec"
                )

    except (ssl.SSLError, ConnectionAbortedError, ConnectionResetError, OSError) as e:
        if hasattr(e, 'winerror') and e.winerror in (10054, 10053):
            pass  # client disconnected cleanly on Windows, ignore
        else:
            print("[ERROR]", e)

    finally:

        with lock:
            if device_id and device_id in clients:
                del clients[device_id]

        conn.close()

        if device_id:
            print(f"[DISCONNECTED] {device_id}")


def send_command():

    global pause_print

    while True:

        with lock:
            device_list = list(clients.keys())

        if not device_list:
            time.sleep(2)
            continue

        pause_print = True

        print("\nConnected devices:", device_list)

        choice = input("Send command? (y/n): ")

        if choice.lower() != "y":
            pause_print = False
            continue

        device = input("Device ID: ")
        command = input("Command (LED_ON / LED_OFF): ")

        with lock:

            if device not in clients:
                print("Device not found")
                pause_print = False
                continue

            msg = {
                "type": "COMMAND",
                "command": command,
                "sent_time": time.time()
            }

            try:
                clients[device].send(json.dumps(msg).encode())
                print("[COMMAND SENT]")

            except Exception as e:
                print("[SEND ERROR]", e)

        pause_print = False


def start_server():

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)

    raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    raw_socket.bind((HOST, PORT))
    raw_socket.listen(5)

    print(f"[SERVER STARTED] TLS/SSL server running on port {PORT}")

    threading.Thread(target=send_command, daemon=True).start()

    while True:

        client_socket, addr = raw_socket.accept()

        try:
            secure_conn = context.wrap_socket(client_socket, server_side=True)
        except (ssl.SSLError, ConnectionAbortedError, ConnectionResetError, OSError) as e:
            print(f"[TLS HANDSHAKE FAILED] {addr}: {e}")
            client_socket.close()
            continue

        threading.Thread(
            target=handle_client,
            args=(secure_conn, addr),
            daemon=True
        ).start()


if __name__ == "__main__":
    start_server()
