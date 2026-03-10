"""
Test script for deduplication + bus name auto-correction.
All bus names include a unique timestamp to avoid cross-run DB interference.
"""

import sys
import os
import time
import requests

# Force UTF-8 for Windows console
if sys.stdout.encoding != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

project_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(project_dir)
sys.path.insert(0, project_dir)

BASE_URL = "http://127.0.0.1:8000"
PASS = 0
FAIL = 0
UNIQUE = str(int(time.time()))


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))


def api_post(ep, json_data):
    r = requests.post(f"{BASE_URL}{ep}", json=json_data, timeout=5)
    return r.status_code, r.json()


def api_get(ep, params=None):
    r = requests.get(f"{BASE_URL}{ep}", params=params, timeout=5)
    return r.status_code, r.json()


def api_put(ep, params=None):
    r = requests.put(f"{BASE_URL}{ep}", params=params, timeout=5)
    return r.status_code, r.json()


print("=" * 60)
print("DEDUP + AUTO-CORRECTION TEST SUITE")
print("=" * 60)

try:
    requests.get(f"{BASE_URL}/", timeout=2)
except requests.exceptions.ConnectionError:
    print("\n[ERROR] Server not running! Start with: uvicorn app.main:app")
    sys.exit(1)

print(f"\nServer OK. Tag: {UNIQUE}\n")

# All names include UNIQUE to avoid stale data issues
CAM = f"CAM_{UNIQUE}"
DEST = f"DEST_{UNIQUE}"
BUS_A = f"ZBUS_A_{UNIQUE}"           # "Z" prefix ensures no fuzzy match with real buses
BUS_A_LONG = f"ZBUS_A_LONG_{UNIQUE}"


# ==== Test 1: Fresh insert ========================================
print("--- Test 1: Fresh Insert ---")
p1 = {"camera_id": CAM, "destination_en": DEST, "destination_conf": 85, "bus_name": BUS_A}
s, d = api_post("/bus-detection", p1)
check("Returns 200", s == 200, f"status={s}")
check("Action=created", d.get("action") == "created", d.get("action"))
ID1 = d.get("id")
check("Got ID", ID1 is not None, f"id={ID1}")
print()


# ==== Test 2: Lower conf dup -> skip ==============================
print("--- Test 2: Lower Conf Dup -> SKIP ---")
p2 = {**p1, "destination_conf": 60, "bus_name": f"ZB_{UNIQUE}"}
s, d = api_post("/bus-detection", p2)
check("Returns 200", s == 200)
check("Action=skipped", d.get("action") == "skipped", d.get("action"))
check("Same ID", d.get("id") == ID1, f"got={d.get('id')} want={ID1}")
print()


# ==== Test 3: Higher conf dup -> update ===========================
print("--- Test 3: Higher Conf Dup -> UPDATE ---")
p3 = {**p1, "destination_conf": 95, "bus_name": BUS_A_LONG}
s, d = api_post("/bus-detection", p3)
check("Returns 200", s == 200)
check("Action=updated", d.get("action") == "updated", d.get("action"))
check("Same ID", d.get("id") == ID1, f"got={d.get('id')} want={ID1}")
check("Name updated", d.get("bus_name") == BUS_A_LONG, f"want={BUS_A_LONG} got={d.get('bus_name')}")
print()


# ==== Test 4: Different dest -> create ============================
print("--- Test 4: Different Dest -> CREATE ---")
BUS_B = f"ZBUS_B_{UNIQUE}"
p4 = {"camera_id": CAM, "destination_en": f"OTHER_{DEST}", "destination_conf": 90, "bus_name": BUS_B}
s, d = api_post("/bus-detection", p4)
check("Returns 200", s == 200)
check("Action=created", d.get("action") == "created", d.get("action"))
check("New ID", d.get("id") != ID1, f"got={d.get('id')}")
print()


# ==== Test 5: Manual bus name confirmation ========================
print("--- Test 5: Confirm Bus Name ---")

# The profile for BUS_A_LONG should exist from Test 3
s, d = api_put(f"/bus-profile/{BUS_A_LONG}/confirm",
               params={"confirmed_name": f"CONFIRMED_A_{UNIQUE}"})
if s == 200:
    check("Confirm returns 200", True, f"confirmed_name={d.get('confirmed_name')}")
elif s == 404:
    # Profile might not exist if update_bus_profile uses the original name
    # Try with BUS_A instead
    s, d = api_put(f"/bus-profile/{BUS_A}/confirm",
                   params={"confirmed_name": f"CONFIRMED_A_{UNIQUE}"})
    check("Confirm returns 200 (with original name)", s == 200, f"status={s}")
else:
    check("Confirm endpoint works", False, f"status={s}")

# Get the confirmed profile name for Test 6
CONFIRMED_NAME = f"CONFIRMED_A_{UNIQUE}"
print()


# ==== Test 6: Auto-correction with confirmed name =================
print("--- Test 6: Auto-Correction ---")

# Insert extra detections so the confirmed profile has total_detections >= 2
# (auto-correct requires >= 2 detections to consider a profile)
for i in range(2):
    api_post("/bus-detection", {
        "camera_id": CAM,
        "destination_en": f"EXTRA_{i}_{DEST}",
        "destination_conf": 85,
        "bus_name": BUS_A,  # same as the profile with confirmed_name
    })

# Now send a detection with a slightly different name
# that should auto-correct to CONFIRMED_NAME
typo_name = f"CONFIRMD_A_{UNIQUE}"   # close typo of CONFIRMED_A_{UNIQUE}
p6 = {
    "camera_id": CAM,
    "destination_en": f"TYPO_{DEST}",
    "destination_conf": 88,
    "bus_name": typo_name,
}
s, d = api_post("/bus-detection", p6)
check("Returns 200", s == 200)
corrected = d.get("bus_name")
print(f"  Sent:     '{typo_name}'")
print(f"  Expected: '{CONFIRMED_NAME}'")
print(f"  Got back: '{corrected}'")
check("Auto-corrected", corrected == CONFIRMED_NAME,
      f"want '{CONFIRMED_NAME}', got '{corrected}'")
print()


# ==== Summary =====================================================
print("--- Summary ---")
s, dets = api_get("/detections", {"camera_id": CAM, "limit": 20})
if s == 200:
    for d in dets:
        print(f"  id={d['id']}  bus={d['bus_name']}  dest={d['destination_en']}  conf={d['destination_conf']}")
    total = len(dets)
    # 6 POSTs total: 1 created, 1 skipped, 1 updated, 1 created, 2 extra, 1 typo
    # = 5 rows max (skip + update don't create new rows)
    check(f"Total={total} (should be <= 5 due to dedup)", total <= 5, f"got {total}")
print()


print("=" * 60)
print(f"RESULTS:  {PASS} passed,  {FAIL} failed")
if FAIL == 0:
    print("ALL TESTS PASSED!")
else:
    print(f"WARNING: {FAIL} test(s) failed")
print("=" * 60)
