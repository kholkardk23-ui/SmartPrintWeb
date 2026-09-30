# SmartPrint — Stage 1: Customer File Upload Website

> **Print Smart. Print Simple.**  
> Self-service smart printing system customer portal with MySQL database integration.

---

## 1. Project Overview

**SmartPrint** is a modern, responsive self-service printing kiosk system. When fully realized across all development stages, customers will scan a QR code at a physical SmartPrint kiosk, access this web portal on their mobile phones, upload a document, configure printing options (color/BW, page range, duplex, copies), pay seamlessly via UPI (GPay, PhonePe, Paytm), and immediately receive printed documents from the kiosk tray.

**Stage 1 Scope:**
- Modern, commercial-grade, mobile-first responsive customer website built with React and Tailwind CSS.
- Fast, secure Python backend powered by FastAPI, SQLAlchemy, **MySQL (PyMySQL)**, and PyMuPDF (`fitz`).
- Drag-and-drop & native mobile PDF file upload (up to 10 MB per file).
- Real-time client and server validation (PDF header/magic bytes verification, strict file size enforcement).
- Backend page count calculation using PyMuPDF (never trusting client-supplied values).
- Document Ready summary card displaying original file name, calculated page count, file size, and upload status.
- Alembic database migration readiness for zero-downtime schema evolution.
- Next Stage preview modal detailing future Stage 2 & 3 capabilities.

---

## 2. System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ STAGE 1 (Current): Customer Web Portal & File Ingestion Engine    │
│  [Mobile/Desktop Web] ──(multipart/form-data)──> [FastAPI Server]│
│                                                          │       │
│                                              ┌───────────┴──────┐│
│                                              ▼                  ▼│
│                                       [PyMuPDF Engine]     [MySQL]
│                                       (Page Counting)   (Metadata)
└─────────────────────────────────┬────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│ STAGE 2 (Planned): Printing Options & Price Calculation Engine   │
│  - Color / Black & White selection                               │
│  - Duplex (Single-sided / Double-sided), page ranges, copies      │
│  - Dynamic pricing calculation per page                          │
└─────────────────────────────────┬────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│ STAGE 3 (Planned): UPI Payment & Verification Gateway            │
│  - Dynamic UPI QR Generation & Webhooks                          │
│  - Instant payment confirmation callback                         │
└─────────────────────────────────┬────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│ STAGE 4 (Planned): Hardware Spooling & Print Queue Manager       │
│  - Local printer driver integration & print job dispatch         │
└─────────────────────────────────┬────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│ STAGE 5 (Planned): ESP32 Microcontroller & Telemetry             │
│  - Paper sensor status, paper jam detection, hardware health     │
└─────────────────────────────────┬────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│ STAGE 6 (Planned): Kiosk Tablet Stand & Dynamic QR Kiosk Screen │
│  - Customer QR generation per session on physical machine screen │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. MySQL Database Setup

Follow these steps to set up MySQL on your system:

### A. Install MySQL
- **Windows:** Download and install [MySQL Community Server 8.0+](https://dev.mysql.com/downloads/installer/).
- **Linux (Ubuntu/Debian):** `sudo apt update && sudo apt install mysql-server`
- **macOS:** `brew install mysql`

### B. Start MySQL Server
- **Windows (Service):**
  Open PowerShell or Command Prompt as Administrator:
  ```powershell
  net start MySQL80
  ```
  *(or open `services.msc` and start the `MySQL80` service).*
- **Linux:**
  ```bash
  sudo systemctl start mysql
  ```
- **macOS:**
  ```bash
  brew services start mysql
  ```

### C. Create Database
Log in to MySQL as root:
```sql
mysql -u root -p
```
Run the database creation command:
```sql
CREATE DATABASE smartprint;
```

### D. Create User
Create a dedicated user for SmartPrint:
```sql
CREATE USER 'smartprint_user'@'localhost' IDENTIFIED BY 'YOUR_PASSWORD';
```

### E. Grant Permissions
```sql
GRANT ALL PRIVILEGES ON smartprint.* TO 'smartprint_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

### F. Configure `.env`
In `backend/.env` (or project root `.env`):
```env
DATABASE_URL=mysql+pymysql://smartprint_user:YOUR_PASSWORD@localhost:3306/smartprint
UPLOAD_DIR=./uploads
MAX_FILE_SIZE_MB=10
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

### G. Install Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### H. Start Backend
```bash
uvicorn app.main:app --reload --port 8000
```
On startup, FastAPI verifies the MySQL connection and automatically creates the `files` table if it does not exist.

---

## 4. Database Migrations with Alembic

Alembic is configured in `backend/alembic`. To generate or run future migrations:

```bash
cd backend

# Generate a new migration revision
alembic revision --autogenerate -m "create_files_table"

# Apply migrations to MySQL database
alembic upgrade head
```

---

## 5. Backend Installation & Running

```bash
cd backend

# 1. Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start server
uvicorn app.main:app --reload --port 8000
```

The backend server will run at `http://localhost:8000`.
- **Swagger Interactive Docs:** [http://localhost:8000/api/docs](http://localhost:8000/api/docs)
- **ReDoc Documentation:** [http://localhost:8000/api/redoc](http://localhost:8000/api/redoc)

---

## 6. Frontend Installation & Running

```bash
cd frontend

# 1. Install dependencies
npm install

# 2. Run development server
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 7. API Endpoints Reference

### `GET /api/health`
Verifies backend operational status and MySQL database connectivity.
- **Response (200 OK):**
  ```json
  {
    "status": "ok",
    "service": "SmartPrint Backend",
    "database": "connected"
  }
  ```

### `POST /api/files/upload`
Uploads, validates, counts pages, saves file to disk, and stores metadata in MySQL.
- **Form Data:** `file` (PDF file, max 10 MB)
- **Response (201 Created):**
  ```json
  {
    "file_id": "c2bb806f-4711-4b72-b58e-35a2a58f7382",
    "original_filename": "assignment.pdf",
    "file_size": 2456789,
    "page_count": 8,
    "status": "uploaded"
  }
  ```

### `POST /api/files/upload-multiple`
Uploads multiple PDF files at a time and stores all metadata in MySQL.
- **Form Data:** `files` (Array of PDF files)
- **Response (201 Created):**
  ```json
  [
    {
      "file_id": "9bd70e41-07dd-438e-8bb3-68a8c1263c2d",
      "original_filename": "doc1.pdf",
      "file_size": 1654,
      "page_count": 3,
      "status": "uploaded"
    }
  ]
  ```

---

## 8. Database Verification Query

After uploading a file, you can verify the metadata stored in MySQL:

```sql
mysql -u smartprint_user -p smartprint
```

```sql
SELECT id, original_filename, file_size, page_count, status, created_at FROM files;
```

---

## 9. Automated Testing

Run the pytest test suite to verify endpoints and database behavior:

```bash
cd backend
pytest -v
```

All 9 test cases will run against the test suite.

---

## 10. Project Team

- **Darshan Kholkar**
- **Harshvardhan Chavan**
- **Rajveer Sahare**
- **Pradeep Biradar**
