"""
CekSehat - AI Engine (Ollama + Decision Making)
================================================
Menggunakan Ollama untuk:
- Generate pertanyaan gejala berdasarkan data sensor
- Analisis jawaban Ya/Tidak dari pengguna
- Menentukan Level keputusan (1=saran, 2=herbal, 3=darurat)
- Generate saran kesehatan yang tepat
"""

import json
import logging
import requests
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT

logger = logging.getLogger(__name__)


class AIEngine:
    """Engine AI menggunakan Ollama untuk analisis kesehatan lokal."""

    def __init__(self):
        self.base_url = OLLAMA_BASE_URL
        self.model = OLLAMA_MODEL
        self.available = self._check_ollama()

    def _check_ollama(self) -> bool:
        """Cek apakah Ollama server berjalan."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if r.status_code == 200:
                logger.info("✅ Ollama tersedia: %s", self.base_url)
                return True
        except Exception:
            pass
        logger.warning("⚠️  Ollama tidak tersedia. Menggunakan rule-based fallback.")
        return False

    def _chat(self, prompt: str, system_prompt: str = "") -> str:
        """Kirim prompt ke Ollama dan dapatkan respons."""
        if not self.available:
            return ""
        try:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt or self._system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 512}
            }
            r = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=OLLAMA_TIMEOUT
            )
            r.raise_for_status()
            return r.json()["message"]["content"].strip()
        except Exception as e:
            logger.error("Error Ollama: %s", e)
            return ""

    def _system_prompt(self) -> str:
        return (
            "Kamu adalah asisten kesehatan AI bernama CekSehat yang bekerja di puskesmas "
            "Indonesia. Tugasmu membantu warga mengidentifikasi kondisi kesehatan mereka "
            "berdasarkan data vital signs dari sensor. Gunakan Bahasa Indonesia yang sopan, "
            "mudah dipahami oleh masyarakat umum, dan tidak menakut-nakuti. "
            "Selalu rekomendasikan konsultasi dokter untuk kondisi serius."
        )

    # ─── Generate Pertanyaan Gejala ──────────────────────────────────────────
    def generate_questions(
        self,
        heart_rate: float,
        spo2: float,
        suhu: float,
        punya_penyakit_kritis: bool = False,
        riwayat_penyakit: str = ""
    ) -> list[dict]:
        """
        Generate 4–6 pertanyaan Ya/Tidak berdasarkan data sensor.
        Return: list of { "id": int, "pertanyaan": str }
        """
        prompt = f"""
Berdasarkan data pemeriksaan berikut:
- Detak Jantung (Heart Rate): {heart_rate} BPM
- Kadar Oksigen Darah (SpO2): {spo2}%
- Suhu Tubuh: {suhu}°C
- Riwayat Penyakit Kritis: {"Ada (" + riwayat_penyakit + ")" if punya_penyakit_kritis else "Tidak ada"}

Buatlah tepat 5 pertanyaan gejala dengan jawaban Ya/Tidak untuk menggali keluhan pengguna.
Pertanyaan harus relevan dengan data sensor di atas.

Format respons HARUS berupa JSON array seperti ini:
[
  {{"id": 1, "pertanyaan": "Apakah Anda merasa pusing atau sakit kepala?"}},
  {{"id": 2, "pertanyaan": "Apakah Anda merasakan sesak napas?"}},
  {{"id": 3, "pertanyaan": "Apakah Anda merasakan nyeri dada?"}},
  {{"id": 4, "pertanyaan": "Apakah Anda merasa lemas dan kelelahan berlebihan?"}},
  {{"id": 5, "pertanyaan": "Apakah Anda mengalami mual atau muntah?"}}
]

Hanya balas dengan JSON array, tanpa penjelasan tambahan.
"""
        raw = self._chat(prompt)
        try:
            # Ekstrak JSON dari respons
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
        except Exception as e:
            logger.error("Gagal parse pertanyaan AI: %s", e)

        # Fallback: pertanyaan statis
        return self._fallback_questions(heart_rate, spo2, suhu)

    def _fallback_questions(self, hr: float, spo2: float, suhu: float) -> list[dict]:
        """Pertanyaan statis jika Ollama tidak tersedia."""
        questions = [
            {"id": 1, "pertanyaan": "Apakah Anda merasakan pusing atau sakit kepala?"},
            {"id": 2, "pertanyaan": "Apakah Anda merasakan sesak napas atau sulit bernapas?"},
            {"id": 3, "pertanyaan": "Apakah Anda merasakan nyeri atau tekanan di dada?"},
            {"id": 4, "pertanyaan": "Apakah Anda merasa sangat lemas atau kelelahan?"},
            {"id": 5, "pertanyaan": "Apakah Anda mengalami mual, muntah, atau tidak nafsu makan?"},
        ]

        # Tambah pertanyaan spesifik sesuai kondisi sensor
        if suhu >= 38.0:
            questions.append({"id": 6, "pertanyaan": "Apakah Anda merasakan menggigil atau panas dingin?"})
        if spo2 < 95:
            questions.append({"id": 7, "pertanyaan": "Apakah bibir atau ujung jari Anda terasa kebiru-biruan?"})
        if hr > 100:
            questions.append({"id": 8, "pertanyaan": "Apakah jantung Anda terasa berdebar-debar kencang?"})

        return questions

    # ─── Tentukan Level Keputusan ─────────────────────────────────────────────
    def determine_level(
        self,
        heart_rate: float,
        spo2: float,
        suhu: float,
        jawaban: dict,
        punya_penyakit_kritis: bool = False
    ) -> int:
        """
        Tentukan level keputusan (1, 2, atau 3).
        Level 1: Normal, hanya saran
        Level 2: Perlu perhatian, saran herbal/mandiri
        Level 3: Darurat, kirim notifikasi puskesmas
        """
        critical_score = 0

        # ── Evaluasi Sensor ──
        if spo2 < 90:
            critical_score += 3
        elif spo2 < 95:
            critical_score += 1

        if heart_rate < 50 or heart_rate > 120:
            critical_score += 2
        elif heart_rate < 60 or heart_rate > 100:
            critical_score += 1

        if suhu >= 39.5:
            critical_score += 3
        elif suhu >= 38.0:
            critical_score += 1

        # ── Evaluasi Jawaban AI ──
        ya_count = sum(1 for v in jawaban.values() if v is True)

        if ya_count >= 3:
            critical_score += 2
        elif ya_count >= 1:
            critical_score += 1

        # ── Faktor Penyakit Kritis ──
        if punya_penyakit_kritis:
            critical_score += 1

        # ── Jawaban khusus gejala darurat ──
        gejala_darurat = ["nyeri dada", "sesak napas", "tidak sadarkan diri", "lumpuh"]
        for key, val in jawaban.items():
            if val and any(g in key.lower() for g in gejala_darurat):
                critical_score += 2

        # ── Tentukan Level ──
        if critical_score >= 5:
            return 3
        elif critical_score >= 2:
            return 2
        else:
            return 1

    # ─── Generate Saran ───────────────────────────────────────────────────────
    def generate_advice(
        self,
        level: int,
        heart_rate: float,
        spo2: float,
        suhu: float,
        jawaban: dict,
        nama: str = "Warga"
    ) -> dict:
        """
        Generate saran kesehatan sesuai level.
        Return: { "saran": str, "catatan": str }
        """
        prompt = f"""
Data pemeriksaan {nama}:
- Detak Jantung: {heart_rate} BPM
- SpO2: {spo2}%
- Suhu: {suhu}°C
- Gejala yang dikeluhkan: {[k for k, v in jawaban.items() if v]}
- Level Kondisi: {level} ({"Normal" if level==1 else "Perlu Perhatian" if level==2 else "DARURAT"})

{"Berikan saran singkat dan imbauan untuk tidak panik. Sampaikan secara menenangkan." if level == 1 else
 "Berikan saran penanganan mandiri dan rekomendasi obat herbal atau pertolongan pertama yang bisa dilakukan di rumah." if level == 2 else
 "Kondisi DARURAT. Informasikan bahwa bantuan medis sedang dipanggil. Berikan instruksi singkat sambil menunggu petugas."}

Format respons JSON:
{{"saran": "saran utama di sini", "catatan": "catatan tambahan singkat"}}

Hanya balas dengan JSON, tanpa penjelasan tambahan.
"""
        raw = self._chat(prompt)
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
        except Exception as e:
            logger.error("Gagal parse saran AI: %s", e)

        return self._fallback_advice(level, suhu, spo2, heart_rate)

    def _fallback_advice(self, level: int, suhu: float, spo2: float, hr: float) -> dict:
        """Saran statis jika Ollama tidak tersedia."""
        if level == 1:
            return {
                "saran": (
                    f"Kondisi Anda saat ini terlihat normal. Detak jantung {hr:.0f} BPM, "
                    f"kadar oksigen {spo2:.0f}%, dan suhu {suhu:.1f}°C masih dalam batas wajar. "
                    "Tetap jaga pola makan sehat, minum air cukup, dan istirahat yang baik."
                ),
                "catatan": "Tidak ada tanda-tanda kondisi darurat. Tetap pantau kesehatan Anda secara rutin."
            }
        elif level == 2:
            return {
                "saran": (
                    "Kondisi Anda perlu sedikit perhatian. Beberapa saran yang bisa dilakukan: "
                    "1) Istirahat yang cukup, 2) Minum air putih yang banyak, "
                    "3) Konsumsi jahe hangat atau madu untuk meredakan gejala, "
                    "4) Hindari aktivitas berat untuk sementara. "
                    "Jika gejala memburuk atau tidak membaik dalam 24 jam, segera ke puskesmas."
                ),
                "catatan": "Pantau kondisi secara berkala. Segera ke fasilitas kesehatan jika memburuk."
            }
        else:
            return {
                "saran": (
                    "KONDISI DARURAT! Tim medis sedang dihubungi untuk membantu Anda. "
                    "Mohon tetap tenang dan duduk atau berbaring di tempat yang aman. "
                    "Jangan lakukan aktivitas fisik berat. Jika ada keluarga atau orang di sekitar, "
                    "minta mereka untuk menemani Anda. Bantuan akan segera tiba."
                ),
                "catatan": "Notifikasi darurat telah dikirimkan ke puskesmas terdekat."
            }

    def full_analysis(
        self,
        warga: dict,
        sensor_data: dict,
        jawaban: dict
    ) -> dict:
        """
        Analisis lengkap: tentukan level + generate saran.
        Return: { "level": int, "saran": str, "catatan": str }
        """
        hr = sensor_data["heart_rate"]
        spo2 = sensor_data["spo2"]
        suhu = sensor_data["suhu"]
        nama = warga.get("nama", "Warga")
        punya_kritis = bool(warga.get("punya_penyakit_kritis", 0))

        level = self.determine_level(hr, spo2, suhu, jawaban, punya_kritis)
        advice = self.generate_advice(level, hr, spo2, suhu, jawaban, nama)

        return {
            "level": level,
            "saran": advice.get("saran", ""),
            "catatan": advice.get("catatan", "")
        }


# Singleton instance
ai_engine = AIEngine()
