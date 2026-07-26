"""
CekSehat - Database Initialization & Connection
================================================
Menggunakan SQLite. Semua data disimpan lokal di Raspberry Pi.
"""

import sqlite3
import logging
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import DATABASE_PATH

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    """Buat koneksi ke SQLite database."""
    conn = sqlite3.connect(str(DATABASE_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row  # Hasil query bisa diakses seperti dict
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # Performa lebih baik
    return conn


def init_database():
    """Buat semua tabel jika belum ada."""
    conn = get_connection()
    cursor = conn.cursor()

    # ─── Tabel Warga ────────────────────────────────────────  ─────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS warga (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            nama                TEXT NOT NULL,
            umur                INTEGER NOT NULL,
            tempat_lahir        TEXT NOT NULL,
            jenis_kelamin       TEXT NOT NULL CHECK(jenis_kelamin IN ('Laki-laki', 'Perempuan')),
            riwayat_penyakit    TEXT DEFAULT '',
            punya_penyakit_kritis INTEGER DEFAULT 0,
            face_encoding       BLOB,
            foto_path           TEXT,
            no_hp               TEXT DEFAULT '',
            alamat              TEXT DEFAULT '',
            created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ─── Tabel Pemeriksaan ────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pemeriksaan (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            warga_id            INTEGER NOT NULL REFERENCES warga(id),
            heart_rate          REAL,
            spo2                REAL,
            suhu                REAL,
            pertanyaan_ai       TEXT DEFAULT '[]',
            jawaban_ai          TEXT DEFAULT '{}',
            keputusan_level     INTEGER DEFAULT 1,
            saran_ai            TEXT DEFAULT '',
            catatan_ai          TEXT DEFAULT '',
            video_path          TEXT DEFAULT '',
            telegram_sent       INTEGER DEFAULT 0,
            created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ─── Tabel Sesi (tracking alur wizard) ───────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sesi (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            session_token       TEXT UNIQUE NOT NULL,
            warga_id            INTEGER REFERENCES warga(id),
            pemeriksaan_id      INTEGER REFERENCES pemeriksaan(id),
            step                TEXT DEFAULT 'login',
            created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at          DATETIME
        )
    """)

    # ─── Seed Data Awal (Jika Kosong) ────────────────────────────────────────
    cursor.execute("SELECT COUNT(*) as count FROM warga")
    row = cursor.fetchone()
    if row and row['count'] == 0:
        cursor.execute("""
            INSERT INTO warga (nama, umur, tempat_lahir, jenis_kelamin, riwayat_penyakit, punya_penyakit_kritis, no_hp, alamat)
            VALUES ('Daniel', 21, 'Masela', 'Laki-laki', 'Tidak ada', 0, '08123456789', '')
        """)
        logger.info("✅ Data default warga (Daniel) berhasil ditambahkan.")

    conn.commit()
    conn.close()
    logger.info("✅ Database berhasil diinisialisasi: %s", DATABASE_PATH)


def insert_warga(data: dict) -> int:
    """Tambah warga baru ke database. Kembalikan ID warga."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO warga (nama, umur, tempat_lahir, jenis_kelamin,
                           riwayat_penyakit, punya_penyakit_kritis,
                           face_encoding, foto_path, no_hp, alamat)
        VALUES (:nama, :umur, :tempat_lahir, :jenis_kelamin,
                :riwayat_penyakit, :punya_penyakit_kritis,
                :face_encoding, :foto_path, :no_hp, :alamat)
    """, data)
    warga_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return warga_id


def get_all_warga() -> list:
    """Ambil semua data warga (termasuk face encoding untuk recognition)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM warga ORDER BY nama")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_warga_by_id(warga_id: int) -> dict | None:
    """Ambil data satu warga berdasarkan ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM warga WHERE id = ?", (warga_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def insert_pemeriksaan(data: dict) -> int:
    """Simpan hasil pemeriksaan. Kembalikan ID pemeriksaan."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO pemeriksaan (warga_id, heart_rate, spo2, suhu,
                                 pertanyaan_ai, jawaban_ai, keputusan_level,
                                 saran_ai, catatan_ai, video_path)
        VALUES (:warga_id, :heart_rate, :spo2, :suhu,
                :pertanyaan_ai, :jawaban_ai, :keputusan_level,
                :saran_ai, :catatan_ai, :video_path)
    """, data)
    periksa_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return periksa_id


def update_pemeriksaan(periksa_id: int, data: dict):
    """Update data pemeriksaan (misalnya setelah tanya jawab AI selesai)."""
    conn = get_connection()
    cursor = conn.cursor()
    set_clause = ", ".join([f"{k} = :{k}" for k in data.keys()])
    data["periksa_id"] = periksa_id
    cursor.execute(f"UPDATE pemeriksaan SET {set_clause} WHERE id = :periksa_id", data)
    conn.commit()
    conn.close()


def get_riwayat_warga(warga_id: int, limit: int = 5) -> list:
    """Ambil riwayat pemeriksaan terbaru seorang warga."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM pemeriksaan
        WHERE warga_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    """, (warga_id, limit))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_database()
    print("Database berhasil diinisialisasi!")
