# sumo_publisher.py
"""
SUMO -> MQTT publisher with in-session emergency spawn trigger.

Usage:
    python sumo_publisher.py --sumocfg path/to/osm.sumocfg [--gui] [--edges e1,e2,...]

Requirements:
 - SUMO installed and 'traci' importable (add SUMO tools to PYTHONPATH or set SUMO_HOME).
 - paho-mqtt (pip install paho-mqtt)
"""

import argparse
import json
import time
import sys
import os
import random
import threading

# Try to import traci; help user if not available
try:
    import traci
except Exception as ex:
    # Attempt to add SUMO tools if SUMO_HOME set
    SUMO_HOME = os.environ.get("SUMO_HOME")
    if SUMO_HOME:
        sys.path.append(os.path.join(SUMO_HOME, "tools"))
        try:
            import traci  # try again
        except Exception:
            raise RuntimeError("Unable to import traci. Ensure SUMO is installed and SUMO_HOME/tools is on PYTHONPATH.") from ex
    else:
        raise RuntimeError("traci not found. Set SUMO_HOME env var pointing to SUMO install or add SUMO tools to PYTHONPATH.") from ex

import paho.mqtt.client as mqtt

# ========== Config ==========
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "sensor/road1/data"
MQTT_TRIGGER_TOPIC = "control/sumo/trigger_emergency"
CONTROL_TOPIC = "control/road1/cmd"  # optional: publisher can also publish immediate control events

STEP_LENGTH = 1.0       # SUMO step length in seconds
PUBLISH_EVERY = 2       # publish every N simulation steps

# SUMO binary names: change to full path if needed
SUMO_BIN = "sumo"
SUMO_GUI_BIN = "sumo-gui"

# ============================

client = mqtt.Client()

def kmh(m_s):
    return float(m_s) * 3.6

def spawn_emergency_on_route(route_id=None, edge_list=None):
    """
    Spawn an emergency vehicle inside the running TraCI session.
    If route_id is None, create a temporary route along provided edge_list or a random route.
    Returns vehicle id (vid) or raises error.
    """
    vid = f"EV_{int(time.time()*1000)}_{random.randint(0,999)}"
    # Create a route if not provided
    if route_id is None:
        if edge_list and len(edge_list) > 0:
            rid = f"route_{vid}"
            try:
                traci.route.add(rid, edge_list)
            except Exception:
                # If route exists or cannot be added, fallback to first available route
                pass
            route_id = rid
        else:
            routes = traci.route.getIDList()
            if len(routes) == 0:
                # fallback: build route from first few non-internal edges
                edges = [e for e in traci.edge.getIDList() if not e.startswith(":")]
                if len(edges) < 2:
                    raise RuntimeError("Network has too few edges to create a route.")
                route_edges = edges[:min(5, len(edges))]
                rid = f"route_{vid}"
                traci.route.add(rid, route_edges)
                route_id = rid
            else:
                route_id = random.choice(routes)

    depart_time = traci.simulation.getTime() + 0.1
    # Add vehicle with type 'emergency' if vType exists; otherwise add with default and set color / type param
    try:
        traci.vehicle.add(vehID=vid, routeID=route_id, typeID="emergency", depart=depart_time)
    except traci.TraCIException:
        # If 'emergency' type not defined in route files, add with default type then set color/params
        traci.vehicle.add(vehID=vid, routeID=route_id, depart=depart_time)
        try:
            traci.vehicle.setColor(vid, (255, 0, 0))
        except Exception:
            pass
    # Optionally tune behaviour for demonstration (aggressive)
    try:
        # set max speed high (in m/s); SUMO uses m/s
        traci.vehicle.setMaxSpeed(vid, 40.0)
        # relax speed mode if needed for demonstration (0 disables many safety features)
        # traci.vehicle.setSpeedMode(vid, 0)
    except Exception:
        pass
    print(f"[SUMO] Spawned emergency vehicle {vid} on route {route_id}")
    return vid

# MQTT trigger handler (called when message arrives on control/sumo/trigger_emergency)
def handle_trigger_message(client_mqtt, userdata, message):
    try:
        payload = json.loads(message.payload.decode())
    except Exception:
        payload = {}
    route = payload.get("route")
    edges = payload.get("edges")  # optional array of edges
    try:
        vid = spawn_emergency_on_route(route_id=route, edge_list=edges)
        # Publish immediate event so decision worker gets low-latency signal (optional)
        evt = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "emergency_spawned": True, "vehicle_id": vid}
        client.publish(CONTROL_TOPIC, json.dumps({"action":"emergency_spawned", "details": evt}))
    except Exception as e:
        print("[SUMO] trigger spawn error:", e)

def start_mqtt_subscriptions():
    client.on_message = None  # default handler is None; we'll add callback_add for trigger topic
    client.message_callback_add(MQTT_TRIGGER_TOPIC, lambda c,u,m: handle_trigger_message(c,u,m))
    client.subscribe(MQTT_TRIGGER_TOPIC)
    client.loop_start()
    print("[MQTT] Trigger subscription active:", MQTT_TRIGGER_TOPIC)

def aggregate_edges(edge_ids):
    total_count = 0
    speed_weight_sum = 0.0
    emergency_flag = False

    for e in edge_ids:
        try:
            vc = traci.edge.getLastStepVehicleNumber(e)
            avg_ms = traci.edge.getLastStepMeanSpeed(e)
            avg_kmh = kmh(avg_ms) if avg_ms > 0 else 0.0
            total_count += int(vc)
            speed_weight_sum += avg_kmh * int(vc)
            # check vehicles on edge for emergency type
            vehs = traci.edge.getLastStepVehicleIDs(e)
            for vid in vehs:
                try:
                    vtype = traci.vehicle.getTypeID(vid)
                    if vtype and "emergency" in vtype.lower():
                        emergency_flag = True
                        # ensure color set for visibility
                        try:
                            traci.vehicle.setColor(vid, (255, 0, 0))
                        except Exception:
                            pass
                        break
                except Exception:
                    # cannot get type; ignore
                    pass
            if emergency_flag:
                break
        except Exception:
            # edge may disappear or be invalid; ignore but continue
            pass

    avg_speed = round((speed_weight_sum / total_count) if total_count > 0 else 0.0, 1)
    return {"vehicle_count": total_count, "avg_speed": avg_speed, "emergency_detected": emergency_flag}

def run_sumo_and_publish(sumocfg, gui=False, edges_to_monitor=None):
    # choose binary
    sumo_bin = SUMO_GUI_BIN if gui else SUMO_BIN
    sumo_cmd = [sumo_bin, "-c", sumocfg, "--start", "--step-length", str(STEP_LENGTH)]
    print("[SUMO] Starting SUMO with:", " ".join(sumo_cmd))
    traci.start(sumo_cmd)
    print("[SUMO] TraCI connected.")

    # determine edges to monitor
    if edges_to_monitor:
        edge_ids = [e.strip() for e in edges_to_monitor.split(",") if e.strip()]
    else:
        edge_ids = [e for e in traci.edge.getIDList() if not e.startswith(":")]
    print(f"[SUMO] Monitoring {len(edge_ids)} edges (first 8):", edge_ids[:8])

    step = 0
    try:
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            step += 1
            if step % PUBLISH_EVERY == 0:
                metrics = aggregate_edges(edge_ids)
                payload = {
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "vehicle_count": metrics["vehicle_count"],
                    "avg_speed": metrics["avg_speed"],
                    "emergency_detected": metrics["emergency_detected"]
                }
                client.publish(MQTT_TOPIC, json.dumps(payload))
                print("[SUMO->MQTT]", payload)
    except KeyboardInterrupt:
        print("[SUMO] KeyboardInterrupt, closing.")
    finally:
        try:
            client.loop_stop()
        except Exception:
            pass
        try:
            traci.close()
        except Exception:
            pass
        print("[SUMO] Publisher stopped.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sumocfg", required=True, help="path to SUMO .sumocfg")
    parser.add_argument("--gui", action="store_true", help="run sumo-gui")
    parser.add_argument("--edges", default=None, help="comma-separated edge ids to monitor")
    args = parser.parse_args()

    # connect MQTT
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    start_mqtt_subscriptions()

    # run SUMO and publisher loop
    run_sumo_and_publish(args.sumocfg, gui=args.gui, edges_to_monitor=args.edges)

if __name__ == "__main__":
    main()
