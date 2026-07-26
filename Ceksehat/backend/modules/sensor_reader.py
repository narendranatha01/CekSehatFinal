"""
CekSehat - Modul Pembacaan Sensor
====================================
Mendukung:
- MAX30102 : Heart Rate + SpO2
- MLX90614 : Suhu Tubuh Infrared
- Mode Mock : Data simulasi untuk testing tanpa hardware
"""

import time
import random
import logging
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import (
    SENSOR_MOCK_MODE, MAX30102_I2C_ADDRESS, MLX90614_I2C_ADDRESS,
    SENSOR_READ_DURATION
)

logger = logging.getLogger(__name__)

# Import hardware libraries (hanya tersedia di Raspberry Pi)
try:
    import smbus2
    SMBUS_AVAILABLE = True
except ImportError:
    SMBUS_AVAILABLE = False
    logger.warning("⚠️  smbus2 tidak tersedia. Sensor mock mode aktif.")

try:
    from max30102 import MAX30102
    MAX30102_AVAILABLE = True
except ImportError:
    MAX30102_AVAILABLE = False


# ─── Konstanta MLX90614 ──────────────────────────────────────────────────────
MLX90614_TOBJ1 = 0x07   # Register suhu objek


class SensorReader:
    """Pembaca sensor kesehatan (MAX30102 + MLX90614)."""

    def __init__(self):
        self.mock_mode = SENSOR_MOCK_MODE or not SMBUS_AVAILABLE
        if self.mock_mode:
            logger.info("🔶 Sensor berjalan dalam MODE SIMULASI (mock data)")
        else:
            logger.info("✅ Sensor berjalan dengan hardware nyata")

    # ─── Heart Rate + SpO2 (MAX30102) ─────────────────────────────────────────
    def read_max30102(self) -> tuple[float, float]:
        """
        Baca Heart Rate dan SpO2 dari sensor MAX30102.
        Return: (heart_rate_bpm, spo2_percent)
        """
        if self.mock_mode:
            return self._mock_max30102()

        try:
            sensor = MAX30102()
            sensor.setup()

            red_readings = []
            ir_readings = []
            start = time.time()

            while time.time() - start < SENSOR_READ_DURATION:
                red, ir = sensor.read_sequential()
                if red and ir:
                    red_readings.extend(red)
                    ir_readings.extend(ir)
                time.sleep(0.1)

            sensor.shutdown()

            if not red_readings or not ir_readings:
                logger.error("Tidak ada data dari MAX30102")
                return 0.0, 0.0

            # Kalkulasi sederhana HR dan SpO2
            heart_rate = self._calculate_hr(ir_readings)
            spo2 = self._calculate_spo2(red_readings, ir_readings)

            return round(heart_rate, 1), round(spo2, 1)

        except Exception as e:
            logger.error("Error baca MAX30102: %s", e)
            return 0.0, 0.0

    def _calculate_hr(self, ir_data: list) -> float:
        """Hitung Heart Rate dari data IR (metode sederhana peak detection)."""
        if len(ir_data) < 10:
            return 0.0

        # Moving average untuk filter noise
        window = 10
        smoothed = []
        for i in range(window, len(ir_data)):
            avg = sum(ir_data[i-window:i]) / window
            smoothed.append(avg)

        if not smoothed:
            return 0.0

        # Deteksi peaks
        threshold = (max(smoothed) + min(smoothed)) / 2
        peaks = 0
        in_peak = False

        for val in smoothed:
            if val > threshold and not in_peak:
                peaks += 1
                in_peak = True
            elif val <= threshold:
                in_peak = False

        # Estimasi HR: peaks per menit
        duration_sec = len(ir_data) / 100  # Asumsi 100 sample/detik
        hr = (peaks / duration_sec) * 60 if duration_sec > 0 else 0
        return max(40, min(200, hr))

    def _calculate_spo2(self, red_data: list, ir_data: list) -> float:
        """Hitung SpO2 menggunakan rasio R (red/IR)."""
        if len(red_data) < 10 or len(ir_data) < 10:
            return 0.0

        try:
            import numpy as np
            red_arr = np.array(red_data, dtype=float)
            ir_arr = np.array(ir_data, dtype=float)

            # AC dan DC komponen
            red_ac = red_arr.std()
            red_dc = red_arr.mean()
            ir_ac = ir_arr.std()
            ir_dc = ir_arr.mean()

            if red_dc == 0 or ir_dc == 0 or ir_ac == 0:
                return 95.0

            R = (red_ac / red_dc) / (ir_ac / ir_dc)
            # Formula empiris SpO2
            spo2 = 110 - 25 * R
            return max(70, min(100, spo2))
        except Exception:
            return 95.0

    def _mock_max30102(self) -> tuple[float, float]:
        """Generate data simulasi MAX30102 (normal range)."""
        time.sleep(1.5)  # Simulasi waktu baca sensor
        heart_rate = round(random.uniform(65, 95), 1)
        spo2 = round(random.uniform(95, 99), 1)
        logger.info("🔶 [MOCK] HR=%.1f BPM, SpO2=%.1f%%", heart_rate, spo2)
        return heart_rate, spo2

    # ─── Suhu Tubuh (MLX90614) ────────────────────────────────────────────────
    def read_mlx90614(self) -> float:
        """
        Baca suhu tubuh dari sensor MLX90614 infrared.
        Return: suhu_celsius (float)
        """
        if self.mock_mode:
            return self._mock_mlx90614()

        try:
            bus = smbus2.SMBus(1)  # I2C bus 1 di Raspberry Pi

            # Baca 3 byte dari register suhu objek
            data = bus.read_i2c_block_data(MLX90614_I2C_ADDRESS, MLX90614_TOBJ1, 3)
            bus.close()

            # Konversi ke suhu Celsius
            raw = (data[1] << 8) | data[0]
            temp_k = raw * 0.02  # Resolusi 0.02K
            temp_c = temp_k - 273.15

            logger.info("✅ Suhu MLX90614: %.1f°C", temp_c)
            return round(temp_c, 1)

        except Exception as e:
            logger.error("Error baca MLX90614: %s", e)
            return 0.0

    def _mock_mlx90614(self) -> float:
        """Generate data simulasi suhu tubuh (normal range)."""
        time.sleep(0.5)
        suhu = round(random.uniform(36.1, 37.2), 1)
        logger.info("🔶 [MOCK] Suhu=%.1f°C", suhu)
        return suhu

    # ─── Baca Semua Sensor Sekaligus ──────────────────────────────────────────
    def read_all(self) -> dict:
        """
        Baca semua sensor dan kembalikan hasilnya sebagai dict.
        Return: { "heart_rate": float, "spo2": float, "suhu": float, "status": str }
        """
        logger.info("📡 Mulai membaca sensor...")

        heart_rate, spo2 = self.read_max30102()
        suhu = self.read_mlx90614()

        result = {
            "heart_rate": heart_rate,
            "spo2": spo2,
            "suhu": suhu,
            "mock_mode": self.mock_mode,
            "status": "ok" if all([heart_rate > 0, spo2 > 0, suhu > 0]) else "error"
        }

        logger.info(
            "📊 Hasil Sensor → HR: %.1f BPM | SpO2: %.1f%% | Suhu: %.1f°C",
            heart_rate, spo2, suhu
        )
        return result

    def classify_vital_signs(self, heart_rate: float, spo2: float, suhu: float) -> dict:
        """
        Klasifikasikan hasil sensor: normal / warning / critical
        Return: dict status per parameter
        """
        from config import (
            HR_NORMAL_MIN, HR_NORMAL_MAX, HR_WARNING_MIN, HR_WARNING_MAX,
            SPO2_NORMAL_MIN, SPO2_WARNING_MIN, SPO2_CRITICAL_MIN,
            TEMP_NORMAL_MIN, TEMP_NORMAL_MAX, TEMP_FEVER, TEMP_HIGH_FEVER
        )

        def hr_status(hr):
            if HR_NORMAL_MIN <= hr <= HR_NORMAL_MAX:
                return "normal"
            elif HR_WARNING_MIN <= hr <= HR_WARNING_MAX:
                return "warning"
            else:
                return "critical"

        def spo2_status(sp):
            if sp >= SPO2_NORMAL_MIN:
                return "normal"
            elif sp >= SPO2_WARNING_MIN:
                return "warning"
            else:
                return "critical"

        def suhu_status(t):
            if TEMP_NORMAL_MIN <= t <= TEMP_NORMAL_MAX:
                return "normal"
            elif t < TEMP_HIGH_FEVER:
                return "warning"
            else:
                return "critical"

        hr_s = hr_status(heart_rate)
        spo2_s = spo2_status(spo2)
        suhu_s = suhu_status(suhu)

        # Tentukan overall level
        statuses = [hr_s, spo2_s, suhu_s]
        if "critical" in statuses:
            overall = "critical"
        elif "warning" in statuses:
            overall = "warning"
        else:
            overall = "normal"

        return {
            "heart_rate_status": hr_s,
            "spo2_status": spo2_s,
            "suhu_status": suhu_s,
            "overall": overall
        }


# Singleton instance
sensor_reader = SensorReader()
