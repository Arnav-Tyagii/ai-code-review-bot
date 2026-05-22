import logging
import os
from typing import List, Dict, Any

from github import Github
from github.PullRequest import PullRequest
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class CommentPoster:
    """
    Handles posting review comments and summaries to GitHub PRs.
    """
    def __init__(self):
        """Initializes the CommentPoster and authenticates with GitHub."""
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            logger.warning("GITHUB_TOKEN environment variable not set. Posting comments will fail.")
        self.github = Github(token)

    def _get_pr(self, repo_full_name: str, pr_number: int) -> PullRequest:
        """Helper to get a PullRequest object."""
        repo = self.github.get_repo(repo_full_name)
        return repo.get_pull(pr_number)

    def post_review(self, repo_full_name: str, pr_number: int, file_comments: List[Dict[str, Any]], pr_summary_dict: Dict[str, Any]) -> None:
        """
        Posts a single PR review using GitHub's create_review API.
        
        Args:
            repo_full_name: The full name of the repository (e.g., 'owner/repo').
            pr_number: The pull request number.
            file_comments: List of issue dictionaries from GeminiReviewer.
            pr_summary_dict: Summary dictionary from GeminiReviewer.
        """
        try:
            pr = self._get_pr(repo_full_name, pr_number)
            
            # Map severity to emojis
            emoji_map = {
                'critical': '🔴',
                'warning': '🟡',
                'suggestion': '🟢'
            }
            
            comments_for_api = []
            for issue in file_comments:
                severity = issue.get('severity', 'suggestion').lower()
                emoji = emoji_map.get(severity, '🟢')
                category = issue.get('category', 'general')
                comment_text = issue.get('comment', '')
                suggestion = issue.get('suggestion', '')
                
                # We need the filename and line number
                filename = issue.get('filename')
                line = issue.get('line')
                
                if not filename or not line:
                    logger.warning(f"Issue missing filename or line, skipping: {issue}")
                    continue
                
                body = f"{emoji} **[{category}]** {comment_text}\n\n💡 *Suggested fix:*\n```python\n{suggestion}\n```"
                
                comments_for_api.append({
                    "path": filename,
                    "line": int(line),
                    "body": body
                })
            
            logger.info(f"Prepared {len(comments_for_api)} inline comments for API.")
            
            # Format the review body
            risk_emoji = self._get_risk_emoji(pr_summary_dict.get('risk_level', 'medium'))
            risk_level = str(pr_summary_dict.get('risk_level', 'medium')).capitalize()
            summary_text = pr_summary_dict.get('summary', 'No summary provided.')
            
            review_body = f"## AI Code Review Complete\n\n**Risk Level:** {risk_emoji} {risk_level}\n\n{summary_text}"
            
            # Create the review
            # If there are no inline comments, we just create a review without them
            if comments_for_api:
                pr.create_review(body=review_body, comments=comments_for_api, event="COMMENT")
                logger.info(f"Posted review with {len(comments_for_api)} inline comments to PR #{pr_number}")
            else:
                pr.create_review(body=review_body, event="COMMENT")
                logger.info(f"Posted review with no inline comments to PR #{pr_number}")
                
        except Exception as e:
            logger.error(f"Error posting review to {repo_full_name} PR #{pr_number}: {e}")
            # If creating a review WITH comments fails (e.g., due to invalid line numbers),
            # try falling back to just the top-level review body without comments
            if "comments_for_api" in locals() and comments_for_api:
                logger.info("Attempting to post review without inline comments as fallback...")
                try:
                    pr.create_review(body=review_body + "\n\n*(Note: Inline comments failed to post, likely due to line number mismatches in the diff)*", event="COMMENT")
                except Exception as fallback_e:
                    logger.error(f"Fallback review posting also failed: {fallback_e}")

    def post_summary_comment(self, repo_full_name: str, pr_number: int, pr_summary_dict: Dict[str, Any]) -> None:
        """
        Posts a top-level summary comment to the PR.
        
        Args:
            repo_full_name: The full name of the repository.
            pr_number: The pull request number.
            pr_summary_dict: Summary dictionary from GeminiReviewer.
        """
        try:
            pr = self._get_pr(repo_full_name, pr_number)
            
            risk_level = str(pr_summary_dict.get('risk_level', 'medium')).lower()
            risk_emoji = self._get_risk_emoji(risk_level)
            
            critical = pr_summary_dict.get('must_fix_count', 0)
            warnings = pr_summary_dict.get('warnings_count', 0)
            suggestions = pr_summary_dict.get('suggestions_count', 0)
            
            summary = pr_summary_dict.get('summary', 'No summary generated.')
            
            good_practices = pr_summary_dict.get('good_practices', [])
            good_practices_list = "\n".join([f"- {gp}" for gp in good_practices]) if good_practices else "- None identified"
            
            comment_body = f"""## 🤖 AI Code Review Complete
   
**Risk Level:** {risk_emoji} {risk_level.capitalize()}
**Issues Found:** 🔴 {critical} Critical | 🟡 {warnings} Warnings | 🟢 {suggestions} Suggestions

### Summary
{summary}

### ✅ Good Practices Detected
{good_practices_list}

---
*Reviewed by AI Code Review Bot using Gemini AI*"""
            
            pr.create_issue_comment(comment_body)
            logger.info(f"Posted summary comment to PR #{pr_number}")
            
        except Exception as e:
            logger.error(f"Error posting summary comment to {repo_full_name} PR #{pr_number}: {e}")

    def delete_previous_bot_comments(self, repo_full_name: str, pr_number: int) -> None:
        """
        Deletes any previous comments made by this bot on the PR.
        
        Args:
            repo_full_name: The full name of the repository.
            pr_number: The pull request number.
        """
        try:
            pr = self._get_pr(repo_full_name, pr_number)
            
            # We need to find comments created by our bot user.
            # Using PyGithub, we can get the authenticated user to compare logins.
            bot_user = self.github.get_user().login
            
            # Delete review comments (inline)
            for comment in pr.get_review_comments():
                if comment.user.login == bot_user:
                    comment.delete()
                    
            # Delete issue comments (top-level)
            for comment in pr.get_issue_comments():
                if comment.user.login == bot_user:
                    comment.delete()
                    
            logger.info(f"Deleted previous bot comments on PR #{pr_number}")
            
        except Exception as e:
            logger.error(f"Error deleting previous bot comments on {repo_full_name} PR #{pr_number}: {e}")

    def _get_risk_emoji(self, risk_level: str) -> str:
        """Helper to map risk level to emoji."""
        risk_level = risk_level.lower()
        if risk_level == 'low':
            return '🟢'
        elif risk_level == 'medium':
            return '🟡'
        elif risk_level == 'high':
            return '🔴'
        return '🟡'
