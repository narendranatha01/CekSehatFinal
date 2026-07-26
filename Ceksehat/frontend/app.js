/* ══════════════════════════════════════════════════
   CekSehat — Frontend Application Logic
   ══════════════════════════════════════════════════ */

// ── State ──────────────────────────────────────────
const S = {
  wargaList:      [],
  selectedWarga:  null,
  sessionId:      null,
  sensorData:     null,
  sensorClass:    null,
  questions:      [],
  qIndex:         0,
  answers:        {},
  result:         null,
  camStream:      null,
  recInterval:    null,
  recPollInterval:null,
  recStartTime:   null,
  recDuration:    60,  // seconds — matches backend VIDEO_DURATION
  mediaRecorder:  null,
  audioChunks:    [],
};

// ── API helpers ─────────────────────────────────────
async function apiFetch(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  const txt = await r.text();
  if (!r.ok) throw new Error(txt || `HTTP ${r.status}`);
  return JSON.parse(txt);
}
const GET  = (p)    => apiFetch('GET',  p);
const POST = (p, b) => apiFetch('POST', p, b ?? {});

// ── Toast ───────────────────────────────────────────
let _toastTid;
function toast(msg, type = 'info') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `toast show ${type}`;
  clearTimeout(_toastTid);
  _toastTid = setTimeout(() => { el.className = 'toast'; }, 3200);
}

// ── Clock ────────────────────────────────────────────
(function clock() {
  const el = document.getElementById('header-time');
  const tick = () => {
    const n = new Date();
    el.textContent = [n.getHours(), n.getMinutes(), n.getSeconds()]
      .map(v => String(v).padStart(2,'0')).join(':');
  };
  tick(); setInterval(tick, 1000);
})();

// ── Step indicator ───────────────────────────────────
const STEP_MAP = {
  welcome: null, identify: 1, 'how-to-register': 1,
  confirm: 2, sensor: 3, questions: 4,
  recording: 5, analyzing: 5, result: 6
};

function setStepIndicator(active) {
  document.querySelectorAll('.step-dot').forEach((dot, i) => {
    const n = i + 1;
    dot.classList.remove('active','done');
    if (active === null) return;
    if (n < active)  dot.classList.add('done');
    if (n === active) dot.classList.add('active');
  });
  document.querySelectorAll('.step-line').forEach((ln, i) => {
    ln.classList.toggle('done', active !== null && i + 1 < active);
  });
}

// ── Screen navigation ────────────────────────────────
function goToScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  const scr = document.getElementById(`screen-${id}`);
  if (scr) scr.classList.add('active');
  const hdr = document.getElementById('app-header');
  hdr.style.display = (id === 'welcome') ? 'none' : 'flex';
  setStepIndicator(STEP_MAP[id] ?? null);
}

// ── Camera helpers ────────────────────────────────────
async function camStart(videoId) {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
      audio: false
    });
    const vid = document.getElementById(videoId);
    if (vid) { vid.srcObject = stream; }
    S.camStream = stream;
    return true;
  } catch (e) {
    console.warn('Camera unavailable:', e.message);
    return false;
  }
}

function camStop() {
  if (S.camStream) {
    S.camStream.getTracks().forEach(t => t.stop());
    S.camStream = null;
  }
}

// ════════════════════════════════════════════════════
// STEP 0 — Welcome
// ════════════════════════════════════════════════════
function startApp() {
  goToScreen('identify');
  loadIdentifyScreen();
}

// ════════════════════════════════════════════════════
// STEP 1 — Identify
// ════════════════════════════════════════════════════
async function loadIdentifyScreen() {
  // start webcam preview
  const ok = await camStart('camera-preview');
  const status  = document.getElementById('cam-status');
  const offMsg  = document.getElementById('cam-off-msg');
  if (ok) {
    status.style.display = 'flex';
    offMsg.style.display = 'none';
  } else {
    status.style.display = 'none';
    offMsg.style.display = 'flex';
  }

  // fetch warga list
  try {
    const res = await GET('/api/warga');
    S.wargaList = res.data || [];
    renderWargaList();
  } catch (e) {
    document.getElementById('warga-list').innerHTML =
      '<div class="list-placeholder">⚠️ Gagal memuat daftar warga</div>';
  }
}

function renderWargaList() {
  const el = document.getElementById('warga-list');
  if (!S.wargaList.length) {
    el.innerHTML = '<div class="list-placeholder">Belum ada warga terdaftar</div>';
    return;
  }
  el.innerHTML = S.wargaList.map(w => `
    <div class="warga-item" onclick="pickWarga(${w.id})">
      <div class="wi-avatar">${w.nama ? w.nama.charAt(0).toUpperCase() : '?'}</div>
      <div class="wi-info">
        <div class="wi-nama">${w.nama}</div>
        <div class="wi-sub">${w.umur} thn · ${w.jenis_kelamin}</div>
      </div>
      <span class="wi-arrow">›</span>
    </div>
  `).join('');
}

async function scanFace() {
  const btn = document.getElementById('btn-scan');
  btn.disabled = true;
  btn.innerHTML = '⏳ Scanning...';

  // Stop browser cam so server can open it (avoid conflict)
  camStop();

  try {
    const res = await POST('/api/face/identify');
    if (res.recognized && res.warga_id) {
      toast('✅ Wajah dikenali!', 'ok');
      S.selectedWarga = res.warga;
      showConfirm(res.warga);
    } else {
      toast('Wajah tidak dikenali — pilih dari daftar atau daftar baru', 'info');
      await camStart('camera-preview');
    }
  } catch (e) {
    toast('⚠️ Gagal scan: ' + e.message, 'err');
    await camStart('camera-preview');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '🔍 Scan Wajah';
  }
}

async function pickWarga(id) {
  camStop();
  try {
    const res = await GET(`/api/warga/${id}`);
    S.selectedWarga = res.data;
    showConfirm(res.data);
  } catch (e) {
    toast('Gagal memuat data warga', 'err');
  }
}

// ════════════════════════════════════════════════════
// STEP 1b — How to Register
// ════════════════════════════════════════════════════
function showHowToRegister() {
  camStop();
  goToScreen('how-to-register');
}

// ════════════════════════════════════════════════════
// STEP 2 — Confirm
// ════════════════════════════════════════════════════
function showConfirm(w) {
  document.getElementById('confirm-avatar').textContent = w.nama ? w.nama.charAt(0).toUpperCase() : '?';
  document.getElementById('confirm-name').textContent = w.nama;

  const rows = [
    ['Umur',             `${w.umur} tahun`],
    ['Jenis Kelamin',    w.jenis_kelamin || '—'],
    ['Tempat Lahir',     w.tempat_lahir  || '—'],
    ['Riwayat Penyakit', w.riwayat_penyakit || 'Tidak ada'],
    ['No. HP',           w.no_hp         || '—'],
  ];

  document.getElementById('confirm-details').innerHTML = rows.map(([lbl, val]) =>
    `<div class="detail-row">
       <span class="detail-label">${lbl}</span>
       <span class="detail-val">${val}</span>
     </div>`
  ).join('');

  goToScreen('confirm');
}

// ════════════════════════════════════════════════════
// STEP 3 — Session start + Sensor
// ════════════════════════════════════════════════════
async function startSession(btn) {
  btn.disabled = true;
  btn.textContent = 'Memulai sesi...';

  try {
    const res = await POST('/api/session/start', { warga_id: S.selectedWarga.id });
    S.sessionId = res.session_id;
    toast(`✅ Sesi dimulai — ID: ${res.session_id}`, 'ok');
    goToScreen('sensor');
  } catch (e) {
    toast('❌ Gagal mulai sesi: ' + e.message, 'err');
    btn.disabled = false;
    btn.textContent = 'Mulai Pemeriksaan →';
  }
}

async function readSensor(btn) {
  btn.disabled = true;
  btn.innerHTML = '⏳ Membaca sensor...';

  // show animated placeholder
  ['val-hr','val-spo2','val-suhu'].forEach(id => {
    document.getElementById(id).textContent = '···';
  });

  try {
    const res = await POST(`/api/session/${S.sessionId}/sensor`);
    S.sensorData  = res.sensor;
    S.sensorClass = res.classification;
    await animateSensorValues(res.sensor, res.classification);

    toast('✅ Sensor berhasil dibaca!', 'ok');
    btn.innerHTML = 'Lanjut ke Tanya Jawab →';
    btn.disabled = false;
    btn.onclick = null;
    btn.addEventListener('click', loadQuestions, { once: true });
  } catch (e) {
    toast('❌ Gagal baca sensor: ' + e.message, 'err');
    btn.disabled = false;
    btn.innerHTML = '📡 Baca Sensor';
  }
}

async function animateSensorValues(sensor, cls) {
  return new Promise(resolve => {
    let tick = 0;
    const id = setInterval(() => {
      tick++;
      const done = tick >= 14;
      document.getElementById('val-hr').textContent   = done ? sensor.heart_rate.toFixed(0)  : rnd(55,120);
      document.getElementById('val-spo2').textContent = done ? sensor.spo2.toFixed(0)         : rnd(93,100);
      document.getElementById('val-suhu').textContent = done ? sensor.suhu.toFixed(1)         : (36 + Math.random() * 1.8).toFixed(1);
      if (done) {
        clearInterval(id);
        applyVitalStyle('hr',   cls.heart_rate);
        applyVitalStyle('spo2', cls.spo2);
        applyVitalStyle('suhu', cls.suhu);
        resolve();
      }
    }, 90);
  });
}

function rnd(a, b) { return Math.floor(Math.random() * (b - a + 1)) + a; }

function applyVitalStyle(key, statusText) {
  const card  = document.getElementById(`vcard-${key}`);
  const badge = document.getElementById(`badge-${key}`);
  card.classList.remove('ok','warn','crit');

  const t = (statusText || '').toLowerCase();
  if (t.includes('kritis') || t.includes('sangat') || t.includes('tinggi') && t.includes('demam')) {
    card.classList.add('crit'); badge.textContent = '🚨 Kritis';
  } else if (t.includes('warn') || t.includes('sedikit') || t.includes('rendah') || t.includes('demam') || t.includes('tinggi')) {
    card.classList.add('warn'); badge.textContent = '⚠️ Perhatian';
  } else {
    card.classList.add('ok');   badge.textContent = '✅ Normal';
  }
}

// ════════════════════════════════════════════════════
// STEP 4 — AI Questions
// ════════════════════════════════════════════════════
async function loadQuestions() {
  // called when user clicks "Lanjut ke Tanya Jawab"
  const btn = document.getElementById('btn-read-sensor');
  btn.disabled = true;
  btn.innerHTML = '⏳ Memuat pertanyaan AI...';

  try {
    const res = await POST(`/api/session/${S.sessionId}/questions`);
    S.questions = (res.pertanyaan || []).map(q => typeof q === 'object' ? q.pertanyaan : q);
    S.qIndex    = 0;
    S.answers   = {};

    if (!S.questions.length) {
      // No questions — go straight to recording
      toast('Tidak ada pertanyaan AI — lanjut ke rekaman', 'info');
      await submitAnswers();
      return;
    }

    goToScreen('questions');
    renderQuestion();
  } catch (e) {
    toast('❌ Gagal memuat pertanyaan: ' + e.message, 'err');
    btn.disabled = false;
    btn.innerHTML = 'Lanjut ke Tanya Jawab →';
  }
}

function renderQuestion() {
  const q   = S.questions;
  const idx = S.qIndex;

  document.getElementById('q-progress').textContent = `Pertanyaan ${idx + 1} dari ${q.length}`;
  document.getElementById('q-number').textContent   = String(idx + 1).padStart(2, '0');

  // Animate text swap
  const textEl = document.getElementById('q-text');
  textEl.style.opacity   = '0';
  textEl.style.transform = 'translateY(10px)';
  setTimeout(() => {
    textEl.textContent   = q[idx];
    textEl.style.transition = 'opacity .3s, transform .3s';
    textEl.style.opacity   = '1';
    textEl.style.transform = 'translateY(0)';
  }, 140);

  // Dots
  document.getElementById('q-dots').innerHTML = q.map((_, i) => {
    let cls = '';
    const ans = S.answers[q[i]];
    if (ans === true)  cls = 'yes';
    else if (ans === false) cls = 'no';
    else if (i === idx) cls = 'current';
    return `<div class="q-dot ${cls}"></div>`;
  }).join('');
}

async function answerQuestion(answer) {
  S.answers[S.questions[S.qIndex]] = answer;

  if (S.qIndex < S.questions.length - 1) {
    S.qIndex++;
    renderQuestion();
  } else {
    await submitAnswers();
  }
}

async function submitAnswers() {
  try {
    await POST(`/api/session/${S.sessionId}/answers`, {
      session_id: S.sessionId,
      jawaban:    S.answers
    });
    goToScreen('recording');
    // Start mic for recording
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true }).catch(e => null);
    if (!stream) {
      toast('⚠️ Mikrofon tidak terdeteksi atau diblokir', 'warn');
    } else {
      S.camStream = stream; // reuse variable name for cleanup
    }
    // Show skip button after 3s so user can see options
    setTimeout(() => {
      document.getElementById('btn-skip-rec').style.display = 'block';
    }, 3000);
  } catch (e) {
    toast('❌ Gagal simpan jawaban: ' + e.message, 'err');
  }
}

// ════════════════════════════════════════════════════
// STEP 5 — Audio Recording
// ════════════════════════════════════════════════════
async function startRecording(btn) {
  btn.disabled = true;
  btn.innerHTML = '⏳ Memulai rekaman...';

  if (!S.camStream) {
    toast('❌ Mikrofon tidak terdeteksi. Silakan lewati rekaman.', 'err');
    btn.disabled = false;
    btn.innerHTML = '🎙️ Mulai Rekam';
    return;
  }

  // Show server-is-recording overlay / animation
  document.getElementById('rec-badge').style.display          = 'none';
  document.getElementById('rec-server-overlay').style.display = 'flex';

  try {
    S.audioChunks = [];
    S.mediaRecorder = new MediaRecorder(S.camStream);
    S.mediaRecorder.ondataavailable = e => {
      if (e.data.size > 0) S.audioChunks.push(e.data);
    };
    S.mediaRecorder.onstop = async () => {
      const audioBlob = new Blob(S.audioChunks, { type: 'audio/webm' });
      await uploadAudio(audioBlob);
    };

    S.mediaRecorder.start();

    document.getElementById('rec-badge').style.display = 'flex';
    document.getElementById('timer-label').textContent  = 'Sedang merekam — ceritakan keluhan Anda';
    
    btn.style.display = 'none';
    const stopBtn = document.getElementById('btn-stop-rec');
    if (stopBtn) {
      stopBtn.style.display = 'block';
      stopBtn.disabled = false;
      stopBtn.innerHTML = '⏹ Stop Rekaman';
    }

    S.recStartTime = Date.now();
    S.recDuration  = 30;

    // Countdown UI
    clearInterval(S.recInterval);
    S.recInterval = setInterval(tickRecording, 1000);

    // Hard failsafe: proceed after duration
    S.recFailsafe = setTimeout(() => {
      if (S.mediaRecorder && S.mediaRecorder.state === 'recording') {
        stopRecording();
      }
    }, S.recDuration * 1000);

  } catch (e) {
    toast('❌ Gagal mulai rekaman: ' + e.message, 'err');
    btn.disabled = false;
    btn.style.display = 'block';
    btn.innerHTML = '🎙️ Mulai Rekam';
    document.getElementById('rec-server-overlay').style.display = 'none';
  }
}

function tickRecording() {
  const elapsed   = Math.floor((Date.now() - S.recStartTime) / 1000);
  const remaining = Math.max(0, S.recDuration - elapsed);
  const mm = String(Math.floor(remaining / 60)).padStart(2, '0');
  const ss = String(remaining % 60).padStart(2, '0');
  document.getElementById('timer-display').textContent = `${mm}:${ss}`;
  const pct = Math.min((elapsed / S.recDuration) * 100, 100);
  document.getElementById('progress-fill').style.width = `${pct}%`;
  if (remaining <= 0) {
    clearInterval(S.recInterval);
    document.getElementById('timer-label').textContent = '✅ Rekaman selesai!';
  }
}

async function uploadAudio(blob) {
  toast('Mengunggah rekaman...', 'info');
  try {
    const formData = new FormData();
    formData.append('audio', blob, 'keluhan.webm');

    const r = await fetch(`/api/session/${S.sessionId}/record/upload`, {
      method: 'POST',
      body: formData
    });
    if (!r.ok) throw new Error(await r.text());
    
    toast('✅ Rekaman berhasil diunggah', 'ok');
    runAnalyze();
  } catch (e) {
    toast('❌ Gagal mengunggah rekaman: ' + e.message, 'err');
    document.getElementById('btn-skip-rec').click(); // skip on fail
  }
}

async function stopRecording() {
  const stopBtn = document.getElementById('btn-stop-rec');
  if(stopBtn) {
    stopBtn.disabled = true;
    stopBtn.innerHTML = '⏳ Menghentikan...';
  }
  clearInterval(S.recInterval);
  if (S.recFailsafe) clearTimeout(S.recFailsafe);

  if (S.mediaRecorder && S.mediaRecorder.state !== 'inactive') {
    S.mediaRecorder.stop();
  }
}

function skipRecording() {
  clearInterval(S.recInterval);
  if (S.recFailsafe) clearTimeout(S.recFailsafe);
  camStop();
  toast('Melewati rekaman — lanjut analisis', 'info');
  runAnalyze();
}

// ════════════════════════════════════════════════════
// STEP 6 — Analyze
// ════════════════════════════════════════════════════
async function runAnalyze() {
  camStop();
  goToScreen('analyzing');

  // Animate analysis steps
  for (let i = 0; i < 3; i++) {
    const el = document.getElementById(`ana-${i}`);
    el.classList.add('on');
    await sleep(750);
    el.classList.remove('on');
    el.classList.add('done');
  }

  try {
    const res = await POST(`/api/session/${S.sessionId}/analyze`);
    S.result = res;
    showResult(res);
  } catch (e) {
    toast('❌ Gagal analisis AI: ' + e.message, 'err');
    // Go back to recording step
    goToScreen('recording');
  }
}

// ════════════════════════════════════════════════════
// STEP 7 — Result
// ════════════════════════════════════════════════════
function showResult(r) {
  goToScreen('result');

  const badge  = document.getElementById('result-badge');
  const icon   = document.getElementById('rb-icon');
  const title  = document.getElementById('rb-title');
  const sub    = document.getElementById('rb-sub');
  const lvl    = r.level;

  badge.className = 'result-badge';

  if (lvl === 1) {
    badge.classList.add('lvl1');
    icon.textContent  = '';
    title.textContent = 'KONDISI AMAN';
    sub.textContent   = 'Tidak ada tindakan darurat diperlukan';
    title.style.color = '#10b981';
  } else if (lvl === 2) {
    badge.classList.add('lvl2');
    icon.textContent  = '';
    title.textContent = 'PERLU PERHATIAN';
    sub.textContent   = 'Disarankan segera konsultasi ke dokter';
    title.style.color = '#f59e0b';
  } else {
    badge.classList.add('lvl3');
    icon.textContent  = '';
    title.textContent = 'KONDISI DARURAT';
    sub.textContent   = 'Segera hubungi tenaga medis!';
    title.style.color = '#ef4444';
  }

  // Vitals summary
  if (S.sensorData) {
    const sd = S.sensorData;
    document.getElementById('result-vitals').innerHTML = `
      <div class="rv-item">
        <span class="rv-value">${sd.heart_rate.toFixed(0)}</span>
        <span class="rv-label">BPM</span>
      </div>
      <div class="rv-item">
        <span class="rv-value">${sd.spo2.toFixed(0)}%</span>
        <span class="rv-label">SpO₂</span>
      </div>
      <div class="rv-item">
        <span class="rv-value">${sd.suhu.toFixed(1)}°</span>
        <span class="rv-label">Suhu °C</span>
      </div>
    `;
  }

  // AI saran
  document.getElementById('result-saran-text').textContent =
    r.saran || 'Tidak ada saran khusus dari AI.';

  // Telegram
  const tgEl = document.getElementById('result-telegram-notif');
  tgEl.style.display = r.telegram_sent ? 'block' : 'none';
}

// ── Restart ──────────────────────────────────────────
function restartApp() {
  clearInterval(S.recInterval);
  camStop();

  Object.assign(S, {
    selectedWarga: null, sessionId: null,
    sensorData: null, sensorClass: null,
    questions: [], qIndex: 0, answers: {}, result: null,
    recStartTime: null, mediaRecorder: null, audioChunks: []
  });

  // Removed form reset as registration is moved to telegram

  // Reset sensor cards
  ['val-hr','val-spo2','val-suhu'].forEach(id => {
    document.getElementById(id).textContent = '—';
  });
  ['vcard-hr','vcard-spo2','vcard-suhu'].forEach(id => {
    document.getElementById(id).classList.remove('ok','warn','crit');
  });
  ['badge-hr','badge-spo2','badge-suhu'].forEach(id => {
    document.getElementById(id).textContent = '—';
  });

  // Reset sensor button
  const sensBtn = document.getElementById('btn-read-sensor');
  sensBtn.innerHTML = '📡 Baca Sensor';
  sensBtn.disabled  = false;
  sensBtn.onclick   = function() { readSensor(this); };

  // Reset analyze steps
  [0,1,2].forEach(i => {
    const el = document.getElementById(`ana-${i}`);
    if (el) el.classList.remove('on','done');
  });

  // Reset recording
  document.getElementById('timer-display').textContent  = '01:00';
  document.getElementById('timer-label').textContent    = 'Siap merekam';
  document.getElementById('progress-fill').style.width  = '0%';
  document.getElementById('rec-badge').style.display          = 'none';
  document.getElementById('rec-server-overlay').style.display = 'none';
  document.getElementById('btn-skip-rec').style.display       = 'none';
  const recBtn = document.getElementById('btn-start-rec');
  recBtn.disabled  = false;
  recBtn.style.display = 'block';
  recBtn.innerHTML = '🎙️ Mulai Rekam';
  recBtn.onclick   = function() { startRecording(this); };

  goToScreen('welcome');
  setStepIndicator(null);
}

// ── Utilities ─────────────────────────────────────────
function sleep(ms) { return new Promise(res => setTimeout(res, ms)); }

// ── Init ──────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  document.getElementById('app-header').style.display = 'none';
  goToScreen('welcome');
});
