#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Single-file Flask fullstack Music app
Features:
- Single file app (SQLite)
- Register / Login (password hashing)
- Upload audio files (mp3/ogg/wav/m4a)
- Browse songs, search
- User's songs management (delete)
- Playlists: create + add/remove songs
- Beautiful UI using Tailwind + custom CSS/JS audio player
- Download songs
Notes:
- uploads/ created automatically
- DB file: musicapp.db
- For production: set a secure MUSICAPP_SECRET env var
"""
import os
# from pyngrok import ngrok
import sqlite3
from datetime import datetime
from functools import wraps
from flask import (
    Flask, g, render_template_string, request, redirect, url_for,
    session, send_from_directory, flash, abort, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ---------- Config ----------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(APP_DIR, "uploads")
DB_PATH = os.path.join(APP_DIR, "musicapp.db")
ALLOWED_EXT = {"mp3", "ogg", "wav", "m4a"}
MAX_UPLOAD = 80 * 1024 * 1024  # 80 MB
SECRET_KEY = os.environ.get("MUSICAPP_SECRET", "dev-secret-change-me")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config.update(
    UPLOAD_FOLDER=UPLOAD_FOLDER,
    DATABASE=DB_PATH,
    MAX_CONTENT_LENGTH=MAX_UPLOAD,
)
app.secret_key = SECRET_KEY

# --------- DB helpers ----------
def get_db():
    db = getattr(g, "_db", None)
    if db is None:
        db = g._db = sqlite3.connect(app.config["DATABASE"])
        db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    cur = db.cursor()
    # users, songs, playlists, playlist_songs, likes (simple)
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS songs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        filename TEXT NOT NULL,
        uploaded_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS playlists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS playlist_songs (
        playlist_id INTEGER NOT NULL,
        song_id INTEGER NOT NULL,
        PRIMARY KEY (playlist_id, song_id),
        FOREIGN KEY(playlist_id) REFERENCES playlists(id),
        FOREIGN KEY(song_id) REFERENCES songs(id)
    );
    """)
    db.commit()

@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, "_db", None)
    if db is not None:
        db.close()

# --------- Auth helpers ----------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Bạn cần đăng nhập để tiếp tục.", "warning")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def current_user():
    if "user_id" not in session:
        return None
    cur = get_db().execute("SELECT id, username, email FROM users WHERE id = ?", (session["user_id"],))
    return cur.fetchone()

# --------- Base template (Tailwind + custom CSS/JS) ----------
BASE_TEMPLATE = """
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>MusicBox — Ứng dụng nghe nhạc</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    /* custom styling for player */
    .player-bar {
      position: fixed;
      left: 0; right: 0; bottom: 0;
      background: linear-gradient(90deg, rgba(99,102,241,0.06), rgba(99,102,241,0.02));
      border-top: 1px solid rgba(15,23,42,0.04);
      backdrop-filter: blur(6px);
      padding: 10px 16px;
    }
    .progress {
      -webkit-appearance: none;
      appearance: none;
      height: 6px;
      border-radius: 6px;
      outline: none;
      width: 100%;
    }
    .progress::-webkit-slider-runnable-track { height:6px; }
    .progress::-webkit-slider-thumb { -webkit-appearance:none; width: 14px; height:14px; border-radius:14px; background:white; border: 2px solid #6366f1; margin-top:-4px; }
  </style>
</head>
<body class="bg-slate-50">
  <nav class="bg-white/90 backdrop-blur sticky top-0 z-30 shadow-sm">
    <div class="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between">
      <a href="{{ url_for('index') }}" class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-full bg-indigo-600 flex items-center justify-center text-white font-bold">M</div>
        <div>
          <div class="font-semibold">MusicBox</div>
          <div class="text-xs text-slate-500">Nghe • Tải lên • Chia sẻ</div>
        </div>
      </a>
      <div class="flex items-center gap-3">
        <form action="{{ url_for('index') }}" method="get" class="hidden md:flex items-center gap-2">
          <input name="q" value="{{ request.args.get('q','') }}" placeholder="Tìm bài, tiêu đề..." class="border rounded px-3 py-1 text-sm" />
          <button class="px-3 py-1 bg-indigo-600 text-white rounded text-sm">Tìm</button>
        </form>
        {% if user %}
          <a href="{{ url_for('my_songs') }}" class="text-sm">Bài của tôi</a>
          <a href="{{ url_for('playlists') }}" class="text-sm">Playlist</a>
          <a href="{{ url_for('upload') }}" class="px-3 py-1 rounded-md bg-indigo-600 text-white text-sm">Tải lên</a>
          <div class="text-sm text-slate-600">Xin chào, <strong>{{ user['username'] }}</strong></div>
          <a href="{{ url_for('logout') }}" class="px-3 py-1 rounded-md border text-sm">Đăng xuất</a>
        {% else %}
          <a href="{{ url_for('login') }}" class="px-3 py-1 rounded-md text-sm">Đăng nhập</a>
          <a href="{{ url_for('register') }}" class="px-3 py-1 rounded-md bg-indigo-600 text-white text-sm">Đăng ký</a>
        {% endif %}
      </div>
    </div>
  </nav>

  <main class="max-w-5xl mx-auto p-6 pb-36">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        <div class="space-y-2 mb-4">
          {% for category, msg in messages %}
            <div class="px-4 py-2 rounded text-sm {% if category=='error' %}bg-red-50 text-red-700{% elif category=='success' %}bg-green-50 text-green-700{% else %}bg-yellow-50 text-yellow-700{% endif %}">{{ msg }}</div>
          {% endfor %}
        </div>
      {% endif %}
    {% endwith %}
    {{ content|safe }}
  </main>

  <!-- Player bar -->
  <div class="player-bar">
    <div class="max-w-5xl mx-auto flex items-center gap-4">
      <div class="w-1/3 md:w-1/4">
        <div id="player-track-title" class="text-sm font-medium"></div>
        <div id="player-track-sub" class="text-xs text-slate-500"></div>
      </div>
      <div class="flex-1">
        <div class="flex items-center gap-3">
          <button id="prev-btn" class="p-2 rounded hover:bg-slate-100">⏮️</button>
          <button id="play-btn" class="p-2 rounded bg-indigo-600 text-white">▶️</button>
          <button id="next-btn" class="p-2 rounded hover:bg-slate-100">⏭️</button>
          <div class="flex-1">
            <input id="progress" type="range" class="progress" min="0" max="100" value="0" />
            <div class="flex justify-between text-xs text-slate-500 mt-1">
              <span id="cur-time">0:00</span>
              <span id="dur-time">0:00</span>
            </div>
          </div>
          <input id="volume" type="range" min="0" max="1" step="0.01" value="1" class="w-24" />
        </div>
      </div>
      <div class="w-1/6 text-right">
        <a id="download-btn" class="px-3 py-1 rounded border text-sm" href="#">Tải xuống</a>
      </div>
    </div>
  </div>

  <!-- Hidden audio element -->
  <audio id="audio" preload="auto"></audio>

  <script>
    // Simple playlist player JS
    const audio = document.getElementById('audio');
    const playBtn = document.getElementById('play-btn');
    const prevBtn = document.getElementById('prev-btn');
    const nextBtn = document.getElementById('next-btn');
    const progress = document.getElementById('progress');
    const curTime = document.getElementById('cur-time');
    const durTime = document.getElementById('dur-time');
    const volume = document.getElementById('volume');
    const titleEl = document.getElementById('player-track-title');
    const subEl = document.getElementById('player-track-sub');
    const downloadBtn = document.getElementById('download-btn');

    let playlist = []; // array of {id, title, url, uploader}
    let current = -1;
    let playing = false;

    // load playlist from DOM dataset if present
    try {
      const domList = document.getElementById('song-list-json');
      if (domList) {
        playlist = JSON.parse(domList.textContent || "[]");
      }
    } catch(e) { console.error(e); }

    function loadTrack(index) {
      if (!playlist || playlist.length === 0) {
        audio.src = "";
        titleEl.textContent = "";
        subEl.textContent = "";
        downloadBtn.href = "#";
        return;
      }
      if (index < 0) index = 0;
      if (index >= playlist.length) index = playlist.length - 1;
      current = index;
      const t = playlist[current];
      audio.src = t.url;
      titleEl.textContent = t.title;
      subEl.textContent = "Tải lên bởi " + (t.uploader || "Unknown");
      downloadBtn.href = t.url + "?download=1";
      progress.value = 0;
      curTime.textContent = '0:00';
      durTime.textContent = '0:00';
    }

    function playPause() {
      if (!audio.src) return;
      if (audio.paused) {
        audio.play(); playing = true; playBtn.textContent = "⏸️";
      } else {
        audio.pause(); playing = false; playBtn.textContent = "▶️";
      }
    }
    playBtn.addEventListener('click', playPause);
    prevBtn.addEventListener('click', () => { if (playlist.length) loadTrack((current-1+playlist.length)%playlist.length); if (!audio.paused) audio.play(); });
    nextBtn.addEventListener('click', () => { if (playlist.length) loadTrack((current+1)%playlist.length); if (!audio.paused) audio.play(); });

    audio.addEventListener('loadedmetadata', () => {
      durTime.textContent = formatTime(audio.duration);
      progress.max = Math.floor(audio.duration);
    });
    audio.addEventListener('timeupdate', () => {
      progress.value = Math.floor(audio.currentTime);
      curTime.textContent = formatTime(audio.currentTime);
    });
    progress.addEventListener('input', () => {
      audio.currentTime = progress.value;
    });
    volume.addEventListener('input', () => {
      audio.volume = volume.value;
    });
    audio.addEventListener('ended', () => {
      nextBtn.click();
    });

    function formatTime(s) {
      if (!s || isNaN(s)) return '0:00';
      const m = Math.floor(s/60);
      const sec = Math.floor(s%60).toString().padStart(2,'0');
      return `${m}:${sec}`;
    }

    // expose quick play from song list
    window.playSong = function(songId) {
      const idx = playlist.findIndex(x => x.id == songId);
      if (idx >= 0) {
        loadTrack(idx);
        audio.play();
        playBtn.textContent = "⏸️";
      }
    };

    // initialize with first song if exists
    if (playlist.length) loadTrack(0);

  </script>
</body>
</html>
"""

# -------- ROUTES --------
@app.route("/")
def index():
    db = get_db()
    q = request.args.get("q", "").strip()
    if q:
        cur = db.execute(
            "SELECT songs.id, songs.title, songs.filename, songs.uploaded_at, users.username FROM songs JOIN users ON users.id = songs.user_id WHERE songs.title LIKE ? ORDER BY songs.id DESC",
            (f"%{q}%",)
        )
    else:
        cur = db.execute(
            "SELECT songs.id, songs.title, songs.filename, songs.uploaded_at, users.username FROM songs JOIN users ON users.id = songs.user_id ORDER BY songs.id DESC LIMIT 200"
        )
    songs = cur.fetchall()
    # build playlist JSON for JS (top 50)
    pl = []
    for s in songs[:50]:
        pl.append({
            "id": s["id"],
            "title": s["title"],
            "url": url_for("serve_file", filename=s["filename"]),
            "uploader": s["username"],
        })
    content = render_template_string("""
      <div class="flex items-center justify-between mb-6">
        <div>
          <h1 class="text-2xl font-bold">Kho nhạc</h1>
          <div class="text-sm text-slate-500">Tổng {{ songs|length }} bài</div>
        </div>
      </div>

      {% if songs|length == 0 %}
        <div class="text-center p-12 text-slate-500">Chưa có bài hát nào. Hãy <a href="{{ url_for('upload') }}" class="text-indigo-600 underline">tải lên</a> ngay!</div>
      {% else %}
        <div id="song-list" class="grid gap-4">
          {% for s in songs %}
            <div class="bg-white p-4 rounded-2xl shadow flex items-center justify-between gap-4">
              <div>
                <div class="font-semibold">{{ s['title'] }}</div>
                <div class="text-xs text-slate-500">Tải lên bởi {{ s['username'] }} • {{ s['uploaded_at'] }}</div>
                <div class="mt-2 flex items-center gap-2">
                  <button onclick="playSong({{ s['id'] }})" class="px-3 py-1 rounded border text-sm">▶️ Phát</button>
                  <a href="{{ url_for('serve_file', filename=s['filename']) }}?download=1" class="px-3 py-1 rounded border text-sm">⬇️ Tải</a>
                  {% if user and user['username']==s['username'] %}
                    <a href="{{ url_for('delete_song', song_id=s['id']) }}" onclick="return confirm('Xác nhận xóa?')" class="px-3 py-1 rounded border text-sm text-red-600">🗑️ Xóa</a>
                  {% endif %}
                </div>
              </div>
            </div>
          {% endfor %}
        </div>
      {% endif %}

      <script type="application/json" id="song-list-json">{{ pl | tojson }}</script>
    """, songs=songs, pl=pl, user=current_user())
    return render_template_string(BASE_TEMPLATE, content=content, user=current_user())

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        if not username or not email or not password:
            flash("Điền đầy đủ thông tin.", "error")
            return redirect(url_for("register"))
        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (username, email, generate_password_hash(password), datetime.utcnow().isoformat())
            )
            db.commit()
            flash("Đăng ký thành công! Hãy đăng nhập.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Tên đăng nhập hoặc email đã tồn tại.", "error")
            return redirect(url_for("register"))
    content = """
      <div class="max-w-md mx-auto bg-white p-6 rounded-2xl shadow">
        <h2 class="text-xl font-semibold mb-4">Tạo tài khoản</h2>
        <form method="post" class="space-y-3">
          <input name="username" placeholder="Tên đăng nhập" class="w-full border rounded px-3 py-2" required />
          <input name="email" type="email" placeholder="Email" class="w-full border rounded px-3 py-2" required />
          <input name="password" type="password" placeholder="Mật khẩu" class="w-full border rounded px-3 py-2" required />
          <button class="w-full py-2 bg-indigo-600 text-white rounded">Đăng ký</button>
        </form>
        <div class="text-sm text-slate-500 mt-3">Đã có tài khoản? <a href="{{ url_for('login') }}" class="text-indigo-600 underline">Đăng nhập</a></div>
      </div>
    """
    return render_template_string(BASE_TEMPLATE, content=content, user=current_user())

@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.args.get("next") or url_for("index")
    if request.method == "POST":
        ident = request.form.get("ident","").strip()
        password = request.form.get("password","")
        db = get_db()
        cur = db.execute("SELECT id, password_hash FROM users WHERE username = ? OR email = ? LIMIT 1", (ident, ident))
        u = cur.fetchone()
        if u and check_password_hash(u["password_hash"], password):
            session["user_id"] = u["id"]
            flash("Đăng nhập thành công.", "success")
            return redirect(next_url)
        else:
            flash("Tên đăng nhập/email hoặc mật khẩu không đúng.", "error")
            return redirect(url_for("login"))
    content = """
      <div class="max-w-md mx-auto bg-white p-6 rounded-2xl shadow">
        <h2 class="text-xl font-semibold mb-4">Đăng nhập</h2>
        <form method="post" class="space-y-3">
          <input name="ident" placeholder="Tên đăng nhập hoặc Email" class="w-full border rounded px-3 py-2" required />
          <input name="password" type="password" placeholder="Mật khẩu" class="w-full border rounded px-3 py-2" required />
          <button class="w-full py-2 bg-indigo-600 text-white rounded">Đăng nhập</button>
        </form>
        <div class="text-sm text-slate-500 mt-3">Chưa có tài khoản? <a href="{{ url_for('register') }}" class="text-indigo-600 underline">Đăng ký</a></div>
      </div>
    """
    return render_template_string(BASE_TEMPLATE, content=content, user=current_user())

@app.route("/logout")
def logout():
    session.clear()
    flash("Bạn đã đăng xuất.", "success")
    return redirect(url_for("index"))

@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        title = request.form.get("title","").strip()
        file = request.files.get("file")
        if not file or file.filename == "":
            flash("Chưa chọn file.", "error")
            return redirect(url_for("upload"))
        if not allowed_file(file.filename):
            flash("Định dạng không hỗ trợ. Hãy dùng mp3/ogg/wav/m4a.", "error")
            return redirect(url_for("upload"))
        filename = secure_filename(f"{int(datetime.utcnow().timestamp())}_{file.filename}")
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(save_path)
        if not title:
            title = os.path.splitext(file.filename)[0]
        db = get_db()
        db.execute("INSERT INTO songs (user_id, title, filename, uploaded_at) VALUES (?, ?, ?, ?)",
                   (session["user_id"], title, filename, datetime.utcnow().isoformat()))
        db.commit()
        flash("Tải lên thành công!", "success")
        return redirect(url_for("index"))
    content = """
      <div class="max-w-lg mx-auto bg-white p-6 rounded-2xl shadow">
        <h2 class="text-xl font-semibold mb-4">Tải lên bài hát</h2>
        <form method="post" enctype="multipart/form-data" class="space-y-3">
          <input name="title" placeholder="Tiêu đề (tùy chọn)" class="w-full border rounded px-3 py-2" />
          <input type="file" name="file" accept="audio/*" class="w-full" required />
          <button class="w-full py-2 bg-indigo-600 text-white rounded">Tải lên</button>
        </form>
        <div class="text-xs text-slate-400 mt-3">Hỗ trợ: mp3, ogg, wav, m4a. Kích thước tối đa: {{ max_upload_mb }} MB.</div>
      </div>
    """
    return render_template_string(BASE_TEMPLATE, content=content, user=current_user(), max_upload_mb=app.config["MAX_CONTENT_LENGTH"]//(1024*1024))

@app.route("/uploads/<path:filename>")
def serve_file(filename):
    # secure serving
    safe = secure_filename(filename)
    if safe != filename:
        abort(404)
    # if ?download=1 then set as attachment
    if request.args.get("download"):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=True)
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.route("/my_songs")
@login_required
def my_songs():
    db = get_db()
    cur = db.execute("SELECT id, title, filename, uploaded_at FROM songs WHERE user_id = ? ORDER BY id DESC", (session["user_id"],))
    my = cur.fetchall()
    content = render_template_string("""
      <div class="max-w-3xl mx-auto">
        <h2 class="text-xl font-semibold mb-4">Bài của tôi</h2>
        {% if my|length == 0 %}
          <div class="text-slate-500">Bạn chưa tải lên bài nào.</div>
        {% else %}
          <div class="space-y-3">
            {% for s in my %}
              <div class="bg-white p-4 rounded shadow flex items-center justify-between">
                <div>
                  <div class="font-semibold">{{ s['title'] }}</div>
                  <div class="text-xs text-slate-500">Tải lên: {{ s['uploaded_at'] }}</div>
                </div>
                <div class="flex items-center gap-2">
                  <button onclick="playSong({{ s['id'] }})" class="px-3 py-1 rounded border text-sm">▶️ Phát</button>
                  <a href="{{ url_for('serve_file', filename=s['filename']) }}?download=1" class="px-3 py-1 rounded border text-sm">⬇️ Tải</a>
                  <a href="{{ url_for('delete_song', song_id=s['id']) }}" onclick="return confirm('Xác nhận xóa?')" class="px-3 py-1 rounded border text-sm text-red-600">🗑️ Xóa</a>
                </div>
              </div>
            {% endfor %}
          </div>
        {% endif %}
      </div>
    """, my=my, user=current_user())
    # provide playlist context so playSong works
    pl = []
    for s in my:
        pl.append({"id": s["id"], "title": s["title"], "url": url_for("serve_file", filename=s["filename"]), "uploader": current_user()["username"]})
    return render_template_string(BASE_TEMPLATE + "<script type='application/json' id='song-list-json'>{{ pl|tojson }}</script>", content=content, user=current_user(), pl=pl)

@app.route("/delete_song/<int:song_id>")
@login_required
def delete_song(song_id):
    db = get_db()
    cur = db.execute("SELECT user_id, filename FROM songs WHERE id = ? LIMIT 1", (song_id,))
    row = cur.fetchone()
    if not row:
        flash("Bài hát không tồn tại.", "error")
        return redirect(url_for("index"))
    if row["user_id"] != session["user_id"]:
        flash("Bạn không có quyền xóa bài hát này.", "error")
        return redirect(url_for("index"))
    # delete file
    try:
        path = os.path.join(app.config["UPLOAD_FOLDER"], row["filename"])
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        app.logger.warning("Error deleting file: %s", e)
    db.execute("DELETE FROM songs WHERE id = ?", (song_id,))
    db.commit()
    flash("Xóa thành công.", "success")
    return redirect(url_for("my_songs"))

# Playlists (simple CRUD)
@app.route("/playlists")
@login_required
def playlists():
    db = get_db()
    cur = db.execute("SELECT id, name, created_at FROM playlists WHERE user_id = ? ORDER BY id DESC", (session["user_id"],))
    pls = cur.fetchall()
    content = render_template_string("""
      <div class="max-w-3xl mx-auto">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-xl font-semibold">Playlist của tôi</h2>
          <a href="{{ url_for('create_playlist') }}" class="px-3 py-1 bg-indigo-600 text-white rounded">Tạo Playlist</a>
        </div>
        {% if pls|length == 0 %}
          <div class="text-slate-500">Bạn chưa có playlist nào.</div>
        {% else %}
          <div class="space-y-3">
            {% for p in pls %}
              <div class="bg-white p-4 rounded shadow flex items-center justify-between">
                <div>
                  <div class="font-semibold">{{ p['name'] }}</div>
                  <div class="text-xs text-slate-500">Tạo: {{ p['created_at'] }}</div>
                </div>
                <div class="flex items-center gap-2">
                  <a href="{{ url_for('view_playlist', playlist_id=p['id']) }}" class="px-3 py-1 rounded border text-sm">Xem</a>
                  <a href="{{ url_for('delete_playlist', playlist_id=p['id']) }}" onclick="return confirm('Xóa playlist?')" class="px-3 py-1 rounded border text-sm text-red-600">Xóa</a>
                </div>
              </div>
            {% endfor %}
          </div>
        {% endif %}
      </div>
    """, pls=pls)
    return render_template_string(BASE_TEMPLATE, content=content, user=current_user())

@app.route("/playlists/create", methods=["GET", "POST"])
@login_required
def create_playlist():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        if not name:
            flash("Tên playlist không được để trống.", "error")
            return redirect(url_for("create_playlist"))
        db = get_db()
        db.execute("INSERT INTO playlists (user_id, name, created_at) VALUES (?, ?, ?)", (session["user_id"], name, datetime.utcnow().isoformat()))
        db.commit()
        flash("Tạo playlist thành công.", "success")
        return redirect(url_for("playlists"))
    content = """
      <div class="max-w-md mx-auto bg-white p-6 rounded-2xl shadow">
        <h2 class="text-xl font-semibold mb-4">Tạo playlist mới</h2>
        <form method="post" class="space-y-3">
          <input name="name" placeholder="Tên playlist" class="w-full border rounded px-3 py-2" required />
          <button class="w-full py-2 bg-indigo-600 text-white rounded">Tạo</button>
        </form>
      </div>
    """
    return render_template_string(BASE_TEMPLATE, content=content, user=current_user())

@app.route("/playlists/<int:playlist_id>")
@login_required
def view_playlist(playlist_id):
    db = get_db()
    p = db.execute("SELECT id, name, user_id FROM playlists WHERE id = ? LIMIT 1", (playlist_id,)).fetchone()
    if not p:
        flash("Playlist không tồn tại.", "error")
        return redirect(url_for("playlists"))
    # fetch songs in playlist
    cur = db.execute("""
      SELECT songs.id, songs.title, songs.filename, users.username
      FROM playlist_songs
      JOIN songs ON songs.id = playlist_songs.song_id
      JOIN users ON users.id = songs.user_id
      WHERE playlist_songs.playlist_id = ?
    """, (playlist_id,))
    items = cur.fetchall()
    # build full list of songs owned by user to allow adding
    all_songs = db.execute("SELECT id, title FROM songs ORDER BY id DESC").fetchall()
    content = render_template_string("""
      <div class="max-w-4xl mx-auto">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h2 class="text-xl font-semibold">{{ p['name'] }}</h2>
            <div class="text-xs text-slate-500">Bạn có {{ items|length }} bài trong playlist</div>
          </div>
          <div class="flex items-center gap-2">
            <form method="post" action="{{ url_for('add_to_playlist', playlist_id=p['id']) }}" class="flex items-center gap-2">
              <select name="song_id" class="border rounded px-2 py-1">
                {% for s in all_songs %}
                  <option value="{{ s['id'] }}">{{ s['title'] }}</option>
                {% endfor %}
              </select>
              <button class="px-3 py-1 bg-indigo-600 text-white rounded">Thêm</button>
            </form>
          </div>
        </div>

        {% if items|length == 0 %}
          <div class="text-slate-500">Chưa có bài nào trong playlist.</div>
        {% else %}
          <div class="space-y-3">
            {% for it in items %}
              <div class="bg-white p-4 rounded shadow flex items-center justify-between">
                <div>
                  <div class="font-semibold">{{ it['title'] }}</div>
                  <div class="text-xs text-slate-500">Tải lên bởi {{ it['username'] }}</div>
                </div>
                <div class="flex items-center gap-2">
                  <button onclick="playSong({{ it['id'] }})" class="px-3 py-1 rounded border text-sm">▶️ Phát</button>
                  <a href="{{ url_for('remove_from_playlist', playlist_id=p['id'], song_id=it['id']) }}" onclick="return confirm('Gỡ khỏi playlist?')" class="px-3 py-1 rounded border text-sm text-red-600">Gỡ</a>
                </div>
              </div>
            {% endfor %}
          </div>
        {% endif %}
      </div>
    """, p=p, items=items, all_songs=all_songs)
    # JS playlist for player
    pl = []
    for s in items:
        pl.append({"id": s["id"], "title": s["title"], "url": url_for("serve_file", filename=s["filename"]), "uploader": s["username"]})
    return render_template_string(BASE_TEMPLATE + "<script type='application/json' id='song-list-json'>{{ pl|tojson }}</script>", content=content, user=current_user(), pl=pl)

@app.route("/playlists/<int:playlist_id>/add", methods=["POST"])
@login_required
def add_to_playlist(playlist_id):
    song_id = int(request.form.get("song_id") or 0)
    db = get_db()
    try:
        db.execute("INSERT INTO playlist_songs (playlist_id, song_id) VALUES (?, ?)", (playlist_id, song_id))
        db.commit()
        flash("Thêm vào playlist thành công.", "success")
    except sqlite3.IntegrityError:
        flash("Bài đã có trong playlist.", "error")
    return redirect(url_for("view_playlist", playlist_id=playlist_id))

@app.route("/playlists/<int:playlist_id>/remove/<int:song_id>")
@login_required
def remove_from_playlist(playlist_id, song_id):
    db = get_db()
    db.execute("DELETE FROM playlist_songs WHERE playlist_id = ? AND song_id = ?", (playlist_id, song_id))
    db.commit()
    flash("Gỡ bài khỏi playlist.", "success")
    return redirect(url_for("view_playlist", playlist_id=playlist_id))

@app.route("/playlists/delete/<int:playlist_id>")
@login_required
def delete_playlist(playlist_id):
    db = get_db()
    db.execute("DELETE FROM playlist_songs WHERE playlist_id = ?", (playlist_id,))
    db.execute("DELETE FROM playlists WHERE id = ? AND user_id = ?", (playlist_id, session["user_id"]))
    db.commit()
    flash("Xóa playlist (nếu thuộc về bạn).", "success")
    return redirect(url_for("playlists"))

# ---------- Startup ----------



# if __name__ == "__main__":
#     # mở tunnel tới port 5000
#     public_url = ngrok.connect(5000)
#     print("Ngrok URL:", public_url)
#     app.run(port=5000)




if __name__ == "__main__":
    with app.app_context():
        init_db()
    print("Starting MusicBox (single-file) ...")
    print("Uploads folder:", app.config['UPLOAD_FOLDER'])
    app.run(debug=True, port=5000)
