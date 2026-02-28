import paho.mqtt.client as mqtt
import json
import time
import threading
import csv
import os

MQTT_BROKER = "localhost"
AUDIT_FILE = "audit_log.csv"
MIN_GREEN = 3
MAX_GREEN = 15

# --- SYSTEM 1 STATE (4-Way Intersection) ---
queues = {"North": 0, "East": 1, "South": 0, "West": 2} # Fast-forward baseline
active_arm = "North"
signal_color = "RED"
is_cycling = False 

# --- SYSTEM 2 & 3 STATE ---
emergency_active = False
is_dangerous = False
manual_limit = 255

# --- LOGGING SETUP ---
if not os.path.exists(AUDIT_FILE):
    with open(AUDIT_FILE, "w", newline="") as f:
        csv.writer(f).writerow(["Timestamp", "Action", "Payload"])

def log_event(action, payload):
    with open(AUDIT_FILE, "a", newline="") as f:
        csv.writer(f).writerow([time.strftime("%Y-%m-%d %H:%M:%S"), action, json.dumps(payload)])

def broadcast_dashboard():
    """Pushes live 4-way state to Flask App"""
    state = {"active_arm": active_arm, "color": signal_color, "queues": queues, "emergency": emergency_active}
    client.publish("city/dashboard/state", json.dumps(state))

# =======================================================
# SYSTEM 1: ML SIGNAL OPTIMIZATION
# =======================================================
def trigger_north():
    global active_arm, signal_color, is_cycling
    active_arm = "North"
    if queues["North"] > 0:
        is_cycling = True
        dur = max(MIN_GREEN, min((queues["North"] * 2.5) + 3, MAX_GREEN))
        signal_color = "GREEN"
        client.publish("city/signal", json.dumps({"color": "GREEN", "duration": int(dur)}))
        log_event("SYS_1_NORTH_GREEN", {"duration": int(dur), "queue": queues["North"]})
    else:
        is_cycling = False
        signal_color = "RED"
    broadcast_dashboard()

def cycle_dummy_arms():
    global active_arm, signal_color, is_cycling
    is_cycling = True
    
    for arm in ["East", "South", "West"]:
        if emergency_active: break
        if queues[arm] == 0: continue # Skip empty arms (Efficiency proof!)
        
        active_arm = arm
        dur = max(MIN_GREEN, min((queues[arm] * 2.5) + 3, MAX_GREEN))
        
        # Simulated Green
        signal_color = "GREEN"
        broadcast_dashboard()
        time.sleep(dur)
        if emergency_active: break
        
        # Simulated Yellow
        signal_color = "YELLOW"
        broadcast_dashboard()
        time.sleep(2)
        if emergency_active: break
        
    # Return Control to Physical North Arm
    active_arm = "North"
    signal_color = "RED"
    broadcast_dashboard()
    is_cycling = False
    
    if queues["North"] > 0 and not emergency_active:
        trigger_north()

# =======================================================
# SYSTEM 2: EMERGENCY OVERRIDE
# =======================================================
def process_system_2():
    global active_arm, signal_color
    if emergency_active:
        active_arm = "North"
        signal_color = "GREEN"
        client.publish("city/signal", json.dumps({"color": "GREEN", "duration": 30}))
        log_event("SYS_2_EMERGENCY", {"action": "Forced North Green"})
        broadcast_dashboard()

# =======================================================
# SYSTEM 3: DYNAMIC SPEED GOVERNOR
# =======================================================
def process_system_3():
    if queues["North"] == 0: base_pwm = 0 # Stop if empty
    elif queues["North"] <= 2: base_pwm = 255 # Relaxed
    elif queues["North"] <= 5: base_pwm = 180 # Restricted
    else: base_pwm = 120 # Heavy restriction

    if is_dangerous: base_pwm = 90 # Danger Override
    
    final_pwm = min(base_pwm, int(manual_limit))
    client.publish("city/governor", json.dumps({"pwm": final_pwm}))

# =======================================================
# MQTT LISTENER
# =======================================================
def on_message(client, userdata, msg):
    global queues, is_dangerous, manual_limit, emergency_active, signal_color
    try: data = json.loads(msg.payload.decode())
    except: return

    # SENSOR EVENTS
    if msg.topic == "road/in":
        queues["North"] += 1
        process_system_3()
        broadcast_dashboard()
        # Wake up North arm if it was sleeping
        if active_arm == "North" and signal_color == "RED" and not is_cycling and not emergency_active:
            trigger_north()
            
    elif msg.topic == "road/out":
        queues["North"] = max(0, queues["North"] - 1)
        process_system_3()
        broadcast_dashboard()

    # ESP32 HARDWARE CYCLE COMPLETE -> Start Dummy Cycle
    elif msg.topic == "city/status" and data.get("state") == "cycle_complete":
        if active_arm == "North" and not emergency_active:
            signal_color = "RED"
            broadcast_dashboard()
            threading.Thread(target=cycle_dummy_arms).start()

    # DASHBOARD BUTTONS (System 3)
    elif msg.topic == "city/settings":
        if "danger" in data: is_dangerous = data["danger"]
        if "manual_limit" in data: manual_limit = data["manual_limit"]
        process_system_3()
        log_event("SYS_3_SETTINGS", data)

    # AMBULANCE (System 2)
    elif msg.topic == "v2i/ambulance/gps":
        emergency_active = (data.get("distance", 1000) < 200)
        process_system_2()

client = mqtt.Client()
client.on_message = on_message
client.connect(MQTT_BROKER, 1883)
client.subscribe([("road/in",0), ("road/out",0), ("city/status",0), ("city/settings",0), ("v2i/ambulance/gps",0)])
print("🧠 ITMS Brain Live. 4-Way Intersection & 3 Decoupled Systems Active.")
client.loop_forever()