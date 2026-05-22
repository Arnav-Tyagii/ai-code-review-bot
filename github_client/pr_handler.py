import logging
import os
from typing import List, Dict, Any, Tuple

from github import Github
from github.PullRequest import PullRequest
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'.py', '.js', '.ts', '.java', '.cpp', '.go'}
IGNORED_DIRS = {'node_modules/', '.git/', 'dist/', 'build/', '__pycache__/'}
MAX_DIFF_LINES = 500

class PRHandler:
    """
    Handles fetching and filtering pull request details and diffs.
    """
    def __init__(self):
        """Initializes the PRHandler and authenticates with GitHub."""
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            logger.warning("GITHUB_TOKEN environment variable not set. GitHub API calls will fail.")
        self.github = Github(token)
        # In-memory cache: (repo_full_name, pr_number) -> List of file dicts
        self._diff_cache: Dict[Tuple[str, int], List[Dict[str, Any]]] = {}

    def _get_pr(self, repo_full_name: str, pr_number: int) -> PullRequest:
        """Helper to get a PullRequest object."""
        try:
            repo = self.github.get_repo(repo_full_name)
            return repo.get_pull(pr_number)
        except Exception as e:
            logger.error(f"Failed to fetch PR {pr_number} from {repo_full_name}: {e}")
            raise

    def get_pr_details(self, repo_full_name: str, pr_number: int) -> Tuple[str, str, str, str]:
        """
        Fetches basic details of a pull request.
        
        Args:
            repo_full_name: The full name of the repository.
            pr_number: The pull request number.
            
        Returns:
            A tuple of (title, author, branch, base_branch).
        """
        pr = self._get_pr(repo_full_name, pr_number)
        title = pr.title
        author = pr.user.login
        branch = pr.head.ref
        base_branch = pr.base.ref
        return title, author, branch, base_branch

    def get_pr_diff(self, repo_full_name: str, pr_number: int) -> List[Dict[str, Any]]:
        """
        Fetches and filters the diff of a pull request.
        Caches the result in memory to avoid re-fetching.
        
        Args:
            repo_full_name: The full name of the repository.
            pr_number: The pull request number.
            
        Returns:
            A list of dictionary objects, each representing a changed file.
            Keys: 'filename', 'patch', 'additions', 'deletions'.
        """
        cache_key = (repo_full_name, pr_number)
        if cache_key in self._diff_cache:
            logger.info(f"Returning cached diff for PR #{pr_number}")
            return self._diff_cache[cache_key]

        pr = self._get_pr(repo_full_name, pr_number)
        files = pr.get_files()
        
        filtered_files = []
        for file in files:
            filename = file.filename
            
            # Check ignored directories
            if any(ignored in filename for ignored in IGNORED_DIRS):
                logger.debug(f"Skipping {filename}: in ignored directory")
                continue
                
            # Check file extension
            ext = os.path.splitext(filename)[1]
            if ext not in ALLOWED_EXTENSIONS:
                logger.debug(f"Skipping {filename}: unsupported extension {ext}")
                continue
                
            # Check diff size
            # Calculate approx diff lines from additions and deletions if patch is missing
            diff_lines = file.changes
            if diff_lines > MAX_DIFF_LINES:
                logger.debug(f"Skipping {filename}: diff too large ({diff_lines} lines)")
                continue
                
            # Need a patch to review
            if not file.patch:
                logger.debug(f"Skipping {filename}: no patch available")
                continue
                
            filtered_files.append({
                "filename": filename,
                "patch": file.patch,
                "additions": file.additions,
                "deletions": file.deletions
            })
            
        logger.info(f"Fetched diff for PR #{pr_number}, {len(filtered_files)} files included for review.")
        
        # Save to cache
        self._diff_cache[cache_key] = filtered_files
        
        return filtered_files
