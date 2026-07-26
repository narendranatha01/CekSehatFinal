"""
CekSehat - Modul Notifikasi Telegram
=====================================
Mengirim notifikasi darurat ke puskesmas melalui Telegram Bot.
Termasuk: data pemeriksaan (PDF), profil warga, dan video rekaman keluhan.
"""

import logging
import requests
import json
import threading
import time
import tempfile
import os
from pathlib import Path
from datetime import datetime
import sys

# PDF generation
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, PUSKESMAS_NAME, SYSTEM_NAME

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Pengirim notifikasi Telegram untuk kondisi darurat."""

    def __init__(self):
        self.token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        self.enabled = self._validate_config()
        self._offset = 0
        self._polling_thread = None
        self._stop_polling = False

    def _validate_config(self) -> bool:
        """Cek apakah konfigurasi Telegram sudah diisi."""
        if "MASUKKAN" in self.token or "MASUKKAN" in str(self.chat_id):
            logger.warning(
                "⚠️  Telegram belum dikonfigurasi. "
                "Isi TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID di config.py"
            )
            return False
        return True

    def _send_message(self, text: str, parse_mode: str = "HTML", chat_id: int = None) -> bool:
        """Kirim pesan teks ke Telegram."""
        if not self.enabled:
            logger.warning("Telegram tidak aktif. Pesan tidak dikirim.")
            logger.info("--- SIMULASI PESAN TELEGRAM ---\n%s\n---", text)
            return False

        target_chat = chat_id if chat_id else self.chat_id

        try:
            r = requests.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": target_chat,
                    "text": text,
                    "parse_mode": parse_mode
                },
                timeout=30
            )
            r.raise_for_status()
            logger.info("✅ Pesan Telegram terkirim")
            return True
        except Exception as e:
            logger.error("❌ Gagal kirim pesan Telegram: %s", e)
            return False

    def _send_voice(self, audio_path: str, caption: str = "") -> bool:
        """Kirim file suara ke Telegram."""
        if not self.enabled:
            logger.warning("Telegram tidak aktif. Suara tidak dikirim.")
            return False

        path = Path(audio_path)
        if not path.exists():
            logger.error("File suara tidak ditemukan: %s", audio_path)
            return False

        size_mb = path.stat().st_size / (1024 * 1024)
        logger.info("📤 Mengirim suara ke Telegram: %s (%.2f MB)", path.name, size_mb)

        try:
            with open(path, "rb") as f:
                r = requests.post(
                    f"{self.api_url}/sendVoice",
                    data={
                        "chat_id": self.chat_id,
                        "caption": caption[:1024],
                        "parse_mode": "HTML"
                    },
                    files={"voice": (path.name, f, "audio/ogg")},
                    timeout=120
                )
                r.raise_for_status()
                logger.info("✅ Suara Telegram terkirim: %s", path.name)
                return True
        except Exception as e:
            logger.warning("⚠️ sendVoice gagal (%.2f MB): %s — mencoba kirim sebagai dokumen...", size_mb, e)

        # Fallback: kirim sebagai dokumen
        try:
            with open(path, "rb") as f:
                r = requests.post(
                    f"{self.api_url}/sendDocument",
                    data={
                        "chat_id": self.chat_id,
                        "caption": caption[:1024],
                        "parse_mode": "HTML"
                    },
                    files={"document": (path.name, f, "audio/ogg")},
                    timeout=120
                )
                r.raise_for_status()
                logger.info("✅ Suara terkirim sebagai dokumen: %s", path.name)
                return True
        except Exception as e:
            logger.error("❌ Gagal kirim suara/dokumen Telegram: %s", e)
            return False

    def _send_document(self, file_path: str, caption: str = "") -> bool:
        """Kirim file dokumen ke Telegram."""
        if not self.enabled:
            return False

        path = Path(file_path)
        if not path.exists():
            return False

        try:
            with open(path, "rb") as f:
                r = requests.post(
                    f"{self.api_url}/sendDocument",
                    data={"chat_id": self.chat_id, "caption": caption},
                    files={"document": (path.name, f)},
                    timeout=60
                )
                r.raise_for_status()
                return True
        except Exception as e:
            logger.error("❌ Gagal kirim dokumen Telegram: %s", e)
            return False

    # ─── Polling Updates ──────────────────────────────────────────────────────
    def start_polling(self):
        """Mulai thread untuk memantau pesan masuk dari Telegram."""
        if not self.enabled:
            return
        if self._polling_thread and self._polling_thread.is_alive():
            return
        
        self._stop_polling = False
        self._polling_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._polling_thread.start()
        logger.info("📡 Telegram polling dimulai...")

    def stop_polling(self):
        """Hentikan thread polling."""
        self._stop_polling = True

    def _poll_loop(self):
        while not self._stop_polling:
            try:
                r = requests.get(
                    f"{self.api_url}/getUpdates",
                    params={"offset": self._offset, "timeout": 20},
                    timeout=25
                )
                if r.status_code == 200:
                    data = r.json()
                    for item in data.get("result", []):
                        self._offset = item["update_id"] + 1
                        if "message" in item:
                            self._handle_message(item["message"])
            except requests.exceptions.Timeout:
                pass
            except Exception as e:
                logger.error("Kesalahan saat polling Telegram: %s", e)
                time.sleep(5)

    def _handle_message(self, message: dict):
        text = message.get("text", "").strip()
        chat_id = message.get("chat", {}).get("id")
        
        if not text or not chat_id:
            return

        if text.startswith("/start") or text.startswith("/help"):
            help_text = (
                "🤖 <b>Bot Admin CekSehat</b>\n\n"
                "Gunakan bot ini untuk mendaftarkan warga baru.\n\n"
                "<b>Format Pendaftaran:</b>\n"
                "<code>/daftar Nama Lengkap, Umur, Jenis Kelamin (L/P), No HP</code>\n\n"
                "<b>Contoh:</b>\n"
                "<code>/daftar Budi Santoso, 45, L, 081234567890</code>"
            )
            self._send_message(help_text, chat_id=chat_id)
        
        elif text.startswith("/daftar"):
            content = text.replace("/daftar", "").strip()
            parts = [p.strip() for p in content.split(",")]
            
            if len(parts) < 3:
                self._send_message("❌ <b>Format salah!</b>\nHarap gunakan format:\n<code>/daftar Nama, Umur, L/P, No HP</code>", chat_id=chat_id)
                return
                
            try:
                nama = parts[0]
                umur = int(parts[1])
                jk_code = parts[2].upper()
                jk = "Laki-laki" if jk_code in ["L", "LAKI-LAKI", "LAKI"] else ("Perempuan" if jk_code in ["P", "PEREMPUAN"] else jk_code)
                hp = parts[3] if len(parts) > 3 else ""
                
                from database.db import insert_warga
                
                warga_data = {
                    "nama": nama,
                    "umur": umur,
                    "tempat_lahir": "",
                    "jenis_kelamin": jk,
                    "riwayat_penyakit": "",
                    "punya_penyakit_kritis": 0,
                    "no_hp": hp,
                    "alamat": "",
                    "face_encoding": None,
                    "foto_path": ""
                }
                warga_id = insert_warga(warga_data)
                
                self._send_message(f"✅ <b>Pendaftaran Berhasil!</b>\n\nNama: {nama}\nID Warga: {warga_id}\n\nSilakan arahkan warga untuk memilih namanya di layar CekSehat.", chat_id=chat_id)
                logger.info("Berhasil mendaftarkan warga via Telegram: %s", nama)
            except ValueError:
                self._send_message("❌ <b>Format umur salah!</b>\nUmur harus berupa angka.", chat_id=chat_id)
            except Exception as e:
                self._send_message(f"❌ <b>Terjadi kesalahan:</b> {e}", chat_id=chat_id)
                logger.error("Gagal mendaftar via Telegram: %s", e)

    # ─── Generate PDF Laporan ─────────────────────────────────────────────────
    def _generate_pdf_report(
        self,
        warga: dict,
        sensor_data: dict,
        saran_ai: str,
        level: int,
        jawaban: dict,
        now: str
    ) -> str:
        """
        Buat file PDF laporan pemeriksaan.
        Return: path ke file PDF sementara.
        """
        nama = warga.get("nama", "Tidak Diketahui")
        umur = warga.get("umur", "-")
        jk = warga.get("jenis_kelamin", "-")
        ttl = warga.get("tempat_lahir", "-")
        riwayat = warga.get("riwayat_penyakit", "Tidak ada") or "Tidak ada"
        hr = sensor_data.get("heart_rate", 0)
        spo2 = sensor_data.get("spo2", 0)
        suhu = sensor_data.get("suhu", 0)

        level_str = "AMAN" if level == 1 else "PERLU PERHATIAN" if level == 2 else "DARURAT"
        level_color_map = {
            1: colors.HexColor("#16a34a"),   # hijau
            2: colors.HexColor("#d97706"),   # oranye
            3: colors.HexColor("#dc2626"),   # merah
        }
        level_color = level_color_map.get(level, colors.gray)
        header_bg = colors.HexColor("#1e3a5f")

        gejala_ya = []
        if jawaban:
            gejala_ya = [k for k, v in jawaban.items() if v is True]

        # Buat file temp
        safe_nama = "".join(c for c in nama if c.isalnum() or c in " _-").strip().replace(" ", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_path = os.path.join(tempfile.gettempdir(), f"CekSehat_{safe_nama}_{timestamp}.pdf")

        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=A4,
            rightMargin=2*cm, leftMargin=2*cm,
            topMargin=2*cm, bottomMargin=2*cm
        )

        styles = getSampleStyleSheet()
        story = []

        # ── Gaya kustom ──
        title_style = ParagraphStyle(
            "Title", parent=styles["Normal"],
            fontSize=18, fontName="Helvetica-Bold",
            textColor=colors.white, alignment=TA_CENTER,
            spaceAfter=4
        )
        subtitle_style = ParagraphStyle(
            "Subtitle", parent=styles["Normal"],
            fontSize=10, fontName="Helvetica",
            textColor=colors.HexColor("#bfdbfe"), alignment=TA_CENTER,
            spaceAfter=2
        )
        section_style = ParagraphStyle(
            "Section", parent=styles["Normal"],
            fontSize=11, fontName="Helvetica-Bold",
            textColor=header_bg, spaceAfter=6, spaceBefore=12
        )
        body_style = ParagraphStyle(
            "Body", parent=styles["Normal"],
            fontSize=10, fontName="Helvetica",
            textColor=colors.HexColor("#1f2937"), spaceAfter=3,
            leading=14
        )
        ai_style = ParagraphStyle(
            "AI", parent=styles["Normal"],
            fontSize=10, fontName="Helvetica",
            textColor=colors.HexColor("#374151"),
            leading=15, spaceAfter=4
        )
        status_style = ParagraphStyle(
            "Status", parent=styles["Normal"],
            fontSize=14, fontName="Helvetica-Bold",
            textColor=colors.white, alignment=TA_CENTER
        )

        # ── Header Banner ──
        header_data = [
            [Paragraph(f"{SYSTEM_NAME} — Laporan Pemeriksaan Kesehatan", title_style)],
            [Paragraph(f"{PUSKESMAS_NAME}  |  {now}", subtitle_style)],
        ]
        header_table = Table(header_data, colWidths=[doc.width])
        header_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), header_bg),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("ROUNDEDCORNERS", [8, 8, 8, 8]),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 0.4*cm))

        # ── Status Badge ──
        status_data = [[Paragraph(f"STATUS KESEHATAN: {level_str}", status_style)]]
        status_table = Table(status_data, colWidths=[doc.width])
        status_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), level_color),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ]))
        story.append(status_table)
        story.append(Spacer(1, 0.5*cm))

        # ── Data Pasien ──
        story.append(Paragraph("👤  DATA PASIEN", section_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#d1d5db")))
        story.append(Spacer(1, 0.2*cm))

        pasien_data = [
            ["Nama Lengkap",    nama],
            ["Umur",           f"{umur} tahun"],
            ["Jenis Kelamin",  jk],
            ["Tempat Lahir",   ttl],
            ["Riwayat Penyakit", riwayat],
        ]
        col_label = ParagraphStyle("ColLabel", parent=styles["Normal"],
            fontSize=10, fontName="Helvetica-Bold", textColor=colors.HexColor("#374151"))
        col_value = ParagraphStyle("ColValue", parent=styles["Normal"],
            fontSize=10, fontName="Helvetica", textColor=colors.HexColor("#1f2937"))

        pasien_rows = [[Paragraph(k, col_label), Paragraph(str(v), col_value)] for k, v in pasien_data]
        pasien_table = Table(pasien_rows, colWidths=[5*cm, doc.width - 5*cm])
        pasien_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#f0f9ff"), colors.HexColor("#f8fafc")]),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
        ]))
        story.append(pasien_table)
        story.append(Spacer(1, 0.5*cm))

        # ── Hasil Sensor ──
        story.append(Paragraph("📊  HASIL PEMERIKSAAN SENSOR", section_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#d1d5db")))
        story.append(Spacer(1, 0.2*cm))

        def sensor_status(val, ok_fn):
            return ("Normal ✓", colors.HexColor("#16a34a")) if ok_fn(val) else ("Perhatian !", colors.HexColor("#dc2626"))

        hr_stat, hr_col  = sensor_status(hr,   lambda v: 60 <= v <= 100)
        spo2_stat, spo2_col = sensor_status(spo2, lambda v: v >= 95)
        suhu_stat, suhu_col = sensor_status(suhu, lambda v: v < 38.0)

        def make_sensor_row(label, value_str, status_str, status_color):
            lbl = Paragraph(label, col_label)
            val = Paragraph(f"<b>{value_str}</b>", ParagraphStyle(
                "Val", parent=styles["Normal"], fontSize=11, fontName="Helvetica-Bold",
                textColor=colors.HexColor("#1f2937")))
            stat = Paragraph(f"<b>{status_str}</b>", ParagraphStyle(
                "Stat", parent=styles["Normal"], fontSize=10, fontName="Helvetica-Bold",
                textColor=status_color, alignment=TA_CENTER))
            return [lbl, val, stat]

        sensor_rows = [
            make_sensor_row("Detak Jantung", f"{hr:.0f} BPM", hr_stat, hr_col),
            make_sensor_row("SpO₂ (Oksigen)", f"{spo2:.0f}%", spo2_stat, spo2_col),
            make_sensor_row("Suhu Tubuh", f"{suhu:.1f} °C", suhu_stat, suhu_col),
        ]
        sensor_table = Table(sensor_rows, colWidths=[4.5*cm, 5*cm, doc.width - 9.5*cm])
        sensor_table.setStyle(TableStyle([
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#f0fdf4"), colors.HexColor("#f8fafc")]),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
            ("ALIGN", (2, 0), (2, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(sensor_table)
        story.append(Spacer(1, 0.5*cm))

        # ── Tanya Jawab AI ──
        story.append(Paragraph("🩺  HASIL TANYA JAWAB AI", section_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#d1d5db")))
        story.append(Spacer(1, 0.2*cm))
        if jawaban:
            for q, a in jawaban.items():
                ans_fmt = "<b><font color='#dc2626'>Ya</font></b>" if a else "<b><font color='#16a34a'>Tidak</font></b>"
                story.append(Paragraph(f"• {q} : {ans_fmt}", body_style))
        else:
            story.append(Paragraph("• Tidak ada data tanya jawab", body_style))
        story.append(Spacer(1, 0.5*cm))

        # ── Analisis AI ──
        story.append(Paragraph("🤖  ANALISIS & REKOMENDASI AI", section_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#d1d5db")))
        story.append(Spacer(1, 0.2*cm))
        ai_box_data = [[Paragraph(saran_ai, ai_style)]]
        ai_box = Table(ai_box_data, colWidths=[doc.width])
        ai_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eff6ff")),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#93c5fd")),
        ]))
        story.append(ai_box)
        story.append(Spacer(1, 0.8*cm))

        # ── Footer ──
        footer_data = [[Paragraph(
            f"Dokumen ini dibuat otomatis oleh sistem {SYSTEM_NAME} · {PUSKESMAS_NAME}",
            ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8,
                fontName="Helvetica", textColor=colors.HexColor("#9ca3af"),
                alignment=TA_CENTER)
        )]]
        footer_table = Table(footer_data, colWidths=[doc.width])
        footer_table.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.HexColor("#d1d5db")),
        ]))
        story.append(footer_table)

        doc.build(story)
        logger.info("✅ PDF laporan dibuat: %s", pdf_path)
        return pdf_path

    # ─── Notifikasi Pemeriksaan ───────────────────────────────────────────────
    def send_examination_report(
        self,
        warga: dict,
        sensor_data: dict,
        saran_ai: str,
        level: int,
        audio_path: str = "",
        jawaban: dict = None
    ) -> bool:
        """
        Kirim laporan pemeriksaan ke puskesmas.

        Args:
            warga: data profil warga
            sensor_data: hasil pemeriksaan sensor
            saran_ai: rekomendasi dari AI
            level: tingkat kedaruratan (1=Aman, 2=Perhatian, 3=Darurat)
            audio_path: path file suara keluhan (opsional)
            jawaban: dict jawaban Ya/Tidak dari tanya jawab AI

        Return: True jika berhasil terkirim
        """
        now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        nama  = warga.get("nama", "Tidak Diketahui")
        umur  = warga.get("umur", "-")
        hr    = sensor_data.get("heart_rate", 0)
        spo2  = sensor_data.get("spo2", 0)
        suhu  = sensor_data.get("suhu", 0)

        level_str = "AMAN" if level == 1 else "PERLU PERHATIAN" if level == 2 else "DARURAT"
        emoji     = "✅" if level == 1 else "⚠️" if level == 2 else "🚨"

        logger.info("[TELEGRAM] Memproses laporan: %s | Level %d | audio_path='%s'",
                    nama, level, audio_path)

        # ── 1. Pesan teks singkat sebagai penanda ──
        short_msg = (
            f"{emoji} <b>LAPORAN PEMERIKSAAN BARU</b> {emoji}\n"
            f"<b>{PUSKESMAS_NAME}</b>\n"
            f"\n"
            f"🕐 <b>Waktu   :</b> {now}\n"
            f"👤 <b>Pasien  :</b> {nama} ({umur} tahun)\n"
            f"⚡ <b>Status  :</b> {level_str}\n"
            f"💓 <b>Nadi    :</b> {hr:.0f} BPM\n"
            f"🩸 <b>SpO₂    :</b> {spo2:.0f}%\n"
            f"🌡️ <b>Suhu    :</b> {suhu:.1f}°C\n"
        )
        if level == 3:
            short_msg += "\n🚨 <b>Harap segera tindak lanjuti!</b>"
        short_msg += "\n\n📄 Detail lengkap: lihat file PDF terlampir."
        if audio_path:
            short_msg += "\n🎙️ Rekaman suara keluhan pasien dilampirkan di bawah."

        msg_ok = self._send_message(short_msg)

        # ── 2. Generate & kirim PDF ──
        pdf_ok = False
        pdf_path = None
        try:
            pdf_path = self._generate_pdf_report(
                warga, sensor_data, saran_ai, level, jawaban or {}, now
            )
            pdf_caption = (
                f"📄 Laporan Pemeriksaan: {nama} | {now} | Status: {level_str}"
            )
            pdf_ok = self._send_document(pdf_path, caption=pdf_caption)
            logger.info("[TELEGRAM] Upload PDF selesai: %s", "OK" if pdf_ok else "GAGAL")
        except Exception as e:
            logger.error("❌ Gagal generate/kirim PDF: %s", e)
        finally:
            # Hapus file PDF sementara
            if pdf_path and os.path.exists(pdf_path):
                try:
                    os.remove(pdf_path)
                except Exception:
                    pass

        # ── 3. Kirim suara jika ada ──
        audio_ok = True
        if audio_path:
            audio_caption = (
                f"🎙️ Rekaman keluhan: {nama} ({umur} tahun)\n"
                f"Waktu: {now} | Status: {level_str}"
            )
            logger.info("[TELEGRAM] Memulai upload suara: %s", audio_path)
            audio_ok = self._send_voice(audio_path, caption=audio_caption)
            logger.info("[TELEGRAM] Upload suara selesai: %s", "OK" if audio_ok else "GAGAL")
        else:
            logger.warning("[TELEGRAM] audio_path kosong — suara tidak dikirim")

        success = msg_ok or pdf_ok
        logger.info(
            "📤 Notifikasi: pesan=%s, pdf=%s, audio=%s",
            "OK" if msg_ok else "GAGAL",
            "OK" if pdf_ok else "GAGAL",
            "OK" if audio_ok else "GAGAL/TIDAK ADA"
        )
        return success

    # ─── Test Koneksi ─────────────────────────────────────────────────────────
    def test_connection(self) -> bool:
        """Kirim pesan test untuk memverifikasi koneksi Telegram Bot."""
        test_msg = (
            f"✅ <b>{SYSTEM_NAME}</b> - Test Koneksi\n\n"
            f"Sistem CekSehat berhasil terhubung ke Telegram.\n"
            f"Waktu: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
            f"Notifikasi darurat akan muncul di sini."
        )
        return self._send_message(test_msg)


# Singleton instance
telegram_notifier = TelegramNotifier()
