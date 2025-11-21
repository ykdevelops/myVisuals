"""
Flask API server for AudioGiphy.

Provides REST endpoints and Server-Sent Events (SSE) for real-time log streaming
during video rendering.
"""

import json
import logging
import threading
import uuid
from collections import deque
from pathlib import Path
from typing import Dict, Optional

from flask import Flask, jsonify, request, Response, stream_with_context
from flask_cors import CORS

from audiogiphy.render_pipeline import render_video
from audiogiphy.config import DEFAULT_RESOLUTION

logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for Vue.js frontend

# In-memory job storage (simple dict-based)
jobs: Dict[str, Dict] = {}
job_logs: Dict[str, deque] = {}
job_lock = threading.Lock()


class LogCaptureHandler(logging.Handler):
    """Custom logging handler that captures logs to a deque for a job."""
    
    def __init__(self, job_id: str, max_logs: int = 1000):
        super().__init__()
        self.job_id = job_id
        self.max_logs = max_logs
        
    def emit(self, record):
        """Emit a log record to the job's log deque."""
        try:
            msg = self.format(record)
            with job_lock:
                if self.job_id not in job_logs:
                    job_logs[self.job_id] = deque(maxlen=self.max_logs)
                job_logs[self.job_id].append(msg)
        except Exception:
            self.handleError(record)


def run_render_job(job_id: str, params: dict):
    """Run render_video in a background thread and capture logs."""
    try:
        with job_lock:
            jobs[job_id]["status"] = "running"
        
        # Set up log capture
        log_handler = LogCaptureHandler(job_id)
        log_handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
        
        # Add handler to all relevant loggers
        loggers_to_capture = [
            logging.getLogger("audiogiphy.audio_analysis"),
            logging.getLogger("audiogiphy.visual_builder"),
            logging.getLogger("audiogiphy.render_pipeline"),
            logging.getLogger("ffmpeg"),
            logging.getLogger("audiogiphy.cli"),
        ]
        
        for lg in loggers_to_capture:
            lg.addHandler(log_handler)
            lg.setLevel(logging.INFO)
        
        try:
            # Run the render
            render_video(
                audio_path=params["audio"],
                video_folder=params["gif_folder"],
                duration_seconds=params["duration_seconds"],
                output_path=params["output"],
                resolution=(params["width"], params["height"]),
                seed=params.get("seed"),
            )
            
            with job_lock:
                jobs[job_id]["status"] = "complete"
                jobs[job_id]["message"] = "Render completed successfully"
                
        except Exception as e:
            error_msg = str(e)
            with job_lock:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["message"] = error_msg
                if job_id in job_logs:
                    job_logs[job_id].append(f"[error] {error_msg}")
        finally:
            # Remove log handlers
            for lg in loggers_to_capture:
                lg.removeHandler(log_handler)
                
    except Exception as e:
        with job_lock:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["message"] = f"Job setup failed: {str(e)}"


@app.route("/api/render", methods=["POST"])
def start_render():
    """Start a new render job."""
    try:
        data = request.get_json()
        
        # Validate required fields
        required = ["audio", "gif_folder", "duration_seconds", "output"]
        for field in required:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Validate paths
        audio_path = Path(data["audio"])
        if not audio_path.exists():
            return jsonify({"error": f"Audio file not found: {data['audio']}"}), 400
        
        gif_folder = Path(data["gif_folder"])
        if not gif_folder.exists() or not gif_folder.is_dir():
            return jsonify({"error": f"Video folder not found: {data['gif_folder']}"}), 400
        
        mp4_files = list(gif_folder.glob("*.mp4"))
        if not mp4_files:
            return jsonify({"error": f"No MP4 files found in: {data['gif_folder']}"}), 400
        
        # Create job
        job_id = str(uuid.uuid4())
        with job_lock:
            jobs[job_id] = {
                "status": "queued",
                "params": data,
                "message": "Job queued",
            }
            job_logs[job_id] = deque(maxlen=1000)
        
        # Start render in background thread
        params = {
            "audio": str(audio_path),
            "gif_folder": str(gif_folder),
            "duration_seconds": int(data["duration_seconds"]),
            "output": data["output"],
            "width": int(data.get("width", DEFAULT_RESOLUTION[0])),
            "height": int(data.get("height", DEFAULT_RESOLUTION[1])),
            "seed": data.get("seed"),
        }
        
        thread = threading.Thread(target=run_render_job, args=(job_id, params))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "job_id": job_id,
            "status": "queued",
            "message": "Render job started",
        }), 202
        
    except Exception as e:
        return jsonify({"error": f"Failed to start render: {str(e)}"}), 500


@app.route("/api/logs/<job_id>", methods=["GET"])
def stream_logs(job_id: str):
    """Stream logs for a job using Server-Sent Events."""
    
    def generate():
        """Generate SSE log stream."""
        # Send initial connection message
        yield f"data: {json.dumps({'type': 'connected', 'job_id': job_id})}\n\n"
        
        # Send existing logs
        with job_lock:
            if job_id in job_logs:
                for log_msg in job_logs[job_id]:
                    yield f"data: {json.dumps({'type': 'log', 'message': log_msg})}\n\n"
        
        # Stream new logs
        last_count = 0
        while True:
            with job_lock:
                if job_id not in jobs:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Job not found'})}\n\n"
                    break
                
                job_status = jobs[job_id]["status"]
                current_count = len(job_logs.get(job_id, []))
                
                # Send new logs
                if job_id in job_logs and current_count > last_count:
                    for i in range(last_count, current_count):
                        log_msg = list(job_logs[job_id])[i]
                        yield f"data: {json.dumps({'type': 'log', 'message': log_msg})}\n\n"
                    last_count = current_count
                
                # Send status updates
                if job_status in ["complete", "error"]:
                    yield f"data: {json.dumps({'type': 'status', 'status': job_status, 'message': jobs[job_id].get('message', '')})}\n\n"
                    break
            
            import time
            time.sleep(0.1)  # Poll every 100ms
    
    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@app.route("/api/status/<job_id>", methods=["GET"])
def get_status(job_id: str):
    """Get the status of a render job."""
    with job_lock:
        if job_id not in jobs:
            return jsonify({"error": "Job not found"}), 404
        
        job = jobs[job_id]
        return jsonify({
            "job_id": job_id,
            "status": job["status"],
            "message": job.get("message", ""),
        })


@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "ok"}), 200

