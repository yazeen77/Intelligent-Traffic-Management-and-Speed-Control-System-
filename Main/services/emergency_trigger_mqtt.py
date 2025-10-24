# emergency_trigger_mqtt.py
"""
Publish a trigger to SUMO publisher to spawn an emergency vehicle.
Usage:
    python emergency_trigger_mqtt.py
You can optionally pass a JSON payload with route or edges:
    python emergency_trigger_mqtt.py '{"route":"route0"}'
"""
import sys
import json
import paho.mqtt.client as mqtt

BROKER = "localhost"
PORT = 1883
TRIGGER_TOPIC = "control/sumo/trigger_emergency"

def main():
    payload = {}
    if len(sys.argv) > 1:
        try:
            payload = json.loads(sys.argv[1])
        except Exception:
            print("Invalid JSON argument; ignoring and using empty payload.")
    else:
        # default payload: empty - publisher will pick a route automatically
        payload = {}

    client = mqtt.Client()
    client.connect(BROKER, PORT, 60)
    client.loop_start()
    client.publish(TRIGGER_TOPIC, json.dumps(payload))
    print("[MQTT] Published trigger:", payload)
    client.loop_stop()
    client.disconnect()

if __name__ == "__main__":
    main()
