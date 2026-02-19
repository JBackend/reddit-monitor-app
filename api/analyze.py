"""
Vercel Serverless Function: Reddit Brand Intelligence Analyzer

Receives POST JSON with brand info, searches Reddit via PullPush.io,
analyzes with Claude AI, and returns a structured intelligence report.

Standalone function — no external package imports.
"""

import json
import os
import urllib.request
import urllib.parse
import urllib.error
from http.server import BaseHTTPRequestHandler

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PULLPUSH_BASE = "https://api.pullpush.io"
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL = "claude-sonnet-4-20250514"
CLAUDE_MAX_TOKENS = 8000
ANTHROPIC_VERSION = "2023-06-01"
TOP_POSTS_FOR_COMMENTS = 5
MAX_SEARCH_RESULTS = 25

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Content-Type": "application/json",
}

# ---------------------------------------------------------------------------
# PullPush.io helpers
# ---------------------------------------------------------------------------


def _pullpush_get(endpoint, params):
    """GET request to PullPush.io API. Returns parsed JSON or raises."""
    query = urllib.parse.urlencode(params)
    url = f"{PULLPUSH_BASE}{endpoint}?{query}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "RedditMonitor/1.0",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(f"PullPush {endpoint} failed (HTTP {exc.code}): {body[:300]}")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"PullPush request failed: {exc.reason}")


# ---------------------------------------------------------------------------
# Reddit search via PullPush.io
# ---------------------------------------------------------------------------


def generate_search_queries(brand, aliases, competitors, keywords):
    """Auto-generate search queries from the provided brand info."""
    queries = []

    queries.append(brand)

    if keywords:
        queries.append(f"{brand} {keywords[0]}")

    if competitors:
        queries.append(f"{brand} vs {' '.join(competitors[:2])}")

    if keywords and len(keywords) >= 2:
        queries.append(f"{keywords[0]} {keywords[1]} recommendation")
    elif keywords:
        queries.append(f"{keywords[0]} recommendation")

    if competitors and keywords:
        queries.append(f"{competitors[0]} {keywords[0]}")

    # Deduplicate
    seen = set()
    unique = []
    for q in queries:
        q_lower = q.lower()
        if q_lower not in seen:
            seen.add(q_lower)
            unique.append(q)

    return unique[:4]


def search_reddit(queries, subreddits):
    """Search Reddit via PullPush.io for each query. Returns (posts, errors)."""
    all_posts = []
    errors = []

    for query in queries:
        try:
            result = _pullpush_get("/reddit/search/submission/", {
                "q": query,
                "size": MAX_SEARCH_RESULTS,
                "sort_type": "score",
                "sort": "desc",
            })
            posts = result.get("data", [])
            for post in posts:
                post["_matched_query"] = query
                all_posts.append(post)
        except RuntimeError as e:
            errors.append(str(e))

    # If subreddits given, search each one with the primary query
    if subreddits and queries:
        for sr in subreddits[:3]:
            try:
                result = _pullpush_get("/reddit/search/submission/", {
                    "q": queries[0],
                    "subreddit": sr,
                    "size": MAX_SEARCH_RESULTS,
                    "sort_type": "score",
                    "sort": "desc",
                })
                posts = result.get("data", [])
                for post in posts:
                    post["_matched_query"] = f"{queries[0]} (r/{sr})"
                    all_posts.append(post)
            except RuntimeError:
                pass

    return all_posts, errors


def fetch_comments_for_posts(posts):
    """Fetch comments for top posts via PullPush.io. Adds '_comments' to each."""
    for post in posts:
        post_id = post.get("id", "")
        if not post_id:
            post["_comments"] = []
            continue

        # Strip any t3_ prefix
        if post_id.startswith("t3_"):
            post_id = post_id[3:]

        try:
            result = _pullpush_get("/reddit/search/comment/", {
                "link_id": post_id,
                "size": 15,
                "sort": "score",
            })
            raw_comments = result.get("data", [])
            comments = []
            for c in raw_comments:
                body = c.get("body", "")
                if body and body not in ("[deleted]", "[removed]"):
                    comments.append({
                        "author": c.get("author", "[deleted]"),
                        "body": body[:800],
                        "score": c.get("score", 0),
                    })
            post["_comments"] = comments[:15]
        except RuntimeError:
            post["_comments"] = []

    return posts


# ---------------------------------------------------------------------------
# Post processing helpers
# ---------------------------------------------------------------------------


def deduplicate_posts(posts):
    """Remove duplicate posts by ID."""
    seen_ids = set()
    unique = []
    for post in posts:
        post_id = post.get("id", "")
        if post_id.startswith("t3_"):
            post_id = post_id[3:]
        if post_id and post_id not in seen_ids:
            seen_ids.add(post_id)
            unique.append(post)
    return unique


def filter_relevant_posts(posts, brand, aliases, competitors, keywords, subreddits):
    """Filter posts by subreddit match or keyword match."""
    all_terms = set()
    for term in [brand] + (aliases or []) + (competitors or []) + (keywords or []):
        all_terms.add(term.lower())

    subreddit_set = set(s.lower() for s in (subreddits or []))
    relevant = []

    for post in posts:
        title = (post.get("title") or "").lower()
        selftext = (post.get("selftext") or "").lower()
        post_sub = (post.get("subreddit") or "").lower()
        # Handle subreddit_prefixed format (r/subreddit)
        if not post_sub and post.get("subreddit_prefixed"):
            post_sub = post["subreddit_prefixed"].replace("r/", "").lower()
        combined_text = f"{title} {selftext}"

        in_subreddit = post_sub in subreddit_set if subreddit_set else False
        has_term = any(term in combined_text for term in all_terms)

        if in_subreddit or has_term:
            relevant.append(post)

    return relevant


def classify_priority(post, brand, aliases, competitors):
    """Classify post priority: URGENT, HIGH, or MEDIUM."""
    title = (post.get("title") or "").lower()
    selftext = (post.get("selftext") or "").lower()
    combined = f"{title} {selftext}"

    brand_terms = set(t.lower() for t in [brand] + (aliases or []))
    competitor_terms = set(t.lower() for t in (competitors or []))

    if any(term in combined for term in brand_terms):
        return "URGENT"
    elif any(term in combined for term in competitor_terms):
        return "HIGH"
    return "MEDIUM"


# ---------------------------------------------------------------------------
# Claude AI analysis
# ---------------------------------------------------------------------------


def build_analysis_prompt(brand, aliases, competitors, keywords, posts):
    """Build the Claude prompt with all collected post data."""
    posts_text = ""
    for i, post in enumerate(posts, 1):
        priority = post.get("_priority", "MEDIUM")
        title = post.get("title", "No title")
        selftext = (post.get("selftext") or "")[:600]
        subreddit = post.get("subreddit") or (post.get("subreddit_prefixed", "").replace("r/", ""))
        score = post.get("score", 0)
        num_comments = post.get("num_comments", 0)
        permalink = post.get("permalink", "")

        posts_text += f"\n--- Post {i} [{priority}] ---\n"
        posts_text += f"Subreddit: r/{subreddit}\n"
        posts_text += f"Title: {title}\n"
        posts_text += f"Score: {score} | Comments: {num_comments}\n"
        if permalink:
            link = permalink if permalink.startswith("http") else f"https://reddit.com{permalink}"
            posts_text += f"URL: {link}\n"
        if selftext:
            posts_text += f"Text: {selftext}\n"

        comments = post.get("_comments", [])
        if comments:
            posts_text += "Top Comments:\n"
            for j, c in enumerate(comments[:10], 1):
                posts_text += f"  {j}. [{c['score']} pts] u/{c['author']}: {c['body'][:300]}\n"

    aliases_str = ", ".join(aliases) if aliases else "none"
    competitors_str = ", ".join(competitors) if competitors else "none"
    keywords_str = ", ".join(keywords) if keywords else "none"

    prompt = f"""You are a brand intelligence analyst. Analyze the following Reddit posts and comments about "{brand}" and its competitive landscape.

BRAND: {brand}
ALIASES: {aliases_str}
COMPETITORS: {competitors_str}
KEYWORDS: {keywords_str}

REDDIT DATA:
{posts_text}

Produce a structured Markdown intelligence report with ALL of the following sections. Use tables where indicated. Be specific — cite actual Reddit quotes and data points.

# Brand Intelligence Report: {brand}

## 1. Brand Perception
Analyze how the brand is discussed on Reddit. Include a table:
| Sentiment | Quote | Subreddit | Context |
|-----------|-------|-----------|---------|

## 2. Competitive Landscape
Compare the brand against competitors mentioned in Reddit discussions.
| Competitor | Mentions | Perceived Strengths | Perceived Weaknesses | Market Position |
|------------|----------|---------------------|----------------------|-----------------|

## 3. Market Insights
Identify market trends and buyer needs from the discussions.
| Buyer Need | Evidence (Quote/Reference) | Implication for {brand} |
|------------|---------------------------|------------------------|

## 4. Pain Points & Opportunities
| Pain Point | Frequency | Severity | Opportunity for {brand} |
|------------|-----------|----------|------------------------|

## 5. Recommendation Patterns
How do Reddit users recommend solutions in this space?
| Situation | Recommended Solution | Reason Given |
|-----------|---------------------|--------------|

## 6. Key Threats
| Threat | Source | Severity | Mitigation Strategy |
|--------|--------|----------|---------------------|

## 7. Actionable Recommendations
| Area | Recommended Action | Rationale |
|------|-------------------|-----------|

## 8. Quote Bank
The most valuable direct quotes from Reddit for marketing and product teams.
| Quote | Source (Subreddit/User) | Strategic Insight |
|-------|------------------------|-------------------|

## 9. Executive Summary
Provide 4-5 bullet points summarizing the most critical findings.

IMPORTANT:
- Fill every table with real data from the posts above. If data is limited for a section, note that explicitly but still provide what you can.
- Use actual Reddit quotes where possible (in quotation marks).
- Be direct and actionable — this report goes to decision makers.
- If no data is found for the brand specifically, focus on the competitive and market landscape."""

    return prompt


def call_claude_api(prompt, api_key):
    """Call the Claude API with the analysis prompt."""
    payload = json.dumps({
        "model": CLAUDE_MODEL,
        "max_tokens": CLAUDE_MAX_TOKENS,
        "messages": [
            {"role": "user", "content": prompt}
        ],
    }).encode("utf-8")

    req = urllib.request.Request(
        CLAUDE_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            content_blocks = result.get("content", [])
            text_parts = []
            for block in content_blocks:
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            report = "\n".join(text_parts)

            usage = result.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            cost = (input_tokens * 3.0 / 1_000_000) + (output_tokens * 15.0 / 1_000_000)

            return report, round(cost, 4)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(f"Claude API returned HTTP {exc.code}: {body[:500]}")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Claude API request failed: {exc.reason}")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run_pipeline(body):
    """Execute the full scrape-analyze pipeline. Returns (result_dict, status_code)."""

    # --- 1. Validate input ---
    brand = (body.get("brand") or "").strip()
    if not brand:
        return {"error": "The 'brand' field is required."}, 400

    aliases = body.get("aliases") or []
    competitors = body.get("competitors") or []
    keywords = body.get("keywords") or []
    subreddits = body.get("subreddits") or []

    has_optional = aliases or competitors or keywords or subreddits
    if not has_optional:
        return {
            "error": "At least one of 'aliases', 'competitors', 'keywords', or 'subreddits' must be provided."
        }, 400

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY environment variable is not set."}, 502

    # --- 2. Generate search queries ---
    queries = generate_search_queries(brand, aliases, competitors, keywords)

    # --- 3. Search Reddit via PullPush.io ---
    search_errors = []
    try:
        raw_posts, search_errors = search_reddit(queries, subreddits)
    except Exception as exc:
        return {"error": f"Reddit search failed: {str(exc)}"}, 502

    if not raw_posts:
        detail = f" Errors: {'; '.join(search_errors[:3])}" if search_errors else ""
        return {
            "error": f"No Reddit posts found for the given search criteria. Try broader keywords or different subreddits.{detail}"
        }, 400

    # --- 4. Deduplicate ---
    unique_posts = deduplicate_posts(raw_posts)
    total_found = len(unique_posts)

    # --- 5. Filter relevant ---
    relevant_posts = filter_relevant_posts(
        unique_posts, brand, aliases, competitors, keywords, subreddits
    )

    if not relevant_posts:
        relevant_posts = unique_posts

    # --- 6. Classify priority ---
    for post in relevant_posts:
        post["_priority"] = classify_priority(post, brand, aliases, competitors)

    priority_order = {"URGENT": 0, "HIGH": 1, "MEDIUM": 2}
    relevant_posts.sort(
        key=lambda p: (
            priority_order.get(p.get("_priority", "MEDIUM"), 2),
            -(p.get("score", 0) + p.get("num_comments", 0)),
        )
    )

    # --- 7. Fetch comments for top posts ---
    top_posts = relevant_posts[:TOP_POSTS_FOR_COMMENTS]
    try:
        top_posts = fetch_comments_for_posts(top_posts)
    except Exception:
        pass

    analyzed_posts = top_posts + relevant_posts[TOP_POSTS_FOR_COMMENTS:]

    # --- 8-9. Build prompt and call Claude ---
    prompt = build_analysis_prompt(brand, aliases, competitors, keywords, analyzed_posts)

    try:
        report, cost_estimate = call_claude_api(prompt, api_key)
    except RuntimeError as exc:
        return {"error": f"Claude API error: {str(exc)}"}, 502

    # --- 10. Return report ---
    return {
        "report": report,
        "stats": {
            "posts_found": total_found,
            "posts_analyzed": len(analyzed_posts),
            "cost_estimate": cost_estimate,
        },
    }, 200


# ---------------------------------------------------------------------------
# Vercel handler
# ---------------------------------------------------------------------------


class handler(BaseHTTPRequestHandler):
    """Vercel serverless function handler."""

    def _send_response(self, status_code, body):
        self.send_response(status_code)
        for key, value in CORS_HEADERS.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))

    def do_OPTIONS(self):
        self._send_response(200, {})

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self._send_response(400, {"error": "Empty request body."})
                return

            raw_body = self.rfile.read(content_length)
            try:
                body = json.loads(raw_body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._send_response(400, {"error": "Invalid JSON in request body."})
                return

            if not isinstance(body, dict):
                self._send_response(400, {"error": "Request body must be a JSON object."})
                return

            result, status_code = run_pipeline(body)
            self._send_response(status_code, result)

        except Exception as exc:
            self._send_response(502, {"error": f"Internal error: {str(exc)}"})
