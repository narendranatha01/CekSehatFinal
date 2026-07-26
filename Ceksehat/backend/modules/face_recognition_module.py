"""
CekSehat - Modul Face Recognition
===================================
Mendukung:
- Enrollment wajah baru (simpan encoding ke database)
- Identifikasi wajah dari kamera secara real-time
- Menggunakan library face_recognition (dlib)
"""

import os
import io
import logging
import pickle
import base64
import numpy as np
from pathlib import Path
from datetime import datetime
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import FACES_DIR, FACE_RECOGNITION_TOLERANCE, CAMERA_INDEX

logger = logging.getLogger(__name__)

# Import opsional — hanya tersedia di Raspberry Pi / Linux dengan dlib
try:
    import face_recognition
    import cv2
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False
    logger.warning("⚠️  face_recognition atau cv2 tidak tersedia. Mode mock aktif.")


class FaceRecognitionModule:
    """Modul pengelola face recognition."""

    def __init__(self):
        self.known_encodings = []    # List numpy array encoding
        self.known_ids = []          # List warga_id
        self.known_names = []        # List nama warga (untuk display)
        self._loaded = False

    def load_from_database(self, warga_list: list):
        """
        Muat semua face encoding dari data warga (hasil query DB).
        Panggil ini setiap kali sistem restart atau ada warga baru.
        """
        self.known_encodings = []
        self.known_ids = []
        self.known_names = []

        for warga in warga_list:
            if warga.get("face_encoding"):
                try:
                    encoding = pickle.loads(warga["face_encoding"])
                    self.known_encodings.append(encoding)
                    self.known_ids.append(warga["id"])
                    self.known_names.append(warga["nama"])
                except Exception as e:
                    logger.error("Gagal load encoding warga %s: %s", warga["id"], e)

        self._loaded = True
        logger.info("✅ Loaded %d face encoding dari database", len(self.known_encodings))

    def capture_photo(self) -> tuple[bool, np.ndarray | None]:
        """
        Ambil satu frame dari kamera.
        Return: (success, frame_bgr)
        """
        if not FACE_RECOGNITION_AVAILABLE:
            logger.warning("Mock: simulasi capture foto")
            return True, None

        cap = cv2.VideoCapture(CAMERA_INDEX)
        if not cap.isOpened():
            logger.error("Kamera tidak bisa dibuka (index %d)", CAMERA_INDEX)
            return False, None

        ret, frame = cap.read()
        cap.release()

        if not ret:
            logger.error("Gagal mengambil frame dari kamera")
            return False, None

        return True, frame

    def enroll_wajah(self, frame: np.ndarray, warga_id: int, nama: str) -> tuple[bool, bytes | None, str]:
        """
        Daftarkan wajah baru dari frame kamera.
        Return: (success, face_encoding_bytes, foto_path)
        """
        if not FACE_RECOGNITION_AVAILABLE:
            # Mock mode: kembalikan encoding palsu
            dummy_encoding = np.zeros(128)
            encoding_bytes = pickle.dumps(dummy_encoding)
            foto_path = str(FACES_DIR / f"{warga_id}_{nama}.jpg")
            return True, encoding_bytes, foto_path

        # Konversi BGR → RGB untuk face_recognition
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Deteksi semua wajah
        face_locations = face_recognition.face_locations(rgb_frame, model="hog")

        if not face_locations:
            return False, None, ""

        # Ambil encoding wajah pertama yang ditemukan
        encodings = face_recognition.face_encodings(rgb_frame, face_locations)
        if not encodings:
            return False, None, ""

        encoding = encodings[0]
        encoding_bytes = pickle.dumps(encoding)

        # Simpan foto ke disk
        foto_filename = f"{warga_id}_{nama}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        foto_path = str(FACES_DIR / foto_filename)
        cv2.imwrite(foto_path, frame)

        # Update loaded encodings
        self.known_encodings.append(encoding)
        self.known_ids.append(warga_id)
        self.known_names.append(nama)

        logger.info("✅ Wajah %s berhasil didaftarkan", nama)
        return True, encoding_bytes, foto_path

    def identify_from_frame(self, frame: np.ndarray) -> tuple[int | None, str | None, float]:
        """
        Identifikasi wajah dari frame kamera.
        Return: (warga_id, nama, confidence) atau (None, None, 0.0)
        """
        if not FACE_RECOGNITION_AVAILABLE:
            # Mock: kembalikan None (tidak dikenali)
            return None, None, 0.0

        if not self.known_encodings:
            logger.warning("Belum ada face encoding terdaftar.")
            return None, None, 0.0

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame, model="hog")

        if not face_locations:
            return None, None, 0.0

        encodings = face_recognition.face_encodings(rgb_frame, face_locations)

        for encoding in encodings:
            distances = face_recognition.face_distance(self.known_encodings, encoding)
            best_idx = int(np.argmin(distances))
            best_distance = distances[best_idx]

            if best_distance <= FACE_RECOGNITION_TOLERANCE:
                confidence = round((1 - best_distance) * 100, 1)
                warga_id = self.known_ids[best_idx]
                nama = self.known_names[best_idx]
                logger.info("✅ Wajah dikenali: %s (%.1f%%)", nama, confidence)
                return warga_id, nama, confidence

        return None, None, 0.0

    def frame_to_base64(self, frame: np.ndarray) -> str:
        """Konversi frame ke base64 string untuk dikirim ke frontend."""
        if frame is None:
            return ""
        if not FACE_RECOGNITION_AVAILABLE:
            return ""
        _, buffer = cv2.imencode(".jpg", frame)
        return base64.b64encode(buffer).decode("utf-8")

    def scan_and_identify(self) -> tuple[int | None, str | None, float, str]:
        """
        Gabungkan capture + identify dalam satu langkah.
        Return: (warga_id, nama, confidence, frame_base64)
        """
        success, frame = self.capture_photo()
        if not success or frame is None:
            return None, None, 0.0, ""

        warga_id, nama, confidence = self.identify_from_frame(frame)
        frame_b64 = self.frame_to_base64(frame)
        return warga_id, nama, confidence, frame_b64


# Singleton instance
face_module = FaceRecognitionModule()
