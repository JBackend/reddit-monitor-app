# Reddit Monitor

Automated Reddit monitoring for brand intelligence. Get email alerts and a web dashboard when your brand, competitors, or industry keywords appear on Reddit.

**Zero dependencies** — runs on Python 3.11+ stdlib only. No `pip install` needed.

## How It Works

1. Searches Reddit for your brand, competitors, and industry keywords
2. Filters and prioritizes posts (URGENT / HIGH / MEDIUM)
3. Sends you an HTML email report with findings
4. Updates a web dashboard you can check anytime

Runs automatically via GitHub Actions — no server required.

---

## Quickstart (5 minutes)

### Step 1: Fork this repository

Click the **Fork** button at the top right of this page. This creates your own copy.

### Step 2: Edit your configuration

Open `config.toml` in your fork (click the file, then the pencil icon to edit).

Replace the example values with your brand:

```toml
[brand]
name = "Your Company"
aliases = ["your company", "yourcompany", "yourcompany.com"]

[competitors]
names = ["competitor1", "competitor2", "competitor3"]
```

Update the `[subreddits]`, `[keywords]`, and `[[queries.daily]]` / `[[queries.weekly]]` sections to match your industry. See [Configuration Reference](#configuration-reference) below for details.

Commit the changes.

### Step 3: Add email secrets

Go to your fork's **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.

Add these 5 secrets:

| Secret name | Value | Example |
|---|---|---|
| `SMTP_SERVER` | Your email server | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP port | `587` |
| `SMTP_USERNAME` | Your email address | `you@gmail.com` |
| `SMTP_PASSWORD` | App password (not your regular password) | `abcd efgh ijkl mnop` |
| `EMAIL_RECIPIENTS` | Comma-separated recipient list | `you@gmail.com,team@company.com` |

<details>
<summary><strong>Gmail setup instructions</strong></summary>

1. Go to https://myaccount.google.com/apppasswords
2. Select **Mail** and your device
3. Click **Generate** — copy the 16-character password
4. Use `smtp.gmail.com` as the server and `587` as the port
5. Use your Gmail address as the username and the app password as the password

Note: You need 2-Factor Authentication enabled on your Google account to create app passwords.
</details>

### Step 4: Enable GitHub Pages

Go to **Settings** → **Pages** → Under "Source", select **Deploy from a branch** → Choose `main` branch and `/docs` folder → **Save**.

Your dashboard will be at: `https://YOUR-USERNAME.github.io/RedditScraper/`

### Step 5: Enable GitHub Actions

Go to the **Actions** tab. If you see a prompt about enabling workflows, click **"I understand my workflows, go ahead and enable them"**.

### Step 6: Test it

Go to **Actions** → Click **Reddit Monitor** in the left sidebar → Click **Run workflow** → Select `daily` → Click **Run workflow**.

Wait a few minutes, then check:
- Your email inbox for the report
- Your GitHub Pages dashboard

---

## Configuration Reference

### `[brand]`

```toml
[brand]
name = "Your Company"           # Display name used in reports
aliases = ["your company", ...] # Search terms (lowercase) — matches in post text trigger URGENT priority
```

### `[competitors]`

```toml
[competitors]
names = ["competitor1", ...]    # Competitor names (lowercase) — matches trigger HIGH priority
```

### `[subreddits]`

```toml
[subreddits]
high_value = ["subreddit1", ...] # Posts in these subs are always considered relevant
```

### `[keywords]`

```toml
[keywords]
relevance = ["keyword1", ...]   # Posts must contain at least one keyword to be included
geographic = ["region1", ...]   # Used for priority classification context
```

### `[[queries.daily]]` and `[[queries.weekly]]`

```toml
[[queries.daily]]
label = "my_search"              # Unique label for tracking
query = "search terms here"      # Reddit search query
subreddit = "optional_sub"       # Optional — omit to search all of Reddit
```

Daily queries run Monday-Friday. Weekly queries run on Mondays along with daily queries.

### `[[queries.scrape]]`

One-shot deep research queries used with `python -m reddit_monitor scrape`. These search the past year for baseline data collection.

### `[settings]`

```toml
[settings]
user_agent = "..."              # Browser user-agent string
rate_delay = 2                  # Seconds between API requests
max_results_per_query = 25      # Posts per search query
max_comments_to_fetch = 15      # Max posts to fetch comments for
min_comments_for_fetch = 5      # Only fetch comments if post has more than this
max_seen_ids = 5000             # Max tracked post IDs (older ones are pruned)
```

---

## Running Locally

Requires Python 3.11 or later. No packages to install.

```bash
# Daily monitoring
python -m reddit_monitor monitor --daily

# Weekly monitoring (daily + weekly queries)
python -m reddit_monitor monitor --weekly

# One-shot deep scrape for research
python -m reddit_monitor scrape
```

Reports are saved to `data/reports/latest.md`.

---

## Schedule

| Schedule | When | What runs |
|---|---|---|
| Daily | Mon-Fri at 8:00 AM UTC | Daily queries only |
| Weekly | Monday at 9:00 AM UTC | Daily + weekly queries |

To change the schedule, edit `.github/workflows/monitor.yml` and update the `cron` expressions. Use [crontab.guru](https://crontab.guru/) to build cron expressions.

---

## FAQ

**Email not arriving?**
- Check the Actions run log for errors (Actions tab → click the run → click the job)
- Verify all 5 secrets are set correctly (Settings → Secrets)
- For Gmail: make sure you're using an App Password, not your regular password
- Check your spam folder

**How do I add more search queries?**
Add new `[[queries.daily]]` or `[[queries.weekly]]` entries to `config.toml`. Each needs a unique `label`, a `query`, and an optional `subreddit`.

**How do I run it manually?**
Actions tab → Reddit Monitor → Run workflow → choose mode → Run workflow.

**Dashboard not updating?**
Make sure GitHub Pages is enabled (Settings → Pages → main branch, /docs folder). The dashboard updates after each successful Actions run.

**How do I monitor a different brand?**
Edit `config.toml` — change `[brand]`, `[competitors]`, `[subreddits]`, `[keywords]`, and all `[[queries.*]]` sections to match your brand and industry.

---

## License

MIT — see [LICENSE](LICENSE).
