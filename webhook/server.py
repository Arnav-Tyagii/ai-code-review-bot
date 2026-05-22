import hmac
import hashlib
import logging
import os
import time
from typing import Dict, Any, Callable

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from reviewer.gemini_reviewer import GeminiReviewer
from reviewer.comment_poster import CommentPoster
from github_client.pr_handler import PRHandler

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Code Review Bot")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Statistics tracker in memory
stats = {
    "total_prs_reviewed": 0,
    "total_issues_found": 0,
    "total_critical_issues": 0
}

@app.middleware("http")
async def log_requests(request: Request, call_next: Callable) -> Response:
    """Middleware to log request method, path, status code, and response time."""
    start_time = time.time()
    response = await call_next(request)
    process_time_ms = (time.time() - start_time) * 1000
    
    logger.info(
        f"Method: {request.method} Path: {request.url.path} "
        f"Status: {response.status_code} Time: {process_time_ms:.2f}ms"
    )
    return response

def verify_signature(payload_body: bytes, signature_header: str) -> bool:
    """Verifies the GitHub webhook signature."""
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not secret:
        logger.warning("GITHUB_WEBHOOK_SECRET not set, skipping signature verification")
        return True
        
    if not signature_header:
        return False
        
    hash_object = hmac.new(secret.encode('utf-8'), msg=payload_body, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + hash_object.hexdigest()
    return hmac.compare_digest(expected_signature, signature_header)

def process_pr_review(repo_full_name: str, pr_number: int):
    """Background task to run the full PR review pipeline."""
    logger.info(f"Starting review pipeline for {repo_full_name} PR #{pr_number}")
    try:
        pr_handler = PRHandler()
        reviewer = GeminiReviewer()
        poster = CommentPoster()
        
        # a. Fetch PR Diff
        diffs = pr_handler.get_pr_diff(repo_full_name, pr_number)
        
        if not diffs:
            logger.info(f"No valid files to review for PR #{pr_number}")
            return
            
        # b. Delete previous bot comments
        poster.delete_previous_bot_comments(repo_full_name, pr_number)
        
        all_issues = []
        
        # c. Review each file
        for file_diff in diffs:
            filename = file_diff["filename"]
            patch = file_diff["patch"]
            issues = reviewer.review_with_retry(filename, patch)
            
            # Add filename to each issue for posting
            for issue in issues:
                issue["filename"] = filename
                
            all_issues.extend(issues)
            
        # Update stats
        stats["total_prs_reviewed"] += 1
        stats["total_issues_found"] += len(all_issues)
        
        critical_count = sum(1 for i in all_issues if i.get("severity", "").lower() == "critical")
        stats["total_critical_issues"] += critical_count
        
        # d. Summarize PR
        summary_dict = reviewer.summarize_pr(all_issues)
        
        # e. Post Review (inline comments)
        poster.post_review(repo_full_name, pr_number, all_issues, summary_dict)
        
        # f. Post Summary Comment
        poster.post_summary_comment(repo_full_name, pr_number, summary_dict)
        
        logger.info(f"Successfully completed review for {repo_full_name} PR #{pr_number}")
        
    except Exception as e:
        logger.error(f"Error in review pipeline for PR #{pr_number}: {e}")

@app.post("/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handles incoming GitHub webhooks."""
    # Read raw body for signature verification
    payload_body = await request.body()
    signature_header = request.headers.get("X-Hub-Signature-256", "")
    
    # 1. Validate signature
    if not verify_signature(payload_body, signature_header):
        raise HTTPException(status_code=401, detail="Invalid signature")
        
    event = request.headers.get("X-GitHub-Event", "")
    
    # Only process pull_request events
    if event != "pull_request":
        return {"status": "ignored", "reason": f"Not a pull_request event, got: {event}"}
        
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
    action = payload.get("action", "")
    
    # Only process opened or synchronize actions
    if action not in ["opened", "synchronize"]:
        return {"status": "ignored", "reason": f"Action '{action}' not processed"}
        
    repo_full_name = payload.get("repository", {}).get("full_name")
    pr_number = payload.get("pull_request", {}).get("number")
    
    if not repo_full_name or not pr_number:
        raise HTTPException(status_code=400, detail="Missing repository or PR number in payload")
        
    # Queue background task
    background_tasks.add_task(process_pr_review, repo_full_name, pr_number)
    
    return {"status": "review queued"}

@app.get("/")
def read_root():
    """Root endpoint providing basic info."""
    return {"message": "AI Code Review Bot is running. See /health or /stats for more info."}

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "version": "1.0.0",
        "gemini": "connected" if os.getenv("GEMINI_API_KEY") else "missing_key",
        "github": "connected" if os.getenv("GITHUB_TOKEN") else "missing_key"
    }

@app.get("/stats")
def get_stats():
    """Returns basic stats about reviews performed."""
    return stats
