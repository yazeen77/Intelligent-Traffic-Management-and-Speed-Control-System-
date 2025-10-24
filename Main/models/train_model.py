import pandas as pd
import os
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from imblearn.over_sampling import SMOTE
import joblib

# Ensure raw traffic data exists before loading
data_file = "data/raw_traffic_data.csv"
if not os.path.exists(data_file) or os.stat(data_file).st_size == 0:
    print(f"Error: {data_file} is missing or empty.")
    exit(1)

# Load raw traffic data
df = pd.read_csv(data_file)

# Handle missing values
df.fillna({"vehicle_id": "unknown", "speed": 0, "lat": 0, "lon": 0, "edge": ""}, inplace=True)

# Remove rows with empty edges
df = df[df["edge"] != ""]

# Rename speed → avg_speed to match processed data
df.rename(columns={"speed": "avg_speed"}, inplace=True)

# Drop NaN values before grouping
df.dropna(subset=["edge", "vehicle_id"], inplace=True)

# Calculate unique vehicle count per edge
df["vehicle_count"] = df.groupby("edge")["vehicle_id"].transform("nunique")

# Ensure dataset is not empty before proceeding
if df["vehicle_count"].empty:
    print("No vehicle data available. Training aborted.")
    exit(1)

# Define congestion levels using percentiles
if len(df) >= 3:  
    q1, q2 = df["vehicle_count"].quantile([0.33, 0.66])
else:
    q1, q2 = 1, 2  # Default fallback for small datasets

df["congestion_level"] = df["vehicle_count"].apply(
    lambda x: "Low" if x <= q1 else ("Medium" if x <= q2 else "High")
)

# Define features (X) and target (y)
X = df[['vehicle_count', 'avg_speed', 'lat', 'lon']]
y = df["congestion_level"]

# Split dataset for training and testing
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Handle class imbalance using SMOTE
smote = SMOTE(random_state=42)
X_train_resampled, y_train_resampled = smote.fit_resample(X_train, y_train)

# Train Random Forest Classifier
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train_resampled, y_train_resampled)

# Save the trained model
joblib.dump(model, "traffic_model.pkl")

print("Model training complete. Model saved as 'traffic_model.pkl'.")
