from flask import Flask, request, render_template_string, jsonify
import socket
import ssl
import json
import time
import threading
from collections import deque

app = Flask(__name__)

SERVER_IP = "127.0.0.1"
PORT = 5000

# Live log store — keeps last 50 log entries, shared across requests
logs = deque(maxlen=50)
logs_lock = threading.Lock()

def add_log(level, message):
    with logs_lock:
        logs.append({
            "time": time.strftime("%H:%M:%S"),
            "level": level,   # "success", "error", "info", "ack"
            "message": message
        })

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IoT Control Panel</title>
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:       #0a0e1a;
    --panel:    #0f1524;
    --border:   #1e2d4a;
    --accent:   #00d4ff;
    --green:    #00ff88;
    --red:      #ff3d5a;
    --amber:    #ffb800;
    --text:     #c8d8f0;
    --muted:    #4a6080;
    --font-mono: 'Share Tech Mono', monospace;
    --font-ui:   'Rajdhani', sans-serif;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font-ui);
    min-height: 100vh;
    padding: 24px;
    background-image:
      radial-gradient(ellipse at 20% 0%, rgba(0,212,255,0.05) 0%, transparent 60%),
      radial-gradient(ellipse at 80% 100%, rgba(0,255,136,0.04) 0%, transparent 60%);
  }

  /* Header */
  .header {
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 32px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border);
  }
  .header-icon {
    width: 42px; height: 42px;
    border: 2px solid var(--accent);
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 20px;
    box-shadow: 0 0 16px rgba(0,212,255,0.3);
  }
  .header h1 {
    font-size: 26px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: #fff;
  }
  .header h1 span { color: var(--accent); }
  .status-dot {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    font-family: var(--font-mono);
    color: var(--green);
  }
  .dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--green);
    animation: pulse 2s ease-in-out infinite;
  }
  @keyframes pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(0,255,136,0.4); }
    50% { box-shadow: 0 0 0 6px rgba(0,255,136,0); }
  }

  /* Grid layout */
  .grid {
    display: grid;
    grid-template-columns: 340px 1fr;
    gap: 20px;
    align-items: start;
  }

  /* Panel */
  .panel {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 24px;
    position: relative;
    overflow: hidden;
  }
  .panel::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, var(--accent), transparent);
    opacity: 0.6;
  }
  .panel-title {
    font-size: 11px;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 20px;
    font-family: var(--font-mono);
  }

  /* Device input */
  .input-group { margin-bottom: 20px; }
  .input-label {
    font-size: 12px;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--muted);
    display: block;
    margin-bottom: 8px;
    font-family: var(--font-mono);
  }
  .device-input {
    width: 100%;
    background: rgba(0,212,255,0.04);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px 16px;
    color: var(--accent);
    font-family: var(--font-mono);
    font-size: 15px;
    outline: none;
    transition: border-color 0.2s, box-shadow 0.2s;
  }
  .device-input:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(0,212,255,0.1);
  }
  .device-input::placeholder { color: var(--muted); }

  /* Buttons */
  .btn-group {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-bottom: 20px;
  }
  .btn {
    padding: 16px 12px;
    border: none;
    border-radius: 10px;
    font-family: var(--font-ui);
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    cursor: pointer;
    transition: transform 0.1s, box-shadow 0.2s;
    position: relative;
    overflow: hidden;
  }
  .btn:active { transform: scale(0.97); }
  .btn-on {
    background: rgba(0,255,136,0.12);
    color: var(--green);
    border: 1px solid rgba(0,255,136,0.4);
    box-shadow: 0 0 20px rgba(0,255,136,0.1);
  }
  .btn-on:hover {
    background: rgba(0,255,136,0.2);
    box-shadow: 0 0 30px rgba(0,255,136,0.25);
  }
  .btn-off {
    background: rgba(255,61,90,0.1);
    color: var(--red);
    border: 1px solid rgba(255,61,90,0.35);
    box-shadow: 0 0 20px rgba(255,61,90,0.08);
  }
  .btn-off:hover {
    background: rgba(255,61,90,0.18);
    box-shadow: 0 0 30px rgba(255,61,90,0.2);
  }

  /* LED status indicator */
  .led-display {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: rgba(0,0,0,0.3);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 20px;
  }
  .led-label {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--muted);
    letter-spacing: 2px;
  }
  .led-bulb {
    width: 20px; height: 20px;
    border-radius: 50%;
    background: var(--muted);
    transition: background 0.4s, box-shadow 0.4s;
  }
  .led-bulb.on {
    background: var(--green);
    box-shadow: 0 0 12px var(--green), 0 0 24px rgba(0,255,136,0.5);
  }
  .led-bulb.off {
    background: rgba(255,61,90,0.4);
    box-shadow: 0 0 8px rgba(255,61,90,0.3);
  }
  .led-state {
    font-family: var(--font-mono);
    font-size: 13px;
    color: var(--text);
  }

  /* Stats row */
  .stats {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .stat-box {
    background: rgba(0,0,0,0.25);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    text-align: center;
  }
  .stat-value {
    font-family: var(--font-mono);
    font-size: 22px;
    color: var(--accent);
    display: block;
  }
  .stat-label {
    font-size: 10px;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--muted);
    margin-top: 4px;
    display: block;
  }

  /* Log panel */
  .log-panel { height: 500px; display: flex; flex-direction: column; }
  .log-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 14px;
  }
  .log-count {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--muted);
  }
  .clear-btn {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--muted);
    background: none;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 3px 10px;
    cursor: pointer;
    transition: color 0.2s, border-color 0.2s;
  }
  .clear-btn:hover { color: var(--red); border-color: var(--red); }

  .log-body {
    flex: 1;
    overflow-y: auto;
    font-family: var(--font-mono);
    font-size: 13px;
    line-height: 1.7;
    scrollbar-width: thin;
    scrollbar-color: var(--border) transparent;
  }
  .log-body::-webkit-scrollbar { width: 4px; }
  .log-body::-webkit-scrollbar-track { background: transparent; }
  .log-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

  .log-entry {
    display: flex;
    gap: 12px;
    padding: 5px 0;
    border-bottom: 1px solid rgba(30,45,74,0.5);
    animation: fadeIn 0.3s ease;
  }
  @keyframes fadeIn { from { opacity: 0; transform: translateX(-6px); } to { opacity: 1; transform: none; } }

  .log-time { color: var(--muted); min-width: 68px; }
  .log-badge {
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 3px;
    min-width: 52px;
    text-align: center;
    align-self: center;
    letter-spacing: 1px;
  }
  .badge-success { background: rgba(0,255,136,0.12); color: var(--green); border: 1px solid rgba(0,255,136,0.25); }
  .badge-error   { background: rgba(255,61,90,0.12);  color: var(--red);   border: 1px solid rgba(255,61,90,0.25); }
  .badge-info    { background: rgba(0,212,255,0.1);   color: var(--accent);border: 1px solid rgba(0,212,255,0.2); }
  .badge-ack     { background: rgba(255,184,0,0.1);   color: var(--amber); border: 1px solid rgba(255,184,0,0.2); }
  .log-msg { color: var(--text); flex: 1; }

  .empty-log {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--muted);
    font-size: 13px;
    letter-spacing: 2px;
  }
</style>
</head>
<body>

<div class="header">
  <div class="header-icon">⚡</div>
  <h1>IoT <span>Control</span> Panel</h1>
  <div class="status-dot">
    <div class="dot"></div>
    SYSTEM ONLINE
  </div>
</div>

<div class="grid">

  <!-- Left: Control panel -->
  <div>
    <div class="panel">
      <div class="panel-title">// Device Control</div>

      <div class="input-group">
        <label class="input-label">Device ID</label>
        <input class="device-input" id="deviceInput" type="text"
               placeholder="e.g. arduino1" value="{{ last_device }}">
      </div>

      <!-- LED status display -->
      <div class="led-display">
        <span class="led-label">LED STATUS</span>
        <div class="led-bulb {{ led_state }}" id="ledBulb"></div>
        <span class="led-state" id="ledState">{{ led_state.upper() if led_state else 'UNKNOWN' }}</span>
      </div>

      <div class="btn-group">
        <button class="btn btn-on" onclick="sendCmd('LED_ON')">
          ◉ ON
        </button>
        <button class="btn btn-off" onclick="sendCmd('LED_OFF')">
          ◎ OFF
        </button>
      </div>

      <!-- Stats -->
      <div class="stats">
        <div class="stat-box">
          <span class="stat-value" id="cmdCount">{{ cmd_count }}</span>
          <span class="stat-label">Commands Sent</span>
        </div>
        <div class="stat-box">
          <span class="stat-value" id="lastLatency">{{ last_latency }}</span>
          <span class="stat-label">Last Latency</span>
        </div>
      </div>
    </div>
  </div>

  <!-- Right: Live log -->
  <div class="panel log-panel">
    <div class="log-toolbar">
      <div class="panel-title" style="margin:0">// Live System Log</div>
      <div style="display:flex;gap:10px;align-items:center">
        <span class="log-count" id="logCount">{{ logs|length }} entries</span>
        <button class="clear-btn" onclick="clearLogs()">CLEAR</button>
      </div>
    </div>

    <div class="log-body" id="logBody">
      {% if logs %}
        {% for entry in logs %}
        <div class="log-entry">
          <span class="log-time">{{ entry.time }}</span>
          <span class="log-badge badge-{{ entry.level }}">{{ entry.level.upper() }}</span>
          <span class="log-msg">{{ entry.message }}</span>
        </div>
        {% endfor %}
      {% else %}
        <div class="empty-log">NO LOGS YET — WAITING FOR COMMANDS</div>
      {% endif %}
    </div>
  </div>

</div>

<script>
  let cmdCount = {{ cmd_count }};
  let pollInterval;

  function sendCmd(command) {
    const device = document.getElementById('deviceInput').value.trim();
    if (!device) {
      appendLog('error', 'No device ID entered');
      return;
    }

    fetch('/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device, command })
    })
    .then(r => r.json())
    .then(data => {
      if (data.status === 'ok') {
        cmdCount++;
        document.getElementById('cmdCount').textContent = cmdCount;

        // Update LED bulb
        const bulb = document.getElementById('ledBulb');
        const state = document.getElementById('ledState');
        bulb.className = 'led-bulb ' + (command === 'LED_ON' ? 'on' : 'off');
        state.textContent = command === 'LED_ON' ? 'ON' : 'OFF';

        appendLog('success', `Sent '${command}' to '${device}'`);
      } else {
        appendLog('error', data.message || 'Command failed');
      }
    })
    .catch(e => appendLog('error', e.toString()));
  }

  function appendLog(level, message) {
    const body = document.getElementById('logBody');
    const empty = body.querySelector('.empty-log');
    if (empty) empty.remove();

    const now = new Date();
    const time = now.toTimeString().slice(0,8);
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = `
      <span class="log-time">${time}</span>
      <span class="log-badge badge-${level}">${level.toUpperCase()}</span>
      <span class="log-msg">${message}</span>
    `;
    body.appendChild(entry);
    body.scrollTop = body.scrollHeight;

    const count = body.querySelectorAll('.log-entry').length;
    document.getElementById('logCount').textContent = count + ' entries';
  }

  function clearLogs() {
    fetch('/clear_logs', { method: 'POST' });
    document.getElementById('logBody').innerHTML =
      '<div class="empty-log">NO LOGS YET — WAITING FOR COMMANDS</div>';
    document.getElementById('logCount').textContent = '0 entries';
  }

  // Poll server for ACK logs every 2 seconds
  function pollLogs() {
    fetch('/logs')
    .then(r => r.json())
    .then(data => {
      if (data.latency) {
        document.getElementById('lastLatency').textContent = data.latency;
        appendLog('ack', `ACK received — latency ${data.latency}`);
      }
    });
  }
  pollInterval = setInterval(pollLogs, 2000);
</script>

</body>
</html>
"""

# Shared state
cmd_count = 0
last_latency = "—"
last_device = "arduino1"
led_state = ""
pending_ack = None


def send_command(device, command):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw_sock.settimeout(10)
    raw_sock.connect((SERVER_IP, PORT))
    sock = context.wrap_socket(raw_sock)

    sent_time = time.time()

    msg = {
        "type": "COMMAND",
        "device_id": device,
        "command": command,
        "sent_time": sent_time
    }

    sock.send(json.dumps(msg).encode())
    time.sleep(0.5)
    sock.close()

    return sent_time


@app.route("/", methods=["GET"])
def home():
    with logs_lock:
        log_list = list(logs)
    return render_template_string(HTML,
        logs=log_list,
        cmd_count=cmd_count,
        last_latency=last_latency,
        last_device=last_device,
        led_state=led_state
    )


@app.route("/command", methods=["POST"])
def command():
    global cmd_count, last_latency, last_device, led_state

    data = request.get_json()
    device = data.get("device", "")
    command = data.get("command", "")

    try:
        send_command(device, command)
        cmd_count += 1
        last_device = device
        led_state = "on" if command == "LED_ON" else "off"

        add_log("success", f"Forwarded '{command}' to '{device}'")
        return jsonify({"status": "ok"})

    except Exception as e:
        add_log("error", str(e))
        return jsonify({"status": "error", "message": str(e)})


@app.route("/logs", methods=["GET"])
def get_logs():
    return jsonify({"latency": None})


@app.route("/clear_logs", methods=["POST"])
def clear_logs():
    with logs_lock:
        logs.clear()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    add_log("info", "IoT Control Panel started")
    app.run(debug=True, use_reloader=False, port=8080)
