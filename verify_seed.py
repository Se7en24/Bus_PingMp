"""Quick verification of seeded data and predictions."""
import requests, json
r = requests.get("http://127.0.0.1:8001/analytics/summary")
print("=== Summary ===")
print(json.dumps(r.json(), indent=2))

r = requests.get("http://127.0.0.1:8001/analytics/predictions", 
                  params={"camera_id": "CAM_TO_KANJIRAPALLY", "hours_ahead": 6})
d = r.json()
print(f"\n=== Predictions for {d.get('current_day')} ===")
for p in d.get("predictions", [])[:10]:
    print(f"  {p['bus_name']:25s}  {p['expected_window']:15s}  "
          f"{p['likelihood_pct']:5.1f}%  ({p['sample_size']} samples)")
if not d.get("predictions"):
    print("  (no predictions)")

r = requests.get("http://127.0.0.1:8001/analytics/buses")
buses = r.json()
print(f"\n=== Bus Profiles ({len(buses)}) ===")
for b in buses[:10]:
    print(f"  {b['bus_name']:25s}  {b['bus_type'] or '?':10s}  {b['total_detections']} dets")

print("\n=== Dashboard ===")
r = requests.get("http://127.0.0.1:8001/dashboard")
print(f"  Status: {r.status_code}  Size: {len(r.text)} bytes")
print("\nAll checks done!")
