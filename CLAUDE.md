# BusPing — CLAUDE.md
> AI context file. Read this at the start of every session to avoid re-scanning the codebase.

---

## 1. What Is This Project?

**BusPing** — an AI-powered smart bus detection and prediction system for  
**Amal Jyothi College of Engineering (AJCE)**, Kerala.

Camera feeds → YOLOv11 detects buses → EasyOCR + IndicPhotoOCR reads destination boards → backend learns arrival patterns → students see predicted arrivals.

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | FastAPI + SQLAlchemy (async-ready) |
| **Database** | PostgreSQL |
| **Background jobs** | `apscheduler` (pattern rebuild every 5 min, frequency analysis weekly) |
| **CV — bus detection** | YOLOv11 (`detection/detector.py`) |
| **CV — OCR English** | EasyOCR (`detection/ocr_engine.py`) |
| **CV — OCR Malayalam** | IndicPhotoOCR (`detection/ocr_engine.py`) |
| **Frontend** | Vanilla HTML / CSS / JS — no framework |
| **Python env** | `venv/` — activate with `venv\Scripts\activate` |
| **Dev server** | `uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload` |

---

## 3. Directory Layout

```
Bus_PingMp/
├── app/
│   ├── main.py            # Entry point, lifespan, scheduler, routers
│   ├── models.py          # SQLAlchemy ORM (4 tables)
│   ├── schemas.py         # Pydantic request/response schemas
│   ├── database.py        # DB session (get_db)
│   └── routers/
│       ├── detections.py  # POST /detections, admin merge/rename
│       └── analytics.py   # GET /analytics/predictions|frequency|heatmap|summary
│
├── detection/
│   ├── detector.py        # YOLOv11 inference
│   ├── ocr_engine.py      # EasyOCR + IndicPhotoOCR (English + Malayalam)
│   ├── preprocessor.py    # Image preprocessing helpers
│   ├── matcher.py         # Fuzzy name matching / auto-correction
│   └── stream_loader.py   # Camera stream handling
│
├── learning/
│   ├── pattern_analyzer.py   # Aggregates detections → 5-min heatmap bins
│   ├── predictor.py          # Queries heatmap → ranked upcoming arrivals
│   └── frequency_analyzer.py # Weekly deep analysis → avg days/week, typical times
│
├── static/
│   ├── student.html       # Student-facing dashboard (predictions + AI patterns)
│   └── dashboard.html     # Admin dashboard (live feed, OCR review, merge)
│
├── pipeline.py            # End-to-end detection pipeline (called externally)
├── config.py              # TIME_WINDOW_MINUTES, ANALYSIS_INTERVAL_SECONDS, etc.
├── .env                   # DB URL, secrets — never commit
└── requirements.txt
```

---

## 4. Database Schema

| Table | Purpose |
|---|---|
| `bus_detections` | Raw detection log — every bus sighting (camera, name, confidence, timestamp) |
| `bus_profiles` | Master bus registry — maps OCR variants → `confirmed_name`, bus_type |
| `arrival_patterns` | 5-min window heatmap (bus × day_of_week × time_window → detection_count) |
| `bus_frequency` | Weekly analysis output — avg_days_per_week, typical_times, regularity_score, trend |

---

## 5. Key API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/detections` | Ingest a new bus detection (auto-dedup + auto-correct) |
| `GET` | `/analytics/predictions` | Upcoming buses for a camera+timeframe |
| `GET` | `/analytics/frequency` | AI learned schedule stats for all buses |
| `GET` | `/analytics/heatmap/{bus_name}` | Full week heatmap for one bus |
| `GET` | `/analytics/summary` | Quick stats (counts) |
| `POST` | `/analytics/rebuild` | Manual pattern rebuild |
| `POST` | `/analytics/analyze` | Manual frequency analysis |
| `POST` | `/detections/{id}/confirm` | Admin: confirm/rename bus name |

---

## 6. Data Flows

### Detection → DB
1. Camera pipeline calls `POST /detections` with raw OCR text.
2. **Dedup:** Same bus + camera within 60 s → keep highest confidence.
3. **Auto-correct:** Fuzzy-match raw name against `bus_profiles.confirmed_name`.

### Learning → Predictions
1. Every 5 min: `rebuild_patterns` aggregates last 60 days into `arrival_patterns`.
2. Every Sunday 00:00 (+ on startup): `analyze_bus_frequency` populates `bus_frequency`.
3. Student hits `/analytics/predictions` → `predictor.py` queries `arrival_patterns` for current dow + next N hours.

### Admin Merge
1. Admin renames a bus via `/detections/{id}/confirm`.
2. All `bus_detections` + `arrival_patterns` rows updated to new name (counts merged).
3. `rebuild_patterns` triggered immediately to sync.

---

## 7. Frontend Pages

| File | URL | Audience |
|---|---|---|
| `static/student.html` | `/` or `/student` | Students — upcoming arrivals + AI patterns |
| `static/dashboard.html` | `/dashboard` | Admin — live feed, OCR review, merge UI |

**Student dashboard features:**
- Upcoming Arrivals cards with ETA, bus type badge, destination, status badge (Arriving / N min / Upcoming)
- **Inline frequency hint per card** (e.g. `📊 Usually ~4.7x/week · 08:00, 11:20`) — reads from `freqMap` cache
- Bus Patterns (AI Learned) grid — shows regularity bar, trend badge, typical times
- Dark / Light mode toggle (persisted in `localStorage`)
- Auto-refresh every 30 s (predictions) / 2 min (patterns)
- AJCE branding: deep blue `#0d47a1` primary, bold red `#c62828` accent

---

## 8. Coding Rules & Conventions

- **Python style:** type hints everywhere, docstrings on public functions, no bare `except`.
- **SQLAlchemy:** always close sessions (use `with SessionLocal() as db` or `finally: db.close()`).
- **Async jobs:** changes to scheduler go in `app/main.py` lifespan only.
- **Frontend:** vanilla JS — no npm, no bundlers. Keep CSS in `<style>` inside the HTML file using CSS custom properties (`var(--primary)`, etc.).
- **OCR pipeline:** EasyOCR for English boards, IndicPhotoOCR for Malayalam boards. Never swap them.
- **Bus names:** always normalised via `bus_profiles.confirmed_name`; raw OCR strings are stored in `destination_en` / `destination_ml`.
- **Tests:** test scripts live in project root (`test_*.py`). Run against dev server at port 8001.

---

## 9. Progress & Status

### ✅ Completed
- Full detection → dedup → auto-correct pipeline
- Admin merge / rename with cascade rebuild
- `arrival_patterns` heatmap + real-time predictions
- `bus_frequency` table + `frequency_analyzer.py` + weekly scheduler
- `/analytics/frequency` API endpoint + `BusFrequencyOut` schema
- Student dashboard: prediction cards with inline frequency hints (`📊 Usually ...`)
- Student dashboard: "Bus Patterns (AI Learned)" section with regularity bars + trend badges
- Admin dashboard: OCR review, manual confirm/merge, live feed monitoring
- Dark / light theme toggle

### 🔲 Remaining / Ideas
- Push notifications / PWA support (students get notified when their bus is close)
- Multi-camera support (currently hardcoded to `CAM_TO_KANJIRAPALLY`)
- User-facing bus filter / favourite buses
- Historical accuracy stats ("this prediction was correct 87% of the time")
- KSRTC schedule import to cross-validate AI predictions

---

## 10. Common Commands

```powershell
# Activate venv (Windows)
venv\Scripts\activate

# Start dev server
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

# Load seed data
python seed_dummy_data.py

# Verify seed
python verify_seed.py

# Test predictions endpoint
python test_upcoming.py

# Test dedup logic
python test_dedup.py
```
