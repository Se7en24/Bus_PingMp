"""Quick test: merge a garbage bus into an existing one."""
import requests

API = "http://127.0.0.1:8001"

buses = requests.get(f"{API}/analytics/buses").json()
print(f"Before: {len(buses)} buses")

# Find TUTTU MOTORS counts
tm = [b for b in buses if b["bus_name"] == "TUTTU MOTORS"]
tm_u = [b for b in buses if b["bus_name"] == "TUTTU MOTORS U200D"]
if tm:
    print(f"  TUTTU MOTORS: {tm[0]['total_detections']} detections")
if tm_u:
    print(f"  TUTTU MOTORS U200D: {tm_u[0]['total_detections']} detections")

# Merge TUTTU MOTORS U200D -> TUTTU MOTORS
if tm_u:
    r = requests.put(
        f"{API}/bus-profile/TUTTU MOTORS U200D/confirm",
        params={"confirmed_name": "TUTTU MOTORS"},
    )
    print(f"\nMerge response: {r.status_code}")
    print(f"  {r.json()}")

    # Check after
    buses2 = requests.get(f"{API}/analytics/buses").json()
    print(f"\nAfter: {len(buses2)} buses (was {len(buses)})")
    tm2 = [b for b in buses2 if b["bus_name"] == "TUTTU MOTORS"]
    if tm2:
        print(f"  TUTTU MOTORS: {tm2[0]['total_detections']} detections")
    tm_u2 = [b for b in buses2 if b["bus_name"] == "TUTTU MOTORS U200D"]
    print(f"  TUTTU MOTORS U200D still exists: {bool(tm_u2)}")
else:
    print("No TUTTU MOTORS U200D to test with")
