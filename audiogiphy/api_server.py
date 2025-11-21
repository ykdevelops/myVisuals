"""
API Server entry point for AudioGiphy.

Starts the Flask development server for the Vue.js frontend.
"""

import logging
import sys
from pathlib import Path

from audiogiphy.api import app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)


def main():
    """Start the Flask API server."""
    # Check if frontend dist exists
    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        # Serve static files from frontend/dist
        from flask import send_from_directory
        
        @app.route("/", defaults={"path": ""})
        @app.route("/<path:path>")
        def serve_frontend(path):
            if path and (frontend_dist / path).exists():
                return send_from_directory(str(frontend_dist), path)
            return send_from_directory(str(frontend_dist), "index.html")
        
        logger.info("Serving frontend from frontend/dist")
    else:
        logger.info("Frontend dist not found, API only mode")
    
    port = 5001  # Use 5001 to avoid conflict with macOS AirPlay on 5000
    logger.info(f"Starting AudioGiphy API server on http://localhost:{port}")
    logger.info("API endpoints:")
    logger.info("  POST   /api/render - Start a render job")
    logger.info("  GET    /api/logs/<job_id> - Stream logs (SSE)")
    logger.info("  GET    /api/status/<job_id> - Get job status")
    logger.info("  GET    /api/health - Health check")
    
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True)


if __name__ == "__main__":
    main()

