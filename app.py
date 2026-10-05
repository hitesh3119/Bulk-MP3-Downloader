import os
import sys
import subprocess

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure all dependencies are available on any new machine
def _ensure_dependencies():
    required_packages = [
        ("fastapi", "fastapi>=0.110.0"),
        ("uvicorn", "uvicorn>=0.28.0"),
        ("yt_dlp", "yt-dlp>=2024.08.01"),
        ("imageio_ffmpeg", "imageio-ffmpeg>=0.5.1"),
        ("pydantic", "pydantic>=2.0.0"),
    ]
    missing = []
    for module_name, pkg_name in required_packages:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(pkg_name)
    
    if missing:
        print("=====================================================")
        print("  [*] First-time setup: Installing required libraries...")
        for pkg in missing:
            print(f"      -> {pkg}")
        print("=====================================================")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
            print("[+] Dependencies successfully installed!\n")
        except Exception as e:
            print(f"[!] Warning: Auto-install failed: {e}")
            print("[!] Please run: pip install -r requirements.txt\n")

_ensure_dependencies()

import json
import uuid
import queue
import asyncio
import threading
import webbrowser
import concurrent.futures
from typing import List, Dict, Any, Optional
from pathlib import Path

import imageio_ffmpeg
import yt_dlp
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Bulk MP3 Downloader")

# Enable CORS so Netlify or any web interface can communicate with the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup default download path
DEFAULT_DOWNLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "downloads"))
os.makedirs(DEFAULT_DOWNLOAD_DIR, exist_ok=True)

# Static files path
STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "static"))
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/style.css")
async def get_root_css():
    return FileResponse(os.path.join(STATIC_DIR, "style.css"))

@app.get("/app.js")
async def get_root_js():
    return FileResponse(os.path.join(STATIC_DIR, "app.js"))

# In-memory store for jobs
JOBS: Dict[str, Dict[str, Any]] = {}
JOB_QUEUES: Dict[str, List[asyncio.Queue]] = {}
BROADCAST_LOCK = threading.Lock()

class DownloadRequest(BaseModel):
    songs: List[str]
    bitrate: str = "320"
    concurrency: int = 5
    add_prefix: bool = True
    folder: Optional[str] = None

class FolderRequest(BaseModel):
    folder: Optional[str] = None


def get_ffmpeg_path() -> str:
    """Finds or extracts ffmpeg executable path."""
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        if os.path.exists(ffmpeg_exe):
            return ffmpeg_exe
    except Exception:
        pass
    return "ffmpeg"


def broadcast_event(job_id: str, event_data: dict):
    """Thread-safe event broadcast to all active SSE queues for this job."""
    with BROADCAST_LOCK:
        if job_id in JOBS:
            JOBS[job_id]["events"].append(event_data)
            JOBS[job_id]["latest"] = event_data
        if job_id in JOB_QUEUES:
            for q in list(JOB_QUEUES[job_id]):
                try:
                    q.put_nowait(event_data)
                except Exception:
                    pass


def sanitize_song_input(raw_input: str) -> List[str]:
    """Splits and cleans list of songs from multi-line text."""
    lines = [line.strip() for line in raw_input.splitlines()]
    songs = []
    for line in lines:
        if not line:
            continue
        if "," in line and not line.startswith("http"):
            parts = [p.strip() for p in line.split(",") if p.strip()]
            songs.extend(parts)
        else:
            songs.append(line)
    return songs


def run_download_job(job_id: str, songs: List[str], bitrate: str, output_dir: str, concurrency: int = 5, add_prefix: bool = True):
    ffmpeg_exe = get_ffmpeg_path()
    total_songs = len(songs)
    
    # Calculate zero padding: 1-9 -> 2 digits (01..), 100-999 -> 3 digits (001..), etc.
    padding = max(2, len(str(total_songs)))

    broadcast_event(job_id, {
        "type": "job_start",
        "total": total_songs,
        "concurrency": concurrency,
        "folder": output_dir,
        "message": f"Starting bulk download of {total_songs} songs ({concurrency} parallel workers)..."
    })

    completed_lock = threading.Lock()
    stats = {"completed": 0, "failed": 0}

    def process_single_song(idx: int, song_query: str):
        if JOBS.get(job_id, {}).get("cancelled"):
            return

        is_url = song_query.lower().startswith("http://") or song_query.lower().startswith("https://")
        search_target = song_query if is_url else f"ytsearch1:{song_query}"

        # Number prefix: e.g., 001 - Title.mp3
        prefix_str = f"{str(idx).zfill(padding)} - " if add_prefix else ""
        out_template = os.path.join(output_dir, f"{prefix_str}%(title)s.%(ext)s")

        broadcast_event(job_id, {
            "type": "song_start",
            "index": idx,
            "total": total_songs,
            "query": song_query,
            "prefix": prefix_str,
            "status": "searching",
            "message": f"Searching for '{song_query}'..."
        })

        def progress_hook(d):
            if JOBS.get(job_id, {}).get("cancelled"):
                raise yt_dlp.utils.DownloadCancelled("Download cancelled by user")
            
            if d['status'] == 'downloading':
                p_str = d.get('_percent_str', '0%').replace('%', '').strip()
                try:
                    percent = float(p_str)
                except ValueError:
                    percent = 0.0
                speed = d.get('_speed_str', '')
                eta = d.get('_eta_str', '')

                broadcast_event(job_id, {
                    "type": "song_progress",
                    "index": idx,
                    "query": song_query,
                    "percent": percent,
                    "speed": speed,
                    "eta": eta,
                    "status": "downloading"
                })
            elif d['status'] == 'finished':
                broadcast_event(job_id, {
                    "type": "song_converting",
                    "index": idx,
                    "query": song_query,
                    "status": "converting",
                    "message": "Extracting & converting to MP3..."
                })

        ydl_opts = {
            'format': 'bestaudio/best',
            'ffmpeg_location': ffmpeg_exe,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': bitrate,
            }],
            'outtmpl': out_template,
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'progress_hooks': [progress_hook],
            'js_runtimes': {'node': {}},
            'windowsfilenames': True,
            'retries': 5,
            'fragment_retries': 5,
            'socket_timeout': 30,
            'nocheckcertificate': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'web', 'mweb'],
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
            }
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_target, download=True)
                if 'entries' in info and info['entries']:
                    track_info = info['entries'][0]
                else:
                    track_info = info

                track_title = track_info.get('title', song_query)
                uploader = track_info.get('uploader', 'Unknown Artist')
                duration = track_info.get('duration_string', '')
                thumbnail = track_info.get('thumbnail', '')
                expected_filename = f"{prefix_str}{track_title}.mp3"

                with completed_lock:
                    stats["completed"] += 1

                broadcast_event(job_id, {
                    "type": "song_completed",
                    "index": idx,
                    "query": song_query,
                    "title": track_title,
                    "artist": uploader,
                    "duration": duration,
                    "thumbnail": thumbnail,
                    "filename": expected_filename,
                    "status": "completed",
                    "message": f"Saved: {expected_filename}"
                })
        except yt_dlp.utils.DownloadCancelled:
            broadcast_event(job_id, {
                "type": "song_cancelled",
                "index": idx,
                "query": song_query,
                "status": "cancelled",
                "message": "Cancelled"
            })
        except Exception as e:
            with completed_lock:
                stats["failed"] += 1
            err_msg = str(e)
            if "No video formats found" in err_msg:
                clean_err = "No song match found"
            else:
                clean_err = err_msg.split("\n")[0][:120]
            broadcast_event(job_id, {
                "type": "song_error",
                "index": idx,
                "query": song_query,
                "status": "error",
                "error": clean_err,
                "message": f"Failed: {clean_err}"
            })

    # Parallel Execution with ThreadPoolExecutor
    workers = max(1, min(concurrency, 10))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(process_single_song, idx, song): idx
            for idx, song in enumerate(songs, start=1)
        }
        for future in concurrent.futures.as_completed(futures):
            if JOBS.get(job_id, {}).get("cancelled"):
                executor.shutdown(wait=False, cancel_futures=True)
                broadcast_event(job_id, {
                    "type": "job_cancelled",
                    "message": "Download task was cancelled by user."
                })
                return

    broadcast_event(job_id, {
        "type": "job_completed",
        "total": total_songs,
        "completed": stats["completed"],
        "failed": stats["failed"],
        "folder": output_dir,
        "message": f"All finished! {stats['completed']} downloaded, {stats['failed']} failed."
    })


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>Loading Bulk MP3 Downloader...</h1>")


@app.get("/api/config")
async def get_config():
    return {
        "default_folder": DEFAULT_DOWNLOAD_DIR,
        "ffmpeg": get_ffmpeg_path()
    }


@app.post("/api/open-folder")
async def open_folder(req: FolderRequest):
    folder = (req.folder or "").strip()
    if not folder or folder.startswith("http://") or folder.startswith("https://"):
        folder = DEFAULT_DOWNLOAD_DIR
    if not os.path.exists(folder):
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception:
            folder = DEFAULT_DOWNLOAD_DIR
    try:
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.run(["open", folder])
        else:
            subprocess.run(["xdg-open", folder])
        return {"status": "ok", "folder": folder}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/browse-folder")
async def browse_folder():
    """Opens a native Windows folder picker dialog."""
    if sys.platform != "win32":
        return {"folder": DEFAULT_DOWNLOAD_DIR}
    try:
        def _pick():
            cmd = [
                sys.executable,
                "-c",
                "import tkinter as tk, tkinter.filedialog as fd; root=tk.Tk(); root.withdraw(); root.wm_attributes('-topmost', 1); f=fd.askdirectory(title='Select Download Folder'); print(f)"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return res.stdout.strip()

        loop = asyncio.get_event_loop()
        selected = await loop.run_in_executor(None, _pick)
        if selected and os.path.exists(selected):
            return {"folder": os.path.normpath(selected)}
        return {"folder": None}
    except Exception as e:
        return {"folder": None, "error": str(e)}


@app.post("/api/download")
async def create_download_job(req: DownloadRequest, background_tasks: BackgroundTasks):
    valid_songs = [s.strip() for s in req.songs if s.strip()]
    if not valid_songs:
        raise HTTPException(status_code=400, detail="Song list cannot be empty")

    output_dir = req.folder.strip() if req.folder and req.folder.strip() else DEFAULT_DOWNLOAD_DIR
    
    if output_dir.startswith("http://") or output_dir.startswith("https://"):
        raise HTTPException(
            status_code=400,
            detail="Web links cannot be used as folder paths. Please specify a local directory on your machine."
        )

    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid folder path: {str(e)}")

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "id": job_id,
        "songs": valid_songs,
        "bitrate": req.bitrate,
        "concurrency": req.concurrency,
        "add_prefix": req.add_prefix,
        "folder": output_dir,
        "events": [],
        "latest": {},
        "cancelled": False
    }
    JOB_QUEUES[job_id] = []

    # Run in separate worker thread
    worker_thread = threading.Thread(
        target=run_download_job,
        args=(job_id, valid_songs, req.bitrate, output_dir, req.concurrency, req.add_prefix),
        daemon=True
    )
    worker_thread.start()

    return {"job_id": job_id, "total": len(valid_songs), "folder": output_dir}


@app.get("/api/progress/{job_id}")
async def job_progress(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        q = asyncio.Queue()
        JOB_QUEUES[job_id].append(q)

        # First replay existing events
        for past_event in JOBS[job_id]["events"]:
            yield f"data: {json.dumps(past_event)}\n\n"

        try:
            while True:
                event = await q.get()
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("job_completed", "job_cancelled"):
                    break
        except asyncio.CancelledError:
            pass
        finally:
            if job_id in JOB_QUEUES and q in JOB_QUEUES[job_id]:
                JOB_QUEUES[job_id].remove(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/api/cancel/{job_id}")
async def cancel_job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    JOBS[job_id]["cancelled"] = True
    return {"status": "cancelling", "job_id": job_id}


# WSGI adapter for standard WSGI servers (if needed)
try:
    from a2wsgi import ASGIMiddleware
    wsgi_app = ASGIMiddleware(app)
except Exception:
    wsgi_app = None


if __name__ == "__main__":
    import uvicorn
    import webbrowser

    port = int(os.environ.get("PORT", 5000))
    is_cloud = "RENDER" in os.environ or "PORT" in os.environ or "DYNO" in os.environ
    host = "0.0.0.0" if is_cloud else "127.0.0.1"

    if not is_cloud:
        def open_browser():
            try:
                webbrowser.open(f"http://127.0.0.1:{port}")
            except Exception:
                pass
        threading.Timer(1.2, open_browser).start()

    print("=====================================================")
    print("  [+] Bulk MP3 Downloader Server Starting...")
    print(f"  [*] Host: {host} | Port: {port}")
    print(f"  [*] Web UI: http://127.0.0.1:{port}")
    print(f"  [*] Default Output Folder: {DEFAULT_DOWNLOAD_DIR}")
    print("=====================================================")
    uvicorn.run(app, host=host, port=port, log_level="warning")

