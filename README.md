# AI Code Review Bot [![Python 3.12.10](https://img.shields.io/badge/python-3.12.10-blue.svg)](https://www.python.org/downloads/release/python-31210/) [![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

A fast, automated code review bot that uses Google's Gemini AI to analyze pull request diffs and post inline feedback on GitHub.

## How it works

```text
+-----------+      +-----------+      +------------+      +---------------+      +---------------+
| PR Opened | ---> |  Webhook  | ---> | Fetch Diff | ---> | Gemini Review | ---> | Post Comments |
+-----------+      +-----------+      +------------+      +---------------+      +---------------+
```

## Features
- **Smart Detection**: Detects bugs, security vulnerabilities, OOP violations, and more.
- **Inline Comments**: Posts inline comments on exact lines with code snippet fix suggestions.
- **Clean PRs**: Deletes old bot comments on re-push so PRs don't get spammed.
- **Risk Assessment**: Provides an overall PR risk assessment (low/medium/high) and highlights good practices.
- **Analytics**: Built-in `/stats` endpoint to track review history and issues found.
- **Responsive**: Sub-5 second response time via background tasks (webhook returns instantly).
- **Filtered & Cached**: Ignores noise like `node_modules`, `dist` and caches diffs in memory to avoid redundant API calls.

## Setup in 5 Steps

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd ai-code-review-bot
   ```

2. **Configure Environment Variables**
   ```bash
   cp .env.example .env
   # Edit .env and add your GEMINI_API_KEY, GITHUB_TOKEN, and GITHUB_WEBHOOK_SECRET
   ```

3. **Build the Docker Image**
   ```bash
   docker build -t ai-code-review-bot .
   ```

4. **Deploy**
   This project is set up with GitHub Actions to deploy to Railway automatically on push to `main`. 
   Set your `RAILWAY_TOKEN` and (optionally) `SLACK_WEBHOOK_URL` in your GitHub repository secrets.

5. **Set Webhook URL**
   Go to your GitHub Repository Settings -> Webhooks -> Add webhook.
   - Payload URL: `https://<your-deployed-domain>/webhook`
   - Content type: `application/json`
   - Secret: Your `GITHUB_WEBHOOK_SECRET`
   - Events: Select "Let me select individual events" -> "Pull requests"

## Example Screenshot
![Screenshot Placeholder](https://via.placeholder.com/800x400.png?text=AI+Code+Review+Example+Comment)

## Contributing
Contributions are welcome! Please open an issue or submit a Pull Request if you have improvements. Make sure to run the tests locally:
```bash
pytest tests/ -v
```
