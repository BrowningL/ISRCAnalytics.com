import os
import time
import asyncio
import schedule
import logging
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
import threading

from streams_service import run_streams_collection
from playlist_followers_service import run_playlist_followers_collection
from catalogue_health_service import run_catalogue_health_check

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
)
logger = logging.getLogger("worker_orchestrator")

# Flask app for HTTP endpoints
app = Flask(__name__)

# Configuration
ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "true").lower() in ("1", "true", "yes")
SCHEDULE_EVERY_HOURS = int(os.getenv("SCHEDULE_EVERY_HOURS", "6"))
AUTOMATION_TOKEN = os.getenv("AUTOMATION_TOKEN")

# Global state
running_task = None
task_lock = threading.Lock()

def check_token():
    """Check automation token if configured."""
    if not AUTOMATION_TOKEN:
        return True
    
    token = request.headers.get("x-automation-token") or request.args.get("token")
    return token == AUTOMATION_TOKEN

async def run_all_tasks(user_id: str, day_override: str = None):
    """Run all data collection tasks for a user."""
    logger.info(f"Starting all tasks for user {user_id}")
    
    try:
        # Run streams collection
        await run_streams_collection(user_id, day_override)
        
        # Run playlist followers collection
        run_playlist_followers_collection(user_id, day_override)
        
        # Run catalogue health check (once per day)
        if not day_override or day_override == datetime.now().date().isoformat():
            run_catalogue_health_check(user_id)
        
        logger.info(f"All tasks completed for user {user_id}")
        return {"status": "success", "user_id": user_id}
    
    except Exception as e:
        logger.error(f"Task execution failed for user {user_id}: {e}")
        return {"status": "error", "error": str(e)}

def scheduled_job():
    """Run scheduled job for all users."""
    logger.info("Running scheduled job")
    
    # In production, this would query all active users from the database
    # For now, using a placeholder
    user_ids = ["test-user-id"]  # Replace with actual user query
    
    for user_id in user_ids:
        asyncio.run(run_all_tasks(user_id))

@app.route("/")
def index():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "scheduler_enabled": ENABLE_SCHEDULER,
        "schedule_hours": SCHEDULE_EVERY_HOURS,
        "timestamp": datetime.now().isoformat()
    })

@app.route("/run", methods=["POST"])
def run_manual():
    """Manually trigger data collection for a user."""
    if not check_token():
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.json or {}
    user_id = data.get("user_id")
    date = data.get("date")
    
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    
    global running_task
    
    with task_lock:
        if running_task and not running_task.done():
            return jsonify({"error": "Task already running"}), 429
        
        # Run in background
        loop = asyncio.new_event_loop()
        threading.Thread(
            target=lambda: loop.run_until_complete(run_all_tasks(user_id, date)),
            daemon=True
        ).start()
    
    return jsonify({"status": "started", "user_id": user_id}), 202

@app.route("/run_streams", methods=["POST"])
async def run_streams_only():
    """Run only streams collection."""
    if not check_token():
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.json or {}
    user_id = data.get("user_id")
    
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    
    result = await run_streams_collection(user_id, data.get("date"))
    return jsonify(result)

@app.route("/run_followers", methods=["POST"])
def run_followers_only():
    """Run only playlist followers collection."""
    if not check_token():
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.json or {}
    user_id = data.get("user_id")
    
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    
    run_playlist_followers_collection(user_id, data.get("date"))
    return jsonify({"status": "completed"})

@app.route("/run_health_check", methods=["POST"])
def run_health_only():
    """Run only catalogue health check."""
    if not check_token():
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.json or {}
    user_id = data.get("user_id")
    
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    
    run_catalogue_health_check(user_id)
    return jsonify({"status": "completed"})

def start_scheduler():
    """Start the scheduler in a background thread."""
    if ENABLE_SCHEDULER:
        logger.info(f"Scheduler enabled: running every {SCHEDULE_EVERY_HOURS} hours")
        
        # Schedule the job
        schedule.every(SCHEDULE_EVERY_HOURS).hours.do(scheduled_job)
        
        # Run scheduler in background
        def run_schedule():
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        
        threading.Thread(target=run_schedule, daemon=True).start()
    else:
        logger.info("Scheduler disabled")

if __name__ == "__main__":
    # Start scheduler
    start_scheduler()
    
    # Start Flask app
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
