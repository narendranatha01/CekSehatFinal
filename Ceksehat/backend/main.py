"""
CekSehat - FastAPI Backend Utama
==================================
Semua endpoint API untuk sistem CekSehat.
"""

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from config import API_HOST, API_PORT, BASE_DIR, VIDEOS_DIR, VIDEO_DURATION
from database.db import (
    init_database, get_all_warga, get_warga_by_id,
    insert_warga, insert_pemeriksaan, update_pemeriksaan,
    get_riwayat_warga
)
from modules.face_recognition_module import face_module
from modules.sensor_reader import sensor_reader
from modules.ai_engine import ai_engine
from modules.telegram_notifier import telegram_notifier

# ─── Setup Logging ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("ceksehat")

# ─── Inisialisasi ─────────────────────────────────────────────────────────────
init_database()

app = FastAPI(
    title="CekSehat API",
    description="Sistem AI Kesehatan Lokal - Raspberry Pi 5",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend static files
frontend_dir = BASE_DIR / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

# ─── State global sesi pemeriksaan ────────────────────────────────────────────
active_sessions: dict = {}  # session_id → data sesi


# ─── Pydantic Models ──────────────────────────────────────────────────────────
class WargaCreate(BaseModel):
    nama: str
    umur: int
    tempat_lahir: str
    jenis_kelamin: str
    riwayat_penyakit: str = ""
    punya_penyakit_kritis: int = 0
    no_hp: str = ""
    alamat: str = ""

class JawabanAI(BaseModel):
    session_id: str
    jawaban: dict  # { "pertanyaan ke-1": True/False, ... }

class StartSession(BaseModel):
    warga_id: int

class AnalysisRequest(BaseModel):
    session_id: str
    jawaban: dict


# ═══════════════════════════════════════════════════════════════════════════════
# ROOT - Serve Frontend
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/")
async def root():
    index_path = frontend_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "CekSehat API berjalan. Frontend tidak ditemukan di /frontend/index.html"}


# ═══════════════════════════════════════════════════════════════════════════════
# WARGA - Manajemen Data Warga
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/api/warga")
async def api_get_all_warga():
    """Ambil daftar semua warga (tanpa face encoding untuk keamanan)."""
    warga_list = get_all_warga()
    # Hapus face_encoding dari response (data biner besar)
    for w in warga_list:
        w.pop("face_encoding", None)
    return {"success": True, "data": warga_list}


@app.get("/api/warga/{warga_id}")
async def api_get_warga(warga_id: int):
    """Ambil data satu warga berdasarkan ID."""
    warga = get_warga_by_id(warga_id)
    if not warga:
        raise HTTPException(status_code=404, detail="Warga tidak ditemukan")
    warga.pop("face_encoding", None)
    return {"success": True, "data": warga}


@app.post("/api/warga")
async def api_create_warga(data: WargaCreate):
    """Daftarkan warga baru (tanpa wajah dulu)."""
    warga_data = data.dict()
    warga_data["face_encoding"] = None
    warga_data["foto_path"] = ""
    warga_id = insert_warga(warga_data)
    return {"success": True, "warga_id": warga_id, "message": "Warga berhasil didaftarkan"}


@app.get("/api/warga/{warga_id}/riwayat")
async def api_riwayat(warga_id: int):
    """Ambil riwayat pemeriksaan warga."""
    riwayat = get_riwayat_warga(warga_id)
    return {"success": True, "data": riwayat}


# ═══════════════════════════════════════════════════════════════════════════════
# FACE RECOGNITION
# ═══════════════════════════════════════════════════════════════════════════════
@app.post("/api/face/load")
async def api_load_faces():
    """Muat semua face encoding dari database ke memori."""
    warga_list = get_all_warga()
    face_module.load_from_database(warga_list)
    return {"success": True, "loaded": len(face_module.known_ids)}


@app.post("/api/face/identify")
async def api_identify_face():
    """
    Scan kamera dan identifikasi wajah.
    Return: data warga jika dikenali, atau status 'unknown'.
    """
    # Pastikan encoding sudah dimuat
    if not face_module._loaded:
        warga_list = get_all_warga()
        face_module.load_from_database(warga_list)

    warga_id, nama, confidence, frame_b64 = face_module.scan_and_identify()

    if warga_id:
        warga = get_warga_by_id(warga_id)
        if warga:
            warga.pop("face_encoding", None)
        return {
            "success": True,
            "recognized": True,
            "warga_id": warga_id,
            "nama": nama,
            "confidence": confidence,
            "frame_base64": frame_b64,
            "warga": warga
        }
    else:
        return {
            "success": True,
            "recognized": False,
            "frame_base64": frame_b64,
            "message": "Wajah tidak dikenali. Silakan daftar terlebih dahulu."
        }


@app.post("/api/face/enroll/{warga_id}")
async def api_enroll_face(warga_id: int):
    """
    Ambil foto dari kamera dan daftarkan wajah warga ke database.
    """
    from database.db import get_connection
    warga = get_warga_by_id(warga_id)
    if not warga:
        raise HTTPException(status_code=404, detail="Warga tidak ditemukan")

    success, frame = face_module.capture_photo()
    if not success or frame is None:
        # Mock mode: simpan encoding kosong
        pass

    success_enroll, encoding_bytes, foto_path = face_module.enroll_wajah(
        frame, warga_id, warga["nama"]
    )

    if not success_enroll and frame is not None:
        raise HTTPException(
            status_code=400,
            detail="Wajah tidak terdeteksi di kamera. Pastikan wajah terlihat jelas."
        )

    # Simpan ke database
    conn = get_connection()
    conn.execute(
        "UPDATE warga SET face_encoding=?, foto_path=?, updated_at=? WHERE id=?",
        (encoding_bytes, foto_path, datetime.now().isoformat(), warga_id)
    )
    conn.commit()
    conn.close()

    # Reload face encodings
    warga_list = get_all_warga()
    face_module.load_from_database(warga_list)

    frame_b64 = face_module.frame_to_base64(frame) if frame is not None else ""
    return {
        "success": True,
        "message": f"Wajah {warga['nama']} berhasil didaftarkan",
        "foto_path": foto_path,
        "frame_base64": frame_b64
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SENSOR
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/api/sensor/read")
async def api_read_sensor():
    """Baca semua sensor (HR, SpO2, Suhu)."""
    data = sensor_reader.read_all()
    classification = sensor_reader.classify_vital_signs(
        data["heart_rate"], data["spo2"], data["suhu"]
    )
    return {"success": True, "sensor": data, "classification": classification}


# ═══════════════════════════════════════════════════════════════════════════════
# ALUR PEMERIKSAAN (SESSION-BASED)
# ═══════════════════════════════════════════════════════════════════════════════
@app.post("/api/session/start")
async def api_start_session(data: StartSession):
    """
    Mulai sesi pemeriksaan untuk seorang warga.
    Return: session_id untuk tracking alur.
    """
    warga = get_warga_by_id(data.warga_id)
    if not warga:
        raise HTTPException(status_code=404, detail="Warga tidak ditemukan")

    session_id = str(uuid.uuid4())[:8].upper()
    active_sessions[session_id] = {
        "warga_id": data.warga_id,
        "warga": {k: v for k, v in warga.items() if k != "face_encoding"},
        "step": "sensor",
        "sensor_data": None,
        "pertanyaan": [],
        "jawaban": {},
        "pemeriksaan_id": None,
        "audio_path": "",
        "result": None,
        "created_at": datetime.now().isoformat()
    }

    logger.info("🟢 Sesi %s dimulai untuk warga: %s", session_id, warga["nama"])
    warga.pop("face_encoding", None)
    return {"success": True, "session_id": session_id, "warga": warga}


@app.post("/api/session/{session_id}/sensor")
async def api_session_sensor(session_id: str):
    """
    Langkah 2: Baca sensor dan simpan hasilnya ke sesi.
    """
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Sesi tidak ditemukan")

    sesi = active_sessions[session_id]
    sensor_data = sensor_reader.read_all()
    classification = sensor_reader.classify_vital_signs(
        sensor_data["heart_rate"], sensor_data["spo2"], sensor_data["suhu"]
    )

    sesi["sensor_data"] = sensor_data
    sesi["classification"] = classification
    sesi["step"] = "questions"

    return {
        "success": True,
        "sensor": sensor_data,
        "classification": classification
    }


@app.post("/api/session/{session_id}/questions")
async def api_session_questions(session_id: str):
    """
    Langkah 3: Generate pertanyaan AI berdasarkan data sensor.
    """
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Sesi tidak ditemukan")

    sesi = active_sessions[session_id]
    if not sesi.get("sensor_data"):
        raise HTTPException(status_code=400, detail="Baca sensor terlebih dahulu")

    warga = sesi["warga"]
    sd = sesi["sensor_data"]

    pertanyaan = ai_engine.generate_questions(
        heart_rate=sd["heart_rate"],
        spo2=sd["spo2"],
        suhu=sd["suhu"],
        punya_penyakit_kritis=bool(warga.get("punya_penyakit_kritis", 0)),
        riwayat_penyakit=warga.get("riwayat_penyakit", "")
    )

    sesi["pertanyaan"] = pertanyaan
    sesi["step"] = "answering"

    return {"success": True, "pertanyaan": pertanyaan}


@app.post("/api/session/{session_id}/answers")
async def api_session_answers(session_id: str, data: JawabanAI):
    """
    Langkah 4: Terima jawaban Ya/Tidak dari pengguna.
    """
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Sesi tidak ditemukan")

    sesi = active_sessions[session_id]
    sesi["jawaban"] = data.jawaban
    sesi["step"] = "recording"

    return {"success": True, "message": "Jawaban disimpan. Lanjut ke perekaman video."}


@app.post("/api/session/{session_id}/record/upload")
async def api_upload_audio(session_id: str, audio: UploadFile = File(...)):
    """
    Langkah 5: Menerima file audio keluhan dari frontend.
    """
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Sesi tidak ditemukan")

    sesi = active_sessions[session_id]
    warga_id = sesi["warga_id"]

    # Buat ID sementara untuk nama file
    temp_id = int(datetime.now().timestamp())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Ambil ekstensi dari filename asli atau gunakan .webm sbg default
    ext = audio.filename.split('.')[-1] if '.' in audio.filename else 'webm'
    filename = f"keluhan_{warga_id}_{temp_id}_{timestamp}.{ext}"
    audio_path = VIDEOS_DIR / filename

    try:
        content = await audio.read()
        with open(audio_path, "wb") as f:
            f.write(content)
        sesi["audio_path"] = str(audio_path.resolve())
        sesi["recording_done"] = True
        logger.info("🎙️ Rekaman audio diterima: %s", audio_path)
    except Exception as e:
        logger.error("Gagal menyimpan audio: %s", e)
        raise HTTPException(status_code=500, detail="Gagal menyimpan audio")

    return {
        "success": True,
        "audio_path": sesi["audio_path"],
        "message": "Audio berhasil diunggah"
    }


@app.post("/api/session/{session_id}/analyze")
async def api_analyze(session_id: str, background_tasks: BackgroundTasks):
    """
    Langkah 6: Analisis AI + tentukan level + simpan ke DB + kirim Telegram jika Level 3.
    """
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Sesi tidak ditemukan")

    sesi = active_sessions[session_id]
    warga = sesi["warga"]
    sd = sesi["sensor_data"]
    jawaban = sesi.get("jawaban", {})

    # Analisis AI
    result = ai_engine.full_analysis(warga, sd, jawaban)
    sesi["result"] = result

    # Simpan ke database
    periksa_id = insert_pemeriksaan({
        "warga_id": sesi["warga_id"],
        "heart_rate": sd["heart_rate"],
        "spo2": sd["spo2"],
        "suhu": sd["suhu"],
        "pertanyaan_ai": json.dumps(sesi.get("pertanyaan", []), ensure_ascii=False),
        "jawaban_ai": json.dumps(jawaban, ensure_ascii=False),
        "keputusan_level": result["level"],
        "saran_ai": result["saran"],
        "catatan_ai": result["catatan"],
        "video_path": sesi.get("audio_path", "")
    })
    sesi["pemeriksaan_id"] = periksa_id

    # Kirim Telegram untuk setiap pemeriksaan
    audio_path = sesi.get("audio_path", "")
    logger.info("[ANALYZE] audio_path yang akan dikirim ke Telegram: '%s'", audio_path)
    background_tasks.add_task(
        telegram_notifier.send_examination_report,
        warga=warga,
        sensor_data=sd,
        saran_ai=result["saran"],
        level=result["level"],
        audio_path=audio_path,
        jawaban=jawaban
    )
    update_pemeriksaan(periksa_id, {"telegram_sent": 1})

    sesi["step"] = "result"
    logger.info(
        "✅ Pemeriksaan selesai: %s | Level %d | ID=%d",
        warga["nama"], result["level"], periksa_id
    )

    return {
        "success": True,
        "level": result["level"],
        "saran": result["saran"],
        "catatan": result["catatan"],
        "pemeriksaan_id": periksa_id,
        "telegram_sent": result["level"] == 3
    }


@app.delete("/api/session/{session_id}")
async def api_end_session(session_id: str):
    """Akhiri dan hapus sesi dari memori."""
    if session_id in active_sessions:
        del active_sessions[session_id]
    return {"success": True, "message": "Sesi diakhiri"}


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/api/status")
async def api_status():
    """Status sistem keseluruhan."""
    return {
        "success": True,
        "system": "CekSehat",
        "version": "1.0.0",
        "ollama_available": ai_engine.available,
        "sensor_mock_mode": sensor_reader.mock_mode,
        "telegram_enabled": telegram_notifier.enabled,
        "active_sessions": len(active_sessions),
        "time": datetime.now().isoformat()
    }


@app.post("/api/telegram/test")
async def api_telegram_test():
    """Kirim pesan test ke Telegram."""
    success = telegram_notifier.test_connection()
    return {"success": success, "message": "Pesan test terkirim" if success else "Gagal kirim. Cek konfigurasi."}


@app.get("/api/videos/{filename}")
async def api_get_video(filename: str):
    """Stream file video dari folder videos."""
    video_path = VIDEOS_DIR / filename
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video tidak ditemukan")
    return FileResponse(str(video_path), media_type="video/mp4")


# ═══════════════════════════════════════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════════════════════════════════════
@app.on_event("startup")
async def on_startup():
    logger.info("=" * 50)
    logger.info("🏥 CekSehat v1.0.0 - Sistem AI Kesehatan Lokal")
    logger.info("=" * 50)

    # Muat face encodings dari DB
    warga_list = get_all_warga()
    face_module.load_from_database(warga_list)
    logger.info("👥 %d warga terdaftar dalam database", len(warga_list))
    logger.info("🌐 Akses UI: http://localhost:%d", API_PORT)
    logger.info("📚 API Docs: http://localhost:%d/docs", API_PORT)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=API_HOST, port=API_PORT, reload=True)
