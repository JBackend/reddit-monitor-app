# Reddit Monitor

AI-powered brand intelligence from real Reddit discussions. Enter your brand, competitors, and keywords — get a strategic report with sentiment analysis, competitive landscape, pain points, and actionable recommendations.

**Live app:** [redditmonitor.jaskaranbedi.com](https://redditmonitor.jaskaranbedi.com)

---

## How It Works

1. **Monitor** — Searches Reddit via PullPush.io for your brand, competitors, and industry keywords
2. **Analyze** — Claude AI reads every post and comment to extract strategic insights
3. **Report** — Structured intelligence report with tables, quotes, and recommendations

Each report covers: brand perception, competitive landscape, market insights, pain points, recommendation patterns, threats, actionable recommendations, and a quote bank.

---

## Architecture

| Component | Platform | Role |
|-----------|----------|------|
| Frontend | Vercel (static) | Form UI, report rendering, local caching |
| API | Fly.io (Docker) | Reddit search, Claude analysis, server-side caching |

The frontend is a single HTML page (`docs/index.html`). The API is a Flask server (`server.py`) that wraps the analysis pipeline (`api/analyze.py`).

**Why the split?** Vercel serverless functions have a 60-second timeout. The analysis pipeline (Reddit search + comment fetching + Claude) takes 30-60 seconds, leaving no room for retries. Fly.io has no timeout, enabling retry logic, in-memory caching, and rate limiting.

---

## Self-Hosting

Fork this repo and deploy your own instance. You'll need:
- An [Anthropic API key](https://console.anthropic.com/) (~$2.50/report)
- A [Fly.io](https://fly.io) account (~$3/month)
- A [Vercel](https://vercel.com) account (free)

### 1. Deploy the API on Fly.io

```bash
# Install Fly CLI
brew install flyctl   # macOS
# or: curl -L https://fly.io/install.sh | sh

# Login and create the app
fly auth login
fly apps create your-app-name --machines

# Set your API key
fly secrets set ANTHROPIC_API_KEY=sk-ant-your-key-here -a your-app-name

# Deploy
fly deploy -a your-app-name
```

Update `app` in `fly.toml` to match your app name. Verify with:

```bash
curl https://your-app-name.fly.dev/health
```

### 2. Deploy the Frontend on Vercel

1. Import the repo on [vercel.com/new](https://vercel.com/new)
2. Vercel auto-detects the config from `vercel.json`
3. No environment variables needed — the frontend is purely static

### 3. Update the API URL

In `docs/index.html`, replace the two occurrences of `redditmonitor-api.fly.dev` with your Fly.io app URL.

### 4. Update CORS

In `server.py`, change `ALLOWED_ORIGIN` to your Vercel domain.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check — returns `{"status": "ok"}` |
| `POST` | `/analyze` | Run the analysis pipeline |

### POST /analyze

```json
{
  "brand": "Linear",
  "aliases": ["linear", "linear.app"],
  "competitors": ["jira", "asana"],
  "keywords": ["project management", "issue tracker"],
  "subreddits": ["programming", "devops"]
}
```

Returns a report with `cached: true/false` flag and stats (posts found, posts analyzed, cost estimate).

**Rate limits:** 10 requests per IP per hour (server-side). 2 requests per day (client-side, localStorage).

---

## Project Structure

```
api/
  analyze.py        # Analysis pipeline — search, filter, Claude analysis
  __init__.py       # Package marker
server.py           # Flask API server (Fly.io entry point)
docs/
  index.html        # Frontend (Vercel entry point)
  style.css         # Styles
  dev-decisions.md  # Development decision log
Dockerfile          # Container for Fly.io
fly.toml            # Fly.io config
requirements.txt    # Python dependencies (Flask, gunicorn)
vercel.json         # Vercel routing config
```

---

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set your API key
export ANTHROPIC_API_KEY=sk-ant-...

# Run the server
python -m gunicorn server:app --bind 0.0.0.0:8080 --workers 1 --threads 2
```

Then open `docs/index.html` in a browser (update the fetch URL to `http://localhost:8080/analyze` for local testing).

---

## License

MIT — see [LICENSE](LICENSE).
