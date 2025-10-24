# emergency_trigger.py
import paho.mqtt.client as mqtt
import json
import time

BROKER = 'localhost'
TOPIC = 'sensor/road1/data'

client = mqtt.Client()
client.connect(BROKER, 1883, 60)

# publish one emergency packet and exit
pkt = {
  "vehicle_count": 25,
  "avg_speed": 10,
  "emergency_detected": True
}
client.publish(TOPIC, json.dumps(pkt))
print("[Emergency trigger] Published:", pkt)
time.sleep(0.2)
client.disconnect()
