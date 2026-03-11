# BusPing — Project State & Architectural Summary

## 1. Project Overview
BusPing is an AI-powered smart bus detection and tracking system designed for Amal Jyothi College of Engineering (AJCE). The system uses camera feeds to detect buses, performs OCR on the destination boards (in both English and Malayalam), and uses this data to predict future bus arrivals for students.

## 2. Core Architecture

The system is built on a modern Python backend using FastAPI and SQLAlchemy, with a vanilla HTML/CSS/JS frontend.

### Component Details
*   **Computer Vision Pipeline:**
    *   **YOLOv11:** Used for detecting the bus in the frame.
    *   **IndicPhotoOCR:** Used for reading Malayalam destination boards.
    *   **EasyOCR:** Used for reading English text on the bus.
*   **Backend:**
    *   **Framework:** FastAPI provides high-performance, asynchronous REST APIs.
    *   **Database:** PostgreSQL (via SQLAlchemy ORM).
    *   **Background Jobs:** `apscheduler` is used to run periodic automated tasks.
*   **Frontend:**
    *   **Admin Dashboard (`dashboard.html`):** Used to monitor live feeds, verify OCR results, and resolve data inconsistencies.
    *   **Student Dashboard (`student.html`):** A mobile-responsive web app where students can view predicted bus arrivals. It features a clean design with "AJCE" branding (deep blue and bold red accents) and dark/light mode toggles.

## 3. Database Schema

The database uses three primary tables to manage the flow from raw data to actionable predictions:

1.  **`bus_detections`:** Logs every single time a bus is detected (who, what time, confidence score).
2.  **`bus_profiles`:** A master registry of unique buses. This is critical for data normalization (e.g., mapping variations of a name to a single `confirmed_name`).
3.  **`arrival_patterns`:** An aggregated "heatmap" table. It breaks days into 5-minute windows and counts how many times a specific bus was seen in that window.
4.  **`bus_frequency` (New - Learning System):** Stores the result of weekly, deep-dive historical analysis to provide human-readable reliability metrics (e.g., "Regularity", "Trend", "Typical Times").

## 4. Current Data Flows

### A. Detection & Auto-Correction Flow
1.  The camera pipeline detects a bus and runs OCR to get a raw string (e.g., "Pala Fast").
2.  This raw string is sent to the `/detections` API endpoint.
3.  **Deduplication:** The backend checks if the same bus was seen by the same camera in the last 60 seconds; if so, it keeps the record with the highest confidence.
4.  **Auto-Correction:** The raw name is fuzzy-matched against `bus_profiles`. If there is a strong match to a `confirmed_name`, the raw name is automatically swapped for the canonical one.

### B. Manual Rename/Merge Flow (Admin)
If the OCR repeatedly makes mistakes, an admin can manually update a bus profile.
When an Admin changes a bus name via the UI (`confirm_bus_name` endpoint):
1.  All old records in `bus_detections` are updated to the new name.
2.  All aggregated records in `arrival_patterns` are updated to the new name (if the target name already exists, the counts are merged).
3.  The system immediately triggers a background rebuild (`rebuild_patterns`) to ensure the predictive heatmap is flawlessly in sync.

### C. Learning & Prediction Flow (The "Smart" aspect)
1.  **Pattern Aggregation (Every 5 mins):** The `apscheduler` runs `rebuild_patterns`, which looks back 60 days and aggregates `bus_detections` into the 5-minute heatmap bins in `arrival_patterns`.
2.  **Frequency Analysis (Weekly & on Startup):** Analyzes the raw detections to figure out high-level patterns (e.g., "This bus comes 4 days a week").
3.  **Real-Time Prediction (Student Dashboard):** When a student opens the app, it hits `/analytics/predictions`. The backend looks at the current day and time, queries the `arrival_patterns` table for the next *N* hours, and returns a probabilistically ranked list of buses most likely to arrive.

## 5. Recent Changes & Current Status

*   **Student UI:** The UI has been heavily refined. Extraneous elements (like status bars and confidence scores) were removed in favor of a clean, highly legible card layout featuring gradient time-boxes, status badges, and AJCE colors.
*   **Learning System Integration:** The database and API have been fully prepped to handle deep weekly learning (The `bus_frequency` table, `frequency_analyzer.py`, and API endpoints are built and tested).
*   **Next Immediate Step:** The backend learning system now needs to be connected to the Student Dashboard so students can see insights like *"Usually 4x/week at ~11:20 AM"*.
