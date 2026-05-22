import json
import logging
import os
import re
import time
from typing import List, Dict, Any

import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class GeminiReviewer:
    """
    Handles interacting with the Google Gemini API to review code diffs.
    """
    def __init__(self):
        """Initializes the GeminiReviewer and configures the API key."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY environment variable not set. Reviews will fail.")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-3.5-flash')

    def review_file(self, filename: str, patch: str) -> List[Dict[str, Any]]:
        """
        Sends the patch to Gemini for code review.
        
        Args:
            filename: The name of the file being reviewed.
            patch: The git diff patch of the file.
            
        Returns:
            A list of dictionary objects representing issues found.
        """
        prompt = f"""You are a senior software engineer doing a thorough 
code review. Analyze this git diff carefully.

For each issue found, return a JSON array where each 
item has exactly these fields:
- line: line number in the diff where the issue is (integer)
- severity: one of 'critical', 'warning', 'suggestion'  
- category: one of 'bug', 'security', 'oop_violation',
  'style', 'performance', 'best_practice'
- comment: clear explanation + how to fix it (2-3 sentences)
- suggestion: the corrected code snippet (1-5 lines)

Filename: {filename}
Diff:
{patch}

Rules:
- Return ONLY a valid JSON array. No markdown blocks, no conversational text.
- If no issues found, return EXACTLY: []
- Only flag real issues, not personal preferences
- For security issues, always include severity: critical
- Maximum 8 issues per file to avoid noise"""

        try:
            response = self.model.generate_content(prompt)
            # Safely get text
            try:
                text_response = response.text
            except ValueError:
                logger.error(f"Gemini blocked response for {filename}")
                return []
            
            # Extract the JSON array by finding the first '[' and last ']'
            start_idx = text_response.find('[')
            end_idx = text_response.rfind(']')
            if start_idx != -1 and end_idx != -1:
                cleaned_text = text_response[start_idx:end_idx+1]
            else:
                cleaned_text = text_response
            
            issues = json.loads(cleaned_text)
            
            if not isinstance(issues, list):
                logger.error(f"Gemini returned non-list JSON for {filename}: {issues}")
                return []
                
            logger.info(f"Reviewing {filename}: found {len(issues)} issues")
            return issues
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response from Gemini for {filename}: {e}\nRaw Response: {text_response}")
            return []
        except Exception as e:
            logger.error(f"Error during Gemini review for {filename}: {e}")
            raise e

    def review_with_retry(self, filename: str, patch: str, max_retries: int = 3) -> List[Dict[str, Any]]:
        """
        Reviews a file with exponential backoff on failure.
        
        Args:
            filename: The name of the file being reviewed.
            patch: The git diff patch of the file.
            max_retries: Maximum number of retry attempts.
            
        Returns:
            A list of issues found, or an empty list if all retries fail.
        """
        backoff_times = [1, 2, 4]
        
        for attempt in range(max_retries):
            try:
                # Add delay to avoid rate limiting
                time.sleep(0.5)
                return self.review_file(filename, patch)
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {filename}: {e}")
                if attempt < max_retries - 1:
                    sleep_time = backoff_times[attempt] if attempt < len(backoff_times) else backoff_times[-1]
                    logger.info(f"Retrying in {sleep_time} seconds...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"All retries failed for {filename}")
                    
        return []

    def summarize_pr(self, all_files_issues: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generates a summary of the entire pull request based on all issues found.
        
        Args:
            all_files_issues: A combined list of all issues found across all files.
            
        Returns:
            A dictionary containing the PR summary.
        """
        issues_json = json.dumps(all_files_issues, indent=2)
        
        prompt = f"""You are a senior software engineer summarizing a code review.
Given this list of issues found in the Pull Request, generate a summary.

Return a JSON object with exactly these fields:
- summary: "3 sentence overall PR summary"
- risk_level: "low", "medium", or "high"
- must_fix_count: number of critical issues (integer)
- warnings_count: number of warning issues (integer)
- suggestions_count: number of suggestion issues (integer)
- good_practices: ["list of things done well"]

Issues:
{issues_json}

Rules:
- Return ONLY a valid JSON object. No markdown blocks, no conversational text.
- Evaluate the risk level based on the severity and number of issues
- If no issues are provided, assume risk_level is 'low' and summarize accordingly."""

        try:
            response = self.model.generate_content(prompt)
            try:
                text_response = response.text
            except ValueError:
                logger.error("Gemini blocked response for summary")
                return self._get_default_summary()
            
            # Extract the JSON object by finding the first '{' and last '}'
            start_idx = text_response.find('{')
            end_idx = text_response.rfind('}')
            if start_idx != -1 and end_idx != -1:
                cleaned_text = text_response[start_idx:end_idx+1]
            else:
                cleaned_text = text_response
            
            summary = json.loads(cleaned_text)
            
            if not isinstance(summary, dict):
                logger.error(f"Gemini returned non-dict JSON for summary: {summary}")
                return self._get_default_summary()
                
            return summary
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response for summary: {e}\nRaw Response: {text_response}")
            return self._get_default_summary()
        except Exception as e:
            logger.error(f"Error during PR summarization: {e}")
            return self._get_default_summary()
            
    def _get_default_summary(self) -> Dict[str, Any]:
        """Returns a default summary structure in case of failure."""
        return {
            "summary": "Could not generate AI summary due to an error.",
            "risk_level": "medium",
            "must_fix_count": 0,
            "warnings_count": 0,
            "suggestions_count": 0,
            "good_practices": ["Unable to determine"]
        }
