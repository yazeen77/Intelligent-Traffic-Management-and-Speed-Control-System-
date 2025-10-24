import traci
import pandas as pd
import time
import os
import utm
import json
import subprocess

# SUMO Configuration
sumo_cmd = ["sumo-gui", "-c", "osm.sumocfg"]
sumo_file = "data/sumo_output.csv"
converted_file = "data/raw_traffic_data.csv"
columns = ["timestamp", "vehicle_id", "lat", "lon", "speed", "edge", "vehicle_count"]

# SUMO netOffset from osm.net.xml
x_offset, y_offset = -712702.83, -3164251.44 
MAX_VEHICLES = 250  
VEHICLE_LIFETIME = 300  

# Ensure data directory exists
os.makedirs(os.path.dirname(sumo_file), exist_ok=True)

# Delete old raw traffic data
if os.path.exists(converted_file):
    os.remove(converted_file)
    print(f"🗑️ Old data removed: {converted_file}")

def get_traffic_density():
    try:
        with open("data/config.json", "r") as f:
            config = json.load(f)
            return max(1, min(100, config.get("traffic_density", 50)))  
    except:
        return 50  

def convert_utm_to_latlon(x, y):
    utm_x, utm_y = x - x_offset, y - y_offset
    lat, lon = utm.to_latlon(utm_x, utm_y, 43, "N")
    return lat, lon

# Start SUMO
sumo_cmd.append("--step-length=1")
traci.start(sumo_cmd)

for _ in range(400):
    traci.simulationStep()

vehicle_positions = {}  
step = 400

vehicle_positions = {}  
while traci.simulation.getMinExpectedNumber() > 0:
    traci.simulationStep()
    timestamp = time.time()
    
    vehicle_ids = set(traci.vehicle.getIDList())
    updated_positions = {}
    edge_vehicle_count = {}  # Track vehicle count per edge

    for vid in vehicle_ids:
        x, y = traci.vehicle.getPosition(vid)
        speed = traci.vehicle.getSpeed(vid)
        edge = traci.vehicle.getRoadID(vid)  
        lat, lon = convert_utm_to_latlon(x, y)

        updated_positions[vid] = (lat, lon, speed, edge)
        edge_vehicle_count[edge] = edge_vehicle_count.get(edge, 0) + 1

    # Remove vehicles that are no longer in SUMO
    for vid in list(vehicle_positions.keys()):
        if vid not in updated_positions:
            del vehicle_positions[vid]

    # Update only the latest vehicle positions
    vehicle_positions.update(updated_positions)

    # Convert dictionary to DataFrame
    df_data = [[timestamp, vid, *vehicle_positions[vid], edge_vehicle_count.get(vehicle_positions[vid][3], 1)] for vid in vehicle_positions]
    
    if not df_data:
        time.sleep(1)
        continue

    df = pd.DataFrame(df_data, columns=columns)
    df.to_csv(converted_file, mode='w', header=True, index=False)

    # ✅ Fixed indentation here
    print(f"🔄 Updated: {converted_file}")

    # ✅ Fixed indentation here
    print("📊 Running traffic data processing...")
    subprocess.run(["python", "process_traffic_data.py"], check=True)

    time.sleep(0.5)

traci.close()
