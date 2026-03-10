"""
Seed the database with 2 weeks of realistic dummy bus detection data.
Uses direct DB inserts (not API) to set historical timestamps.

Run:
    python seed_dummy_data.py
    
(Backend does NOT need to be running - this writes directly to the DB)
"""

import sys
import os
import random
from datetime import datetime, timedelta, timezone

project_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(project_dir)
sys.path.insert(0, project_dir)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL
from app.models import BusDetection, BusProfile, Base
from learning.pattern_analyzer import rebuild_patterns

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine)

# Ensure tables exist
Base.metadata.create_all(bind=engine)

# ── Realistic Kerala Bus Data ────────────────────────────
BUSES = [
    {
        "name": "TUTTU MOTORS",
        "type": "PRIVATE",
        "routes": ["KANJIRAPALLY", "PONKUNNAM"],
        "hours": [6, 7, 8, 10, 12, 14, 16, 18],
        "conf_range": (82, 98),
    },
    {
        "name": "ANGEL BUS",
        "type": "PRIVATE",
        "routes": ["PALA", "KOTTAYAM"],
        "hours": [7, 9, 11, 13, 15, 17, 19],
        "conf_range": (78, 95),
    },
    {
        "name": "KALLADA TRAVELS",
        "type": "PRIVATE",
        "routes": ["ERNAKULAM", "KOTTAYAM"],
        "hours": [6, 8, 14, 18, 20],
        "conf_range": (85, 99),
    },
    {
        "name": "KSRTC SUPERFAST",
        "type": "KSRTC",
        "routes": ["ERNAKULAM", "KOTTAYAM", "PALA"],
        "hours": [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
        "conf_range": (80, 96),
    },
    {
        "name": "KSRTC FAST PASSENGER",
        "type": "KSRTC",
        "routes": ["KANJIRAPALLY", "PONKUNNAM", "ERUMELY"],
        "hours": [6, 8, 10, 13, 16, 18],
        "conf_range": (75, 92),
    },
    {
        "name": "SURESH MOTORS",
        "type": "PRIVATE",
        "routes": ["NEDUMKANDAM", "KANJIRAPALLY"],
        "hours": [7, 10, 14, 18],
        "conf_range": (80, 94),
    },
    {
        "name": "ROJA BUS",
        "type": "PRIVATE",
        "routes": ["PALA", "PONKUNNAM"],
        "hours": [8, 12, 16, 20],
        "conf_range": (76, 90),
    },
    {
        "name": "SARITHA BUS",
        "type": "PRIVATE",
        "routes": ["ERUMELY", "KANJIRAPALLY"],
        "hours": [6, 9, 13, 17],
        "conf_range": (82, 96),
    },
    {
        "name": "KOTTAYAM EXPRESS",
        "type": "PRIVATE",
        "routes": ["KOTTAYAM", "ERNAKULAM"],
        "hours": [5, 7, 9, 11, 15, 19],
        "conf_range": (84, 97),
    },
    {
        "name": "PALA FAST",
        "type": "PRIVATE",
        "routes": ["PALA", "KOTTAYAM"],
        "hours": [6, 8, 10, 14, 18],
        "conf_range": (79, 93),
    },
]

EN_TO_ML = {
    "PONKUNNAM": "ponkunnam_ml",
    "PALA": "pala_ml",
    "KANJIRAPALLY": "kanjirapally_ml",
    "NEDUMKANDAM": "nedumkandam_ml",
    "KOTTAYAM": "kottayam_ml",
    "ERNAKULAM": "ernakulam_ml",
    "ERUMELY": "erumely_ml",
}

CAMERA_ID = "CAM_TO_KANJIRAPALLY"
DAYS_BACK = 14


def seed():
    db = Session()
    
    # Clean old test data (optional - remove this if you want to keep existing data)
    print("Cleaning old test/dummy data...")
    db.query(BusDetection).filter(BusDetection.camera_id == CAMERA_ID).delete()
    # Reset bus profiles for our known buses
    for bus in BUSES:
        profile = db.query(BusProfile).filter_by(bus_name=bus["name"]).first()
        if profile:
            db.delete(profile)
    db.commit()
    
    print(f"Seeding {DAYS_BACK} days of dummy data for {len(BUSES)} buses...\n")

    now = datetime.now()
    total = 0
    profiles_created = {}

    for day_offset in range(DAYS_BACK, 0, -1):
        base_date = now - timedelta(days=day_offset)
        dow = base_date.weekday()
        day_count = 0

        for bus in BUSES:
            # Some buses skip Sundays
            if dow == 6 and bus["type"] == "PRIVATE" and random.random() < 0.3:
                continue

            for hour in bus["hours"]:
                # ~15% of trips randomly skipped
                if random.random() < 0.15:
                    continue

                dest_en = random.choice(bus["routes"])
                dest_ml = EN_TO_ML.get(dest_en, dest_en)
                minute = random.randint(0, 50)
                conf = random.randint(*bus["conf_range"])

                ts = base_date.replace(
                    hour=hour, minute=minute,
                    second=random.randint(0, 59),
                    microsecond=0,
                )

                det = BusDetection(
                    camera_id=CAMERA_ID,
                    destination_en=dest_en,
                    destination_ml=dest_ml,
                    destination_conf=conf,
                    bus_name=bus["name"],
                    bus_type=bus["type"],
                    created_at=ts,  # HISTORICAL timestamp
                )
                db.add(det)
                day_count += 1
                total += 1

                # Track for profile creation
                if bus["name"] not in profiles_created:
                    profiles_created[bus["name"]] = {
                        "type": bus["type"],
                        "first": ts,
                        "last": ts,
                        "count": 0,
                    }
                p = profiles_created[bus["name"]]
                p["count"] += 1
                if ts < p["first"]:
                    p["first"] = ts
                if ts > p["last"]:
                    p["last"] = ts

        day_str = base_date.strftime("%a %Y-%m-%d")
        print(f"  {day_str}: {day_count} detections")

    db.commit()

    # Create/update bus profiles
    print(f"\nCreating {len(profiles_created)} bus profiles...")
    for name, info in profiles_created.items():
        profile = BusProfile(
            bus_name=name,
            confirmed_name=name,  # auto-confirm all dummy buses
            bus_type=info["type"],
            first_seen=info["first"],
            last_seen=info["last"],
            total_detections=info["count"],
        )
        db.add(profile)
    db.commit()

    print(f"\nTotal detections inserted: {total}")
    
    # Rebuild patterns
    print("\nRebuilding arrival patterns...")
    count = rebuild_patterns(db, days_back=DAYS_BACK + 1)
    print(f"Pattern rows created: {count}")

    # Show quick summary
    print("\n--- Summary ---")
    for name, info in sorted(profiles_created.items(), key=lambda x: -x[1]["count"]):
        print(f"  {name:25s}  {info['type']:10s}  {info['count']:4d} detections")

    db.close()
    print(f"\nDone! Start the server and open /dashboard to see predictions.")


if __name__ == "__main__":
    seed()
