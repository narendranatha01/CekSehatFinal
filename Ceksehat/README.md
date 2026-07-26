# 🏥 CekSehat — Sistem AI Kesehatan Lokal

> Sistem pemeriksaan kesehatan berbasis AI yang berjalan **sepenuhnya lokal** di Raspberry Pi 5.  
> Menggunakan face recognition, sensor kesehatan, AI lokal (Ollama), dan notifikasi Telegram ke puskesmas.

---

## 📋 Daftar Isi

1. [Fitur Sistem](#fitur)
2. [Kebutuhan Hardware](#hardware)
3. [Instalasi](#instalasi)
4. [Konfigurasi Telegram Bot](#telegram)
5. [Konfigurasi Sensor](#sensor)
6. [Menjalankan Sistem](#menjalankan)
7. [Alur Penggunaan](#alur)
8. [Struktur Folder](#struktur)
9. [Troubleshooting](#troubleshooting)

---

## ✨ Fitur Sistem <a name="fitur"></a>

| Fitur | Keterangan |
|---|---|
| 👁️ Face Recognition | Identifikasi otomatis warga via kamera |
| 📡 Sensor Kesehatan | HR, SpO₂ (MAX30102) + Suhu (MLX90614) |
| 🤖 AI Lokal (Ollama) | Analisis gejala & pertanyaan otomatis |
| 🎙️ Rekam Suara | Perekaman suara keluhan pasien via Web Audio API |
| 📄 Laporan PDF | Laporan pemeriksaan otomatis (*ReportLab*) |
| 📬 Notifikasi Telegram | Kirim alert + suara + PDF ke puskesmas |
| 🗄️ Database SQLite | Semua data tersimpan lokal |
| 🖥️ UI Kiosk | Touchscreen fullscreen Bahasa Indonesia |
| 🔒 100% Offline | Data tidak keluar jaringan lokal |

---

## 🔧 Kebutuhan Hardware <a name="hardware"></a>

| Komponen | Spesifikasi | Keterangan |
|---|---|---|
| Raspberry Pi 5 | 4GB / 8GB RAM | Disarankan 8GB untuk Ollama |
| Kamera | USB Webcam / RPi Camera Module 3 | Untuk Face Recognition |
| Mikrofon | USB/Built-in Webcam | Untuk Perekaman Suara Keluhan |
| Sensor MAX30102 | HR + SpO₂ | Koneksi I2C (GPIO 2, 3) |
| Sensor MLX90614 | Suhu infrared | Koneksi I2C (GPIO 2, 3) |
| Layar Touchscreen | 7" atau lebih | Kiosk mode |
| microSD | ≥ 32GB Class 10 | Untuk OS + Ollama model |
| Internet | Saat setup saja | Download Ollama model & paket |

### Skema Koneksi Sensor I2C

```
Raspberry Pi 5          MAX30102        MLX90614
─────────────           ────────        ────────
Pin 1  (3.3V)  ──────── VCC    ──────── VCC
Pin 3  (GPIO2/SDA) ──── SDA    ──────── SDA
Pin 5  (GPIO3/SCL) ──── SCL    ──────── SCL
Pin 6  (GND)   ──────── GND    ──────── GND

⚠️ Jika menggunakan 2 sensor I2C:
  - MAX30102 address: 0x57
  - MLX90614 address: 0x5A
  - Keduanya bisa share SDA/SCL yang sama
```

---

## 🚀 Instalasi <a name="instalasi"></a>

### Opsi A: Instalasi Otomatis (Direkomendasikan)

```bash
# 1. Clone / copy proyek ke Raspberry Pi
cd /home/pi
git clone <repo-url> CekSehat
# atau copy via SCP/USB

# 2. Masuk ke folder
cd CekSehat

# 3. Beri izin eksekusi
chmod +x setup.sh

# 4. Jalankan installer (±30-60 menit pertama kali)
./setup.sh
```

### Opsi B: Instalasi Manual

```bash
# 1. Update sistem
sudo apt-get update && sudo apt-get upgrade -y

# 2. Install dependensi sistem
sudo apt-get install -y python3 python3-pip python3-venv \
  libatlas-base-dev cmake build-essential \
  libopencv-dev python3-opencv i2c-tools python3-smbus

# 3. Aktifkan I2C
sudo raspi-config
# → Interface Options → I2C → Enable

# 4. Buat virtual environment
python3 -m venv venv
source venv/bin/activate

# 5. Install libraries (face recognition, reportlab, dll)
pip install dlib face_recognition reportlab

# 6. Install requirements (asumsikan semua dependencies lain)
pip install -r requirements.txt
pip install smbus2

# 7. Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 8. Download model AI
ollama pull llama3

# 9. Inisialisasi database
cd backend
python -c "from database.db import init_database; init_database()"
```

---

## 📬 Konfigurasi Telegram Bot <a name="telegram"></a>

### Langkah 1: Buat Bot Baru di Telegram

1. Buka Telegram → cari **@BotFather**
2. Ketik `/newbot`
3. Masukkan **nama bot**: `CekSehat Puskesmas`
4. Masukkan **username bot**: `ceksehat_puskesmas_bot` *(harus unik, diakhiri _bot)*
5. BotFather akan memberikan **Bot Token** seperti:
   ```
   1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ
   ```
   **Simpan token ini!**

### Langkah 2: Dapatkan Chat ID Puskesmas

**Cara A — Untuk chat pribadi:**
1. Buka browser: `https://api.telegram.org/bot<TOKEN>/getUpdates`
2. Kirim pesan ke bot dari akun Telegram puskesmas
3. Refresh halaman, cari `"chat":{"id":` → itu adalah Chat ID Anda

**Cara B — Untuk grup:**
1. Buat grup Telegram untuk puskesmas
2. Tambahkan bot ke grup tersebut
3. Kirim pesan di grup
4. Buka: `https://api.telegram.org/bot<TOKEN>/getUpdates`
5. Chat ID grup dimulai dengan tanda minus, contoh: `-1001234567890`

### Langkah 3: Isi Konfigurasi

Edit file `backend/config.py`:

```python
TELEGRAM_BOT_TOKEN = "1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ"  # Token dari BotFather
TELEGRAM_CHAT_ID   = "-1001234567890"  # Chat ID grup puskesmas
PUSKESMAS_NAME     = "Puskesmas Cikaret"  # Nama puskesmas Anda
```

### Langkah 4: Test Koneksi

```bash
curl -X POST http://localhost:8000/api/telegram/test
```

Jika berhasil, bot akan mengirim pesan ke Telegram puskesmas.

---

## 🔌 Konfigurasi Sensor <a name="sensor"></a>

Edit `backend/config.py`:

```python
# Ganti False saat sensor sudah terpasang
SENSOR_MOCK_MODE = False

# Verifikasi alamat I2C (jalankan: sudo i2cdetect -y 1)
MAX30102_I2C_ADDRESS = 0x57
   I2C_ADDRESS = 0x5A
```

**Cek sensor terdeteksi:**
```bash
sudo i2cdetect -y 1
```

Output yang benar:
```
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:                         -- -- -- -- -- -- -- -- --
...
50: -- -- -- -- -- -- -- 57 -- -- -- -- -- -- -- -- --
...
58: -- -- 5a -- -- -- -- -- -- -- -- -- -- -- -- -- --
```

---

## ▶️ Menjalankan Sistem <a name="menjalankan"></a>

### Cara 1: Otomatis (setelah `setup.sh`)

```bash
# Start service
sudo systemctl start ceksehat

# Cek status
sudo systemctl status ceksehat

# Lihat log
journalctl -u ceksehat -f

# Stop service
sudo systemctl stop ceksehat
```

### Cara 2: Manual

```bash
# Terminal 1: Jalankan Ollama
ollama serve

# Terminal 2: Jalankan backend
cd backend
source ../venv/bin/activate
python main.py
```

### Cara 3: Testing di PC/Laptop (Windows/Mac/Linux)

```bash
# Tidak perlu sensor fisik, gunakan mock mode
# Pastikan SENSOR_MOCK_MODE = True di config.py

cd backend
pip install -r ../requirements.txt
python main.py
```

Buka browser: **http://localhost:8000**

*(Catatan: Karena Perekaman Suara menggunakan akses Microphone lewat Web API, jika diakses bukan melalui localhost/Raspberry Pi melainkan melalui IP Lokal (misalnya `http://192.168...`), pastikan keamanan browser Anda mengizinkan penggunaan microphone tanpa HTTPS, atau pastikan menggunakan localhost secara langsung.)*

---

## 🗺️ Alur Penggunaan <a name="alur"></a>

```
1. BUKA LAYAR KIOSK
   └── Tampilan login dengan animasi scan wajah

2. LOGIN
   ├── Tekan "Scan Wajah" → kamera scan otomatis
   │   └── Jika dikenal → lanjut pemeriksaan
   └── Hubungi Petugas → Petugas daftarkan akun baru di Telegram bot.

3. PEMERIKSAAN SENSOR
   ├── Tempelkan jari ke sensor MAX30102
   ├── Arahkan tangan ke sensor MLX90614
   └── Tekan "Mulai Baca Sensor" → tunggu hasilnya

4. PERTANYAAN AI
   ├── AI generate 5 pertanyaan berdasarkan data sensor
   └── Jawab Ya / Tidak dengan menekan tombol

5. REKAM SUARA KELUHAN
   ├── Tekan "Mulai Rekam" → ceritakan keluhan via mikrofon
   └── Rekaman suara diunggah secara otomatis ke sistem

6. HASIL PEMERIKSAAN
   ├── Level 1 (Normal)  → Saran + imbauan
   ├── Level 2 (Perhatian) → Saran herbal / penanganan mandiri
   └── Level 3 (Darurat) → Notifikasi darurat, Voice Note keluhan, & Laporan Medis PDF dikirim ke puskesmas.
```

---

## 📁 Struktur Folder <a name="struktur"></a>

```
CekSehat/
├── backend/
│   ├── main.py                    # FastAPI entry point
│   ├── config.py                  # ⚙️ KONFIGURASI UTAMA
│   ├── database/
│   │   └── db.py                  # SQLite operations
│   ├── modules/
│   │   ├── face_recognition_module.py
│   │   ├── sensor_reader.py
│   │   ├── ai_engine.py
│   │   └── telegram_notifier.py   # Pengiriman Bot Telegram + PDF Generator
│   └── dataset/
│       └── faces/                 # Foto wajah warga
├── frontend/
│   ├── index.html                 # UI Kiosk
│   ├── style.css                  # Dark glassmorphism UI
│   └── app.js                     # Logika frontend & MediaRecorder Suara
├── database/
│   └── ceksehat.db               # Database SQLite
├── videos/                        # Penyimpanan lokal rekaman keluhan (audio .webm)
├── logs/                          # Log sistem
├── requirements.txt
├── setup.sh                       # Installer otomatis
└── README.md
```

---

## 🔍 API Endpoints

| Method | Endpoint | Keterangan |
|---|---|---|
| GET | `/` | UI Kiosk |
| GET | `/api/status` | Status sistem |
| GET | `/api/warga` | Daftar semua warga |
| POST | `/api/warga` | Daftarkan warga baru |
| POST | `/api/face/identify` | Scan & identifikasi wajah |
| POST | `/api/face/enroll/{id}` | Daftarkan wajah warga |
| GET | `/api/sensor/read` | Baca sensor langsung |
| POST | `/api/session/start` | Mulai sesi pemeriksaan |
| POST | `/api/session/{id}/sensor` | Baca sensor untuk sesi |
| POST | `/api/session/{id}/questions` | Generate pertanyaan AI |
| POST | `/api/session/{id}/answers` | Kirim jawaban |
| POST | `/api/session/{id}/record/upload` | Upload suara keluhan dari Web API |
| POST | `/api/session/{id}/analyze` | Analisis & simpan hasil (dan kirim Telegram/PDF) |
| POST | `/api/telegram/test` | Test koneksi Telegram |
| GET | `/docs` | Dokumentasi API Swagger |

---

## 🛠️ Troubleshooting <a name="troubleshooting"></a>

### ❌ Sensor tidak terbaca
```bash
# Cek koneksi I2C
sudo i2cdetect -y 1
# Jika tidak ada output, cek kabel SDA/SCL/VCC/GND
# Sementara gunakan: SENSOR_MOCK_MODE = True di config.py
```

### ❌ Face recognition error
```bash
# Pastikan dlib terinstal dengan benar
pip show dlib
# Jika error, install ulang:
pip install --no-cache-dir dlib
```

### ❌ Ollama tidak merespons
```bash
# Cek status Ollama
sudo systemctl status ollama
# Start manual:
ollama serve &
# Test:
curl http://localhost:11434/api/tags
```

### ❌ Telegram gagal kirim
```bash
# Verifikasi token dan chat ID
curl "https://api.telegram.org/bot<TOKEN>/getMe"
# Pastikan bot sudah ditambahkan ke grup
# Kirim pesan ke bot terlebih dahulu sebelum getUpdates
```

### ❌ Kamera / Mikrofon tidak terdeteksi
```bash
# Kamera
ls /dev/video*
ffplay /dev/video0

# Mikrofon (Audio recording) dipastikan izinkan akses mikrofon di Browser.
```

### ❌ Port 8000 sudah dipakai
```bash
# Ganti port di config.py
API_PORT = 8080
# atau kill proses yang menggunakan port 8000
sudo lsof -i :8000
sudo kill -9 <PID>
```

---

## 📞 Dukungan

Jika ada masalah, cek log sistem:
```bash
# Log real-time
journalctl -u ceksehat -f

# Log Ollama
journalctl -u ollama -f
```

---

*CekSehat v1.0.0 — Sistem AI Kesehatan Lokal untuk Raspberry Pi 5*  
*Data Anda aman, semua diproses secara lokal* 🔒
