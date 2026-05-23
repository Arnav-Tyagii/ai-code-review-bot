import json
import pytest
from unittest.mock import patch, MagicMock, call

from reviewer.gemini_reviewer import GeminiReviewer
from github_client.pr_handler import PRHandler
from webhook.server import verify_signature, app
from fastapi.testclient import TestClient

client = TestClient(app)

# --- GeminiReviewer Tests ---

@pytest.fixture
def mock_gemini_response():
    mock_response = MagicMock()
    mock_response.text = '''```json
[
  {
    "line": 10,
    "severity": "warning",
    "category": "style",
    "comment": "Use a descriptive variable name.",
    "suggestion": "user_age = 25"
  }
]
```'''
    return mock_response

@patch("reviewer.gemini_reviewer.genai.GenerativeModel")
def test_review_file_valid_json(mock_model_class, mock_gemini_response):
    mock_model = mock_model_class.return_value
    mock_model.generate_content.return_value = mock_gemini_response
    
    reviewer = GeminiReviewer()
    issues = reviewer.review_file("test.py", "+ x = 25")
    
    assert len(issues) == 1
    assert issues[0]["line"] == 10
    assert issues[0]["severity"] == "warning"

@patch("reviewer.gemini_reviewer.genai.GenerativeModel")
def test_review_file_malformed_json(mock_model_class):
    mock_response = MagicMock()
    mock_response.text = "This is not json"
    
    mock_model = mock_model_class.return_value
    mock_model.generate_content.return_value = mock_response
    
    reviewer = GeminiReviewer()
    issues = reviewer.review_file("test.py", "+ x = 25")
    
    assert issues == []

@patch("reviewer.gemini_reviewer.genai.GenerativeModel")
@patch("reviewer.gemini_reviewer.time.sleep")
def test_review_with_retry_fails_3_times(mock_sleep, mock_model_class):
    mock_model = mock_model_class.return_value
    mock_model.generate_content.side_effect = Exception("API Error")
    
    reviewer = GeminiReviewer()
    issues = reviewer.review_with_retry("test.py", "+ x = 25", max_retries=3)
    
    assert issues == []
    assert mock_model.generate_content.call_count == 3
    # Called with exponential backoff times 1, 2 plus the 0.5s initial delays
    assert mock_sleep.call_count == 5 

# --- PRHandler Tests ---

@pytest.fixture
def mock_github():
    with patch("github_client.pr_handler.Github") as mock_gh:
        yield mock_gh

def test_pr_handler_filters(mock_github):
    mock_repo = MagicMock()
    mock_pr = MagicMock()
    
    # Setup files: one python, one md, one too large, one in node_modules
    file1 = MagicMock(filename="valid.py", changes=10, patch="+ x=1", additions=1, deletions=0)
    file2 = MagicMock(filename="readme.md", changes=10, patch="+ read me", additions=1, deletions=0)
    file3 = MagicMock(filename="huge.py", changes=600, patch="+ lots", additions=600, deletions=0)
    file4 = MagicMock(filename="node_modules/dep.js", changes=10, patch="+ foo", additions=1, deletions=0)
    
    mock_pr.get_files.return_value = [file1, file2, file3, file4]
    mock_repo.get_pull.return_value = mock_pr
    mock_github.return_value.get_repo.return_value = mock_repo
    
    handler = PRHandler()
    diffs = handler.get_pr_diff("owner/repo", 1)
    
    assert len(diffs) == 1
    assert diffs[0]["filename"] == "valid.py"

def test_pr_handler_caching(mock_github):
    mock_repo = MagicMock()
    mock_pr = MagicMock()
    
    file1 = MagicMock(filename="valid.py", changes=10, patch="+ x=1", additions=1, deletions=0)
    mock_pr.get_files.return_value = [file1]
    mock_repo.get_pull.return_value = mock_pr
    mock_github.return_value.get_repo.return_value = mock_repo
    
    handler = PRHandler()
    # Call twice
    diffs1 = handler.get_pr_diff("owner/repo", 1)
    diffs2 = handler.get_pr_diff("owner/repo", 1)
    
    assert len(diffs1) == 1
    assert diffs1 == diffs2
    # Should only fetch files once
    mock_pr.get_files.assert_called_once()

# --- Webhook Tests ---

@patch("webhook.server.os.getenv")
def test_valid_hmac_signature(mock_getenv):
    mock_getenv.return_value = "my_secret"
    payload = b'{"hello": "world"}'
    
    import hmac
    import hashlib
    hash_object = hmac.new(b"my_secret", msg=payload, digestmod=hashlib.sha256)
    expected_sig = "sha256=" + hash_object.hexdigest()
    
    assert verify_signature(payload, expected_sig) is True
    assert verify_signature(payload, "sha256=invalid") is False

@patch("webhook.server.verify_signature", return_value=True)
def test_non_pull_request_event(mock_verify):
    response = client.post("/webhook", json={}, headers={"X-GitHub-Event": "push"})
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"

@patch("webhook.server.verify_signature", return_value=True)
def test_pull_request_closed_event(mock_verify):
    response = client.post(
        "/webhook", 
        json={"action": "closed"}, 
        headers={"X-GitHub-Event": "pull_request"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"

@patch("webhook.server.verify_signature", return_value=False)
def test_invalid_signature_401(mock_verify):
    response = client.post(
        "/webhook", 
        json={"action": "opened"}, 
        headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": "invalid"}
    )
    assert response.status_code == 401


#testing bad code
import os


def login(u, p, debug=False):
    # BAD PRACTICE: Global mutable variable modification inside a local scope
    global attempts
    attempts = attempts + 1

    # SECURITY ISSUE: SQL Injection via string interpolation (never do this!)
    # SECURITY ISSUE: Plaintext password handling (never store or query raw passwords)
    query = f"SELECT * FROM users WHERE username = '{u}' AND password = '{p}'"

    if debug:
        # SECURITY ISSUE: Info disclosure / Leaking sensitive query text to logs/output
        print(f"Executing: {query}")

        # SECURITY ISSUE: Remote Code Execution (RCE) / Arbitrary Command Execution
        # Blindly executing user input via system shell
        os.system("echo debug_user: " + u)

    # BAD PRACTICE: Using 'eval' to run code or fetch a hardcoded mockup dictionary
    # SECURITY ISSUE: Arbitrary code execution if data source is untrusted
    db_mock = eval("{'admin': 'super_secret_password123'}")

    # BAD PRACTICE: Broad, generic exception handling that silences all errors
    try:
        if db_mock.get(u) == p:
            return "SUCCESS"
        else:
            return "FAIL"
    except Exception:
        # BAD PRACTICE: Bare pass or generic return on failure completely hides bugs
        return None
