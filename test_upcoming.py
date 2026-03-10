"""Verify reliability tiers and likelihood values."""
import requests, json

API = "http://127.0.0.1:8001"
r = requests.get(f"{API}/analytics/predictions?camera_id=CAM_TO_KANJIRAPALLY&hours_ahead=6")
d = r.json()
preds = d.get("predictions", [])
print(f"Predictions: {len(preds)}")
print(f"Day: {d.get('current_day')}")
print()
for p in preds:
    print(f"  {p['bus_name']:25s} | {p.get('reliability','?'):15s} | {p['likelihood_pct']:5.1f}% | {p['expected_window']:12s} | -> {p.get('destination','?')}")

print(f"\nDashboard: {requests.get(f'{API}/dashboard').status_code}")
