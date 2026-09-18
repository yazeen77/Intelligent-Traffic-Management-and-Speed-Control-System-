import paho.mqtt.client as mqtt
import json
import time
import threading
import csv
import os
import sys

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
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
manual_limit = 150 # FIX 1: Set default innate limit to 150 (matches paper)

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
# OPTIMIZATION: NON-BLOCKING SLEEP
# =======================================================
def smart_sleep(duration):
    """Sleeps in 0.1s chunks so emergencies can interrupt instantly."""
    elapsed = 0
    while elapsed < duration:
        if emergency_active: return False # Emergency detected! Break sleep.
        time.sleep(0.1)
        elapsed += 0.1
    return True # Sleep finished normally

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
        if emergency_active: return # FIX 2: Safely return/exit thread immediately without overwriting state
        if queues[arm] == 0: continue # Skip empty arms (Efficiency proof!)
        
        active_arm = arm
        dur = max(MIN_GREEN, min((queues[arm] * 2.5) + 3, MAX_GREEN))
        
        # Simulated Green
        signal_color = "GREEN"
        broadcast_dashboard()
        if not smart_sleep(dur): return # OPTIMIZED: Ultra-low latency interrupt
        
        # Simulated Yellow
        signal_color = "YELLOW"
        broadcast_dashboard()
        if not smart_sleep(2): return # OPTIMIZED: Ultra-low latency interrupt
        
    # Return Control to Physical North Arm
    if not emergency_active:
        active_arm = "North"
        signal_color = "RED"
        broadcast_dashboard()
        is_cycling = False
        
        if queues["North"] > 0:
            trigger_north()

# =======================================================
# SYSTEM 2: EMERGENCY OVERRIDE
# =======================================================
def process_system_2():
    global active_arm, signal_color, is_cycling
    if emergency_active:
        active_arm = "North"
        signal_color = "GREEN"
        is_cycling = True
        client.publish("city/signal", json.dumps({"color": "GREEN", "duration": 30}))
        log_event("SYS_2_EMERGENCY", {"action": "Forced North Green", "status": "ACTIVE"})
        broadcast_dashboard()
        process_system_3()
    else:
        # FIX 3: Properly resolve emergency and revert to normal state
        log_event("SYS_2_EMERGENCY", {"action": "Emergency Cleared", "status": "RESOLVED"})
        
        # Tell the Arduino that its Green duration is instantly 0.
        # It will instantly transition to Yellow (2s), then Red, and report back via MQTT.
        client.publish("city/signal", json.dumps({"color": "GREEN", "duration": 0}))
        
        # Sync the dashboard with the Arduino's brief 2-second Yellow phase
        signal_color = "YELLOW"
        broadcast_dashboard()

# =======================================================
# SYSTEM 3: DYNAMIC SPEED GOVERNOR
# =======================================================
def process_system_3():
    q = queues["North"] # OPTIMIZATION: Read memory once

    if q == 0: base_pwm = 255 # Limit Relieved
    elif q <= 2: base_pwm = 200 # Relaxed
    elif q <= 5: base_pwm = 150 # Innate Limit Enforced
    else: base_pwm = 130 # Heavy restriction

    if is_dangerous: base_pwm = 125 # Danger Override
    
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
        if "queue_update" in data:
            arm = data["queue_update"]["arm"]
            change = data["queue_update"]["change"]
            if arm in queues:
                queues[arm] = max(0, queues[arm] + change)
        process_system_3()
        log_event("SYS_3_SETTINGS", data)

    # AMBULANCE (System 2) - FIX 3: Handle emergency state changes properly
    elif msg.topic == "v2i/ambulance/gps":
        dist = data.get("distance", 1000)
        was_emergency = emergency_active
        
        # Check if ambulance is within 200 meters
        emergency_active = (dist < 200)
        
        # Only trigger process_system_2 if the state ACTUALLY changed
        if emergency_active != was_emergency:
            process_system_2()

client = mqtt.Client()
client.on_message = on_message
try:
    client.connect(MQTT_BROKER, MQTT_PORT)
except ConnectionRefusedError:
    print(
        f"Cannot connect to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}. "
        "Start Mosquitto first, or set MQTT_BROKER to the machine running the broker."
    )
    print('Example: "C:\\Program Files\\Mosquitto\\mosquitto.exe" -c mosquitto.conf')
    sys.exit(1)
client.subscribe([("road/in",0), ("road/out",0), ("city/status",0), ("city/settings",0), ("v2i/ambulance/gps",0)])
print("🧠 ITMS Brain Live. 4-Way Intersection & 3 Decoupled Systems Active.")
client.loop_forever()
