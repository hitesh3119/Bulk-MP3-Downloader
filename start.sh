#!/usr/bin/env bash
set -e

PORT="${PORT:-5000}"
HOST="0.0.0.0"

echo "========================================================"
echo "        🎵 BULK MP3 DOWNLOADER STUDIO 🎵"
echo "========================================================"

# Auto-check dependencies if running locally
if [ -z "$RENDER" ] && [ -z "$DYNO" ]; then
    PYTHON_CMD=""
    if command -v python3 &>/dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &>/dev/null; then
        PYTHON_CMD="python"
    fi

    if [ -n "$PYTHON_CMD" ]; then
        if ! $PYTHON_CMD -c "import fastapi, uvicorn, yt_dlp, imageio_ffmpeg, pydantic" &>/dev/null; then
            echo "[*] Installing missing dependencies from requirements.txt..."
            $PYTHON_CMD -m pip install -r requirements.txt
        fi
        echo "[*] Launching Bulk MP3 Downloader on port $PORT..."
        exec $PYTHON_CMD app.py
    fi
fi

echo "[*] Starting Bulk MP3 Downloader on port $PORT..."
exec uvicorn app:app --host "$HOST" --port "$PORT"
