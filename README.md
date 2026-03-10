# BusPing 🚍

**BusPing** is an AI-powered smart bus detection and tracking system designed for Amal Jyothi College of Engineering (AJCE). The system uses camera feeds to detect buses, performs OCR on the destination boards (in both English and Malayalam), and uses this data to predict future bus arrivals for students.

## Features
- **Computer Vision Pipeline:** Uses YOLOv11 for bus detection.
- **Multilingual OCR:** Employs IndicPhotoOCR for reading Malayalam destination boards and EasyOCR for English text.
- **Smart Analytics & Learning System:** Aggregates detection data to create arrival heatmaps and predict bus frequencies (e.g., "Usually 4x/week at ~11:20 AM"). Automatically rebuilds patterns via background jobs.
- **Admin Dashboard:** Real-time monitoring, OCR verification, and manual bus profile management (renaming/merging records).
- **Student Dashboard:** A mobile-responsive web app with clean, AJCE-branded card layouts, dark/light mode, and live predictive insights.

---

## Architecture
- **Backend:** FastAPI (Python)
- **Database:** PostgreSQL (via SQLAlchemy ORM)
- **Background Tasks:** `apscheduler` for automated weekly learning and pattern rebuilds.
- **Frontend:** Vanilla HTML, CSS, and JavaScript served directly by FastAPI. No separate frontend framework or build step is required.

---

## Getting Started

Follow these steps to run the project locally.

### 1. Prerequisites
- Python 3.10+
- PostgreSQL server running locally or remotely.

### 2. Install Dependencies
Clone the repository, create a virtual environment, and install the required packages:

```bash
git clone https://github.com/YourUsername/Bus_PingMp.git
cd Bus_PingMp
python -m venv venv

# On Windows
venv\Scripts\activate
# On macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Database Configuration
Create a `.env` file in the root directory and add your PostgreSQL credentials:

```env
DB_USER=postgres
DB_PASSWORD=your_password_here
DB_HOST=localhost
DB_PORT=5432
DB_NAME=smart_bus

# Optional: Adjust camera or learning configurations
CAMERA_ID=CAM_TO_KANJIRAPALLY
```

*Note: When you run the server for the first time, SQLAlchemy will automatically create all the necessary database tables.*

### 4. Run the Server
Start the FastAPI server using Uvicorn:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

### 5. Access the Dashboards
Once the server is running, open your web browser:
- **Student Dashboard:** [http://localhost:8000/student](http://localhost:8000/student)
- **Admin Dashboard:** [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
- **API Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Project Structure
- `app/` — FastAPI application, routers, database configuration, and Pydantic schemas.
- `detection/` — YOLO detector, OCR engines, and media processing.
- `learning/` — Pattern analyzers and prediction logic that power the "AI" aspects of predicting bus arrivals.
- `static/` — Frontend HTML files (Dashboards) and CSS/JS assets.
- `Models/` — Weights for the YOLO models.
- `pipeline.py` — Standalone script to run the detection pipeline on a video feed.

## Note on External Models
This project requires model weights (`yolo11s.pt`, etc.) and the `IndicPhotoOCR` module which may not be pushed to GitHub due to their file size. You will need to download or place these models in their respective directories (`Models/` and `IndicPhotoOCR/`) locally for the detection pipeline to run.
