
# sensor_sim.py  --- Software-in-the-Loop data generator
import paho.mqtt.client as mqtt
import json
import random
import time

BROKER = 'localhost'
TOPIC = 'sensor/road1/data'

client = mqtt.Client()
client.connect(BROKER, 1883, 60)

while True:
    data = {
        'vehicle_count': random.randint(5, 25),
        'avg_speed': random.randint(20, 80),
        'emergency_detected': random.choice([True, False, False])
    }
    client.publish(TOPIC, json.dumps(data))
    print(f"[SensorSim] Sent: {data}")
    time.sleep(5)

