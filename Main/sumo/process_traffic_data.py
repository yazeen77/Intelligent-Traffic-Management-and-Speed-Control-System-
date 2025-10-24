import pandas as pd
import joblib
import subprocess

# Load trained machine learning model
model = joblib.load("traffic_model.pkl")

# Load raw traffic data
df = pd.read_csv("data/raw_traffic_data.csv")

# Handle missing values by replacing them with defaults
df.fillna({"vehicle_id": "", "speed": 0, "lat": 0, "lon": 0, "edge": ""}, inplace=True)

# Load valid edges with coordinates
edges_df = pd.read_csv("data/edges.csv")

# Check if edges.csv contains required columns
required_columns = {"edge_id", "lat_start", "lon_start", "lat_end", "lon_end"}
if not required_columns.issubset(edges_df.columns):
    raise KeyError(f"Missing required columns in edges.csv! Expected: {required_columns}")

valid_edges = set(edges_df["edge_id"])

# Filter out invalid edges
df = df[df["edge"].isin(valid_edges)]

# Count unique vehicles per edge and compute average speed
df_grouped = df.groupby("edge").agg({"vehicle_id": pd.Series.nunique, "speed": "mean"}).reset_index()
df_grouped.rename(columns={"vehicle_id": "vehicle_count", "speed": "avg_speed"}, inplace=True)

# Merge with edges to add coordinates
df_grouped = df_grouped.merge(edges_df, left_on="edge", right_on="edge_id", how="left")

# Ensure correct lat/lon format; convert if necessary
if df_grouped["lat_start"].max() > 1000:  # Detect incorrect UTM values
    df_grouped[["lat", "lon"]] = df_grouped.apply(lambda row: convert_utm_to_latlon(row["lat_start"], row["lon_start"]), axis=1, result_type="expand")
else:
    df_grouped["lat"] = df_grouped["lat_start"]
    df_grouped["lon"] = df_grouped["lon_start"]

# Predict congestion level using the ML model
X = df_grouped[['vehicle_count', 'avg_speed', 'lat', 'lon']]
if not X.empty:
    df_grouped["predicted_congestion"] = model.predict(X)
    df_grouped["congestion_level"] = df_grouped["predicted_congestion"].map({"Low": 1, "Medium": 2, "High": 3}).map({1: "Low", 2: "Medium", 3: "High"})
else:
    df_grouped["congestion_level"] = "Low"  # Default if no vehicles are present

# Save processed datasets
df[["timestamp", "vehicle_id", "lat", "lon", "speed", "edge"]].to_csv("data/processed_vehicle_data.csv", index=False)
df_grouped[["edge_id", "lat", "lon", "lat_start", "lon_start", "lat_end", "lon_end", "vehicle_count", "avg_speed", "congestion_level"]].to_csv("data/processed_traffic_data.csv", index=False)

print("Processed traffic data saved.")

# Run anonymization script
subprocess.run(["python", "apply_anonymization.py"], check=True)
