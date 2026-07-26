"""
CekSehat - Konfigurasi Sistem
=============================
Ubah nilai di file ini sesuai dengan kebutuhan Anda.
"""

import os
from pathlib import Path

# ─── Direktori Utama ─────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_DIR = BASE_DIR / "database"
VIDEOS_DIR = BASE_DIR / "videos"
FACES_DIR = BASE_DIR / "backend" / "dataset" / "faces"
LOGS_DIR = BASE_DIR / "logs"

# Buat direktori jika belum ada
for d in [DATABASE_DIR, VIDEOS_DIR, FACES_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ─── Database ─────────────────────────────────────────────────────────────────
DATABASE_PATH = DATABASE_DIR / "ceksehat.db"

# ─── FastAPI Server ───────────────────────────────────────────────────────────
API_HOST = "0.0.0.0"
API_PORT = 8000
API_RELOAD = True  # Set False di production

# ─── Telegram Bot ─────────────────────────────────────────────────────────────
# Ikuti panduan di README.md untuk mendapatkan token dan chat ID
TELEGRAM_BOT_TOKEN = "8145679869:AAGa_Vif3laxif1Dq44yzltjOPL74fwxAPA"
TELEGRAM_CHAT_ID = "6963006871"  # Bisa angka atau @username_grup

# ─── Ollama AI (Lokal) ────────────────────────────────────────────────────────
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3"          # atau "mistral", "llama3.2", dll
OLLAMA_TIMEOUT = 120             # timeout dalam detik

# ─── Sensor ───────────────────────────────────────────────────────────────────
# Mode simulasi: True = gunakan data palsu (untuk testing tanpa hardware)
#                False = baca sensor nyata via I2C
SENSOR_MOCK_MODE = False         # Diubah ke False karena sensor sudah terpasang (Pin 3 SDA, Pin 5 SCL)

# I2C Address sensor
MAX30102_I2C_ADDRESS = 0x57      # Alamat default MAX30102
MLX90614_I2C_ADDRESS = 0x5A     # Alamat default MLX90614

# Durasi baca sensor (detik)
SENSOR_READ_DURATION = 15

# ─── Kamera & Video ───────────────────────────────────────────────────────────
CAMERA_INDEX = 0                 # Index kamera (0 = kamera pertama)
VIDEO_DURATION = 30              # Durasi rekaman keluhan (detik)
VIDEO_FPS = 10                   # Dikurangi agar file lebih kecil
VIDEO_WIDTH = 640                # Resolusi dikurangi agar upload Telegram lancar
VIDEO_HEIGHT = 480
FACE_RECOGNITION_TOLERANCE = 0.5  # Semakin kecil = semakin ketat (0.4-0.6)

# ─── Decision Level Thresholds ────────────────────────────────────────────────
# Heart Rate (BPM)
HR_NORMAL_MIN = 60
HR_NORMAL_MAX = 100
HR_WARNING_MIN = 50
HR_WARNING_MAX = 120

# SpO2 (%)
SPO2_NORMAL_MIN = 95
SPO2_WARNING_MIN = 90
SPO2_CRITICAL_MIN = 85

# Suhu Tubuh (°C)
TEMP_NORMAL_MIN = 36.0
TEMP_NORMAL_MAX = 37.5
TEMP_FEVER = 38.0
TEMP_HIGH_FEVER = 39.0

# ─── Nama Puskesmas ───────────────────────────────────────────────────────────
PUSKESMAS_NAME = "Puskesmas Setempat"
SYSTEM_NAME = "CekSehat"
VERSION = "1.0.0"
