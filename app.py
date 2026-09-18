from flask import Flask, render_template, jsonify, request
import paho.mqtt.client as mqtt
import json
import csv
import os
import sys

app = Flask(__name__)
AUDIT_FILE = "audit_log.csv"
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

# Global state to hold the intersection data
intersection_state = {
    "active_arm": "North", 
    "color": "RED", 
    "queues": {"North": 0, "East": 1, "South": 0, "West": 2},
    "emergency": False
}

def on_message(client, userdata, msg):
    global intersection_state
    if msg.topic == "city/dashboard/state":
        intersection_state = json.loads(msg.payload.decode())

client = mqtt.Client()
client.on_message = on_message
try:
    client.connect(MQTT_BROKER, MQTT_PORT)
except ConnectionRefusedError:
    print(
        f"Cannot connect to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}. "
        "Start Mosquitto first, or set MQTT_BROKER to the broker machine."
    )
    sys.exit(1)
client.subscribe("city/dashboard/state")
client.loop_start()

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/latest')
def latest_logs():
    if os.path.exists(AUDIT_FILE):
        try:
            with open(AUDIT_FILE, "r") as f:
                reader = csv.reader(f)
                next(reader, None)
                return jsonify(list(reader)[-15:])
        except: return jsonify([])
    return jsonify([])

@app.route('/intersection_data')
def get_intersection_data():
    return jsonify(intersection_state)

@app.route('/set_limiter')
def set_limiter():
    client.publish("city/settings", json.dumps({"manual_limit": int(request.args.get('val', 255))}))
    return jsonify({"status": "Sent"})

@app.route('/update_queue')
def update_queue():
    arm = request.args.get('arm')
    change = int(request.args.get('change', 0))
    client.publish("city/settings", json.dumps({"queue_update": {"arm": arm, "change": change}}))
    return jsonify({"status": "Sent"})

@app.route('/toggle_danger')
def toggle_danger():
    client.publish("city/settings", json.dumps({"danger": request.args.get('state') == 'true'}))
    return jsonify({"status": "Sent"})

@app.route('/ambulance')
def ambulance():
    client.publish("v2i/ambulance/gps", json.dumps({"distance": int(request.args.get('dist', 1000))}))
    return jsonify({"status": "Sent"})

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)