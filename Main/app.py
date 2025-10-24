# app.py  --- Flask backend skeleton (robust)
from flask import Flask, request, jsonify, render_template
import json
import time
import csv
import os
import threading
import paho.mqtt.client as mqtt

app = Flask(__name__, template_folder='templates')

# MQTT Setup
BROKER = 'localhost'
PORT = 1883
TOPIC_SENSOR = 'sensor/road1/data'
TOPIC_CONTROL = 'control/road1/cmd'

audit_file = 'audit_log.csv'

# ensure audit file exists with header
if not os.path.exists(audit_file):
    with open(audit_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['ts', 'action_type', 'payload'])

client = mqtt.Client()

# Optional: callbacks to log connect and messages
def on_connect(client, userdata, flags, rc):
    print(f"[MQTT] Connected with result code {rc}")
    # subscribe if you want to log incoming control messages
    client.subscribe(TOPIC_CONTROL)

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        print(f"[MQTT] Incoming on {msg.topic}: {payload}")
        # If it's a control message, log it to audit
        if msg.topic == TOPIC_CONTROL:
            log_action('control_received', json.loads(payload))
    except Exception as e:
        print("[MQTT] on_message error:", e)

client.on_connect = on_connect
client.on_message = on_message

# Connect safely (wrap in try/except)
def start_mqtt():
    try:
        client.connect(BROKER, PORT, 60)
    except Exception as e:
        print("[MQTT] Could not connect to broker:", e)
        return
    client.loop_start()  # important: starts network loop in background thread
    print("[MQTT] loop started")

# Save decisions to a CSV
def log_action(action_type, data):
    try:
        with open(audit_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([time.strftime('%Y-%m-%d %H:%M:%S'), action_type, json.dumps(data)])
    except Exception as e:
        print("[AUDIT] Error writing audit:", e)

@app.route('/telemetry', methods=['POST'])
def telemetry():
    data = request.get_json(force=True)
    print(f"Received telemetry: {data}")
    # publish to MQTT; check that client loop started
    try:
        client.publish(TOPIC_SENSOR, json.dumps(data))
    except Exception as e:
        print("[MQTT] publish error:", e)
    return jsonify({'status': 'Data received', 'data': data})

@app.route('/latest', methods=['GET'])
def latest():
    try:
        if not os.path.exists(audit_file):
            return jsonify([])
        with open(audit_file, 'r') as f:
            rows = list(csv.reader(f))
        # return last 10 rows (excluding header if present)
        return jsonify(rows[-10:])
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/')
def home():
    # if you created templates/dashboard.html it will serve it
    if os.path.exists(os.path.join(app.template_folder, 'dashboard.html')):
        return render_template('dashboard.html')
    return '<h3>Flask Backend Running - Intelligent Traffic System</h3>'

# Start MQTT loop only once (avoid double-start with Flask debug reloader)
if __name__ == '__main__':
    # start mqtt in a thread to not block Flask startup (loop_start already uses background thread but guard connect)
    start_mqtt()
    # Run Flask normally; in dev you can use debug=True but beware the reloader will import twice
    app.run(debug=True, host='0.0.0.0', port=5000)
