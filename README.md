# Intelligent Traffic Management and Speed Control System

> An IoT-powered smart traffic solution for adaptive signal control, emergency vehicle priority, and dynamic speed governance.

## Overview

The Intelligent Traffic Management and Speed Control System is a unified smart-city solution designed to make road intersections safer, faster, and more responsive. It combines live vehicle sensing, MQTT-based communication, a Python decision engine, an ESP32 edge controller, and a real-time web dashboard.

The system replaces fixed traffic-light timers with dynamic decisions based on traffic demand. It also gives ambulances immediate right of way and regulates vehicle speed during congestion or hazardous conditions.

## Key features

- **Adaptive traffic signals** - Green-light duration responds to the current vehicle queue.
- **Emergency priority** - Ambulance proximity triggers immediate signal pre-emption.
- **Dynamic speed control** - V2I commands regulate vehicle speed through PWM-based motor control.
- **Live dashboard** - Visualises the four-way intersection, queue levels, signals, emergency status, and audit logs.
- **MQTT communication** - Decouples sensing, decisions, dashboard controls, and hardware actuation.
- **Hardware-in-the-loop operation** - Connects a physical ESP32, IR sensors, LEDs, and an L298N motor driver with the traffic-control software.

## System architecture

```text
                   +-------------------------+
                   |     Flask Dashboard     |
                   |  Live status & controls |
                   +------------+------------+
                                |
                                | MQTT
                                v
+----------------+     +-------------------------+     +----------------+
| IR Sensors     | --> |  Python Traffic Brain   | --> | Mosquitto MQTT |
| Vehicle events |     | Signal, priority, speed |     |     Broker     |
+----------------+     +-------------------------+     +--------+-------+
                                                                |
                                                                | MQTT
                                                                v
                                                       +----------------+
                                                       | ESP32 Edge Node |
                                                       | LEDs + L298N +  |
                                                       | DC motor        |
                                                       +----------------+
```

## Core modules

### 1. Adaptive signal optimisation

The controller calculates green-light duration from the detected vehicle queue. Lighter traffic receives a shorter green window, while heavier traffic receives additional time within a safe maximum limit.

### 2. Emergency vehicle priority

When an ambulance is detected within the configured proximity threshold, the system overrides the regular traffic cycle and activates a priority green signal for the emergency route.

### 3. V2I dynamic speed governor

The traffic controller converts congestion and safety conditions into a PWM value. The ESP32 applies this value through the L298N driver to demonstrate infrastructure-guided vehicle speed control.

## Technology stack

| Layer | Technology |
| --- | --- |
| Decision engine | Python |
| Web application | Flask |
| Communication | MQTT / Eclipse Mosquitto |
| Edge controller | ESP32 / Arduino framework |
| Hardware | IR sensors, LEDs, L298N motor driver, DC motor |
| Dashboard | HTML, CSS, JavaScript |
| Traffic simulation | SUMO |

## Project structure

```text
.
├── app.py                    # Flask dashboard server and MQTT bridge
├── brain.py                  # Traffic-control decision engine
├── aurdinio code.txt         # ESP32 firmware
├── mosquitto.conf            # MQTT broker configuration
├── audit_log.csv             # Traffic-control event log
└── templates/
    └── dashboard.html        # Real-time traffic-management dashboard
```

## How it works

1. IR sensors connected to the ESP32 detect vehicle entry and exit events.
2. The ESP32 publishes those events to the MQTT broker.
3. The Python traffic brain updates queue state and decides signal duration, emergency priority, and the speed limit.
4. Commands are published through MQTT.
5. The ESP32 receives the commands and controls the LEDs and motor PWM output.
6. The Flask dashboard displays the current intersection state and provides live controls.

## Getting started

### Prerequisites

- Python 3
- Eclipse Mosquitto
- ESP32 with the Arduino IDE or PlatformIO
- Python packages: `flask` and `paho-mqtt`

### 1. Install Python dependencies

```bash
pip install flask paho-mqtt
```

### 2. Start the MQTT broker

```bash
mosquitto -c mosquitto.conf
```

### 3. Start the traffic decision engine

```bash
python brain.py
```

### 4. Start the dashboard

```bash
python app.py
```

Open `http://localhost:5000` in a browser.

### 5. Upload the ESP32 firmware

Update the Wi-Fi and broker settings in `aurdinio code.txt`, then upload it to the ESP32 using the Arduino IDE.

## Dashboard controls

- Adjust simulated traffic queues for the East, South, and West approaches.
- Set a dynamic speed limit with the PWM slider.
- Mark or clear a dangerous zone.
- Trigger and cancel an ambulance priority event.
- View recent traffic-control decisions in the audit log.

## Future enhancements

- Computer-vision vehicle detection and classification.
- Multi-intersection corridor coordination.
- Predictive traffic control using machine-learning models.
- Vehicle-to-vehicle coordination for safer braking and platooning.
- Cloud-based city-wide traffic analytics.

## Team

Developed as an academic smart-city project at the Department of Computer Science and Engineering, TKM Institute of Technology.

---

Built for smarter, safer, and more sustainable urban mobility.
