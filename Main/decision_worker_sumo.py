# decision_worker_sumo.py
import paho.mqtt.client as mqtt
import json
import time
import csv
import os

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
SENSOR_TOPIC = "sensor/road1/data"
CONTROL_TOPIC = "control/road1/cmd"
AUDIT_FILE = "audit_log.csv"

# ensure audit file exists with header
if not os.path.exists(AUDIT_FILE):
    with open(AUDIT_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ts", "action", "payload"])

def log_action(action, payload):
    try:
        with open(AUDIT_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), action, json.dumps(payload)])
    except Exception as e:
        print("[AUDIT] write error:", e)

client = mqtt.Client()

def on_connect(c, userdata, flags, rc):
    print("[MQTT] DecisionWorker connected with rc=", rc)
    c.subscribe(SENSOR_TOPIC)
    # optionally subscribe to other topics

def on_message(c, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        print("[DecisionWorker] Received:", data)
        # Simple rule-based logic:
        vc = data.get("vehicle_count", 0)
        avg_speed = data.get("avg_speed", 0)
        emergency = data.get("emergency_detected", False)

        if emergency:
            decision = {"action": "priority_mode", "signal": "green", "speed_limit": 30, "reason": "emergency"}
        elif vc > 25 and avg_speed < 30:
            decision = {"action": "reduce_speed", "speed_limit": 40, "reason": "heavy_congestion"}
        elif vc > 15 and avg_speed < 40:
            decision = {"action": "reduce_speed", "speed_limit": 50, "reason": "moderate_congestion"}
        else:
            decision = {"action": "normal", "speed_limit": 60, "reason": "normal"}

        # publish decision
        client.publish(CONTROL_TOPIC, json.dumps(decision))
        print("[DecisionWorker] Published:", decision)
        # audit log
        log_action(decision["action"], decision)
    except Exception as e:
        print("[DecisionWorker] on_message error:", e)

def main():
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_forever()

if __name__ == "__main__":
    main()
