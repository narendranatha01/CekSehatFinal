#!/bin/bash
# ══════════════════════════════════════════════════════════════════
# CekSehat — Script Instalasi Otomatis untuk Raspberry Pi 5
# Jalankan dengan: chmod +x setup.sh && ./setup.sh
# ══════════════════════════════════════════════════════════════════

set -e  # Berhenti jika ada error

# ─── Warna ───────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ─── Banner ───────────────────────────────────────────────────────
echo -e "${CYAN}"
echo "  ██████╗███████╗██╗  ██╗███████╗███████╗██╗  ██╗ █████╗ ████████╗"
echo " ██╔════╝██╔════╝██║ ██╔╝██╔════╝██╔════╝██║  ██║██╔══██╗╚══██╔══╝"
echo " ██║     █████╗  █████╔╝ ███████╗█████╗  ███████║███████║   ██║   "
echo " ██║     ██╔══╝  ██╔═██╗ ╚════██║██╔══╝  ██╔══██║██╔══██║   ██║   "
echo " ╚██████╗███████╗██║  ██╗███████║███████╗██║  ██║██║  ██║   ██║   "
echo "  ╚═════╝╚══════╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝  "
echo -e "${NC}"
echo -e "${BOLD}  Sistem AI Kesehatan Lokal — Raspberry Pi 5${NC}"
echo -e "  ════════════════════════════════════════════"
echo ""

step() { echo -e "${CYAN}[SETUP]${NC} $1"; }
ok()   { echo -e "${GREEN}  ✓ $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }
fail() { echo -e "${RED}  ✗ $1${NC}"; }

# ═══════════════════════════════════════════════════════════════════
# 1. System Update
# ═══════════════════════════════════════════════════════════════════
step "Update sistem Raspberry Pi..."
sudo apt-get update -qq
sudo apt-get upgrade -y -qq
ok "Sistem berhasil diupdate"

# ═══════════════════════════════════════════════════════════════════
# 2. Dependensi Sistem
# ═══════════════════════════════════════════════════════════════════
step "Instalasi dependensi sistem..."
sudo apt-get install -y -qq \
  python3 python3-pip python3-venv \
  libatlas-base-dev \
  cmake build-essential \
  libopencv-dev python3-opencv \
  i2c-tools python3-smbus \
  libboost-python-dev \
  libssl-dev \
  git curl wget \
  chromium-browser \
  unclutter \
  xdotool
ok "Dependensi sistem terinstal"

# ═══════════════════════════════════════════════════════════════════
# 3. Aktifkan I2C
# ═══════════════════════════════════════════════════════════════════
step "Mengaktifkan I2C..."
if ! grep -q "^dtparam=i2c_arm=on" /boot/config.txt 2>/dev/null; then
  echo "dtparam=i2c_arm=on" | sudo tee -a /boot/config.txt > /dev/null
  ok "I2C diaktifkan (perlu reboot)"
else
  ok "I2C sudah aktif"
fi
sudo modprobe i2c-dev 2>/dev/null || warn "Modul i2c-dev gagal dimuat (normal jika belum reboot)"

# ═══════════════════════════════════════════════════════════════════
# 4. Python Virtual Environment
# ═══════════════════════════════════════════════════════════════════
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

step "Membuat Python virtual environment..."
python3 -m venv "$VENV_DIR"
ok "Venv dibuat: $VENV_DIR"

step "Mengupgrade pip..."
"$VENV_DIR/bin/pip" install --upgrade pip -q
ok "Pip diupgrade"

# ═══════════════════════════════════════════════════════════════════
# 5. Install dlib (untuk face_recognition) — Bisa lama
# ═══════════════════════════════════════════════════════════════════
step "Instalasi dlib (proses ini membutuhkan 10-30 menit)..."
"$VENV_DIR/bin/pip" install dlib --no-cache-dir -q
ok "dlib terinstal"

step "Instalasi face_recognition..."
"$VENV_DIR/bin/pip" install face_recognition -q
ok "face_recognition terinstal"

# ═══════════════════════════════════════════════════════════════════
# 6. Install Requirements Python
# ═══════════════════════════════════════════════════════════════════
step "Instalasi Python requirements..."
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" -q

# Install library sensor tambahan
"$VENV_DIR/bin/pip" install smbus2 -q
ok "Semua requirements Python terinstal"

# ═══════════════════════════════════════════════════════════════════
# 7. Install Ollama
# ═══════════════════════════════════════════════════════════════════
step "Instalasi Ollama (AI engine lokal)..."
if ! command -v ollama &> /dev/null; then
  curl -fsSL https://ollama.com/install.sh | sh
  ok "Ollama terinstal"
else
  ok "Ollama sudah terinstal"
fi

step "Menjalankan Ollama service..."
sudo systemctl enable ollama 2>/dev/null || true
sudo systemctl start ollama 2>/dev/null || ollama serve &
sleep 3

step "Download model AI (llama3 — bisa membutuhkan waktu lama)..."
warn "Pastikan koneksi internet stabil. Download ±4GB..."
ollama pull llama3 || warn "Gagal download llama3. Coba 'ollama pull mistral' sebagai alternatif."
ok "Model AI siap"

# ═══════════════════════════════════════════════════════════════════
# 8. Buat Direktori Yang Diperlukan
# ═══════════════════════════════════════════════════════════════════
step "Membuat direktori proyek..."
mkdir -p "$SCRIPT_DIR/database"
mkdir -p "$SCRIPT_DIR/videos"
mkdir -p "$SCRIPT_DIR/logs"
mkdir -p "$SCRIPT_DIR/backend/dataset/faces"
ok "Direktori siap"

# ═══════════════════════════════════════════════════════════════════
# 9. Inisialisasi Database
# ═══════════════════════════════════════════════════════════════════
step "Inisialisasi database SQLite..."
cd "$SCRIPT_DIR/backend"
"$VENV_DIR/bin/python" -c "from database.db import init_database; init_database()"
ok "Database berhasil dibuat"

# ═══════════════════════════════════════════════════════════════════
# 10. Buat systemd Service (Auto-start)
# ═══════════════════════════════════════════════════════════════════
step "Membuat systemd service untuk auto-start..."
sudo tee /etc/systemd/system/ceksehatfinal.service > /dev/null <<EOF
[Unit]
Description=CekSehatFinal AI Kesehatan Lokal
After=network.target ollama.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR/backend
ExecStart=$VENV_DIR/bin/python main.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ceksehatfinal
ok "Service ceksehatfinal berhasil dibuat dan diaktifkan"

# ═══════════════════════════════════════════════════════════════════
# 11. Kiosk Mode — Auto-launch Chromium fullscreen
# ═══════════════════════════════════════════════════════════════════
step "Konfigurasi kiosk mode (auto-launch browser fullscreen)..."

AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"

cat > "$AUTOSTART_DIR/ceksehatfinal-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=CekSehatFinal Kiosk
Exec=bash -c "sleep 5 && chromium-browser --kiosk --noerrdialogs --disable-infobars --use-fake-ui-for-media-stream --no-first-run --enable-features=OverlayScrollbar http://localhost:8000"
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF

ok "Kiosk mode dikonfigurasi"

# ═══════════════════════════════════════════════════════════════════
# 12. Cek Sensor I2C
# ═══════════════════════════════════════════════════════════════════
step "Deteksi sensor I2C..."
if i2cdetect -y 1 2>/dev/null | grep -q "57\|5a\|57\|5A"; then
  ok "Sensor terdeteksi di bus I2C"
else
  warn "Sensor tidak terdeteksi. Pastikan koneksi kabel SDA/SCL/VCC/GND sudah benar."
  warn "Sistem akan berjalan dalam mode simulasi (mock mode) sampai sensor terhubung."
fi

# ═══════════════════════════════════════════════════════════════════
# SELESAI
# ═══════════════════════════════════════════════════════════════════
echo ""
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅ Instalasi CekSehatFinal Selesai!         ${NC}"
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
echo ""
echo -e "${BOLD}Langkah selanjutnya:${NC}"
echo "  1. Edit konfigurasi: nano $SCRIPT_DIR/backend/config.py"
echo "     → Isi TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID"
echo "     → Set SENSOR_MOCK_MODE = False (jika sensor sudah terpasang)"
echo ""
echo "  2. Jalankan sistem:"
echo "     sudo systemctl start ceksehatfinal"
echo "     atau manual: cd backend && ../venv/bin/python main.py"
echo ""
echo "  3. Akses UI di browser:"
echo "     http://localhost:8000"
echo ""
echo "  4. Test Telegram:"
echo "     curl -X POST http://localhost:8000/api/telegram/test"
echo ""
echo -e "${YELLOW}  ⚠ Reboot diperlukan untuk I2C aktif: sudo reboot${NC}"
echo ""
