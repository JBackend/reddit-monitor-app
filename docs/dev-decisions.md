# Development Decisions Log

## Context

Reddit Monitor was running entirely on Vercel — frontend at `redditmonitor.jaskaranbedi.com`, API as a serverless function at `/api/analyze`. Users hitting the endpoint were getting "Reddit blocked" errors because PullPush.io rate-limits under multi-user load, and Vercel's 60-second function timeout made resilience (retries, backoff) nearly impossible to implement.

---

## Decision 1: Split Frontend and API

**Problem:** Vercel serverless functions have a hard 60-second timeout. The pipeline (PullPush search + comment fetching + Claude analysis) routinely takes 30-60s, leaving zero room for retries or backoff.

**Decision:** Keep the frontend on Vercel (static hosting, free, already configured with custom domain). Move the API to a separate server with no timeout constraints.

**Rationale:** The frontend is just static HTML/CSS/JS — Vercel is perfect for that. The API needs a long-running process, which serverless can't provide.

---

## Decision 2: Hosting Platform — Fly.io

**Considered:**

| Platform | Cost | Pros | Cons |
|----------|------|------|------|
| **Fly.io** | ~$3-5/month | Simple deploy, no timeout, persistent process, Docker support | Not free |
| **Render (free)** | $0 | Drop-in Dockerfile deploy, no timeout | Spins down after 15 min (cold start ~30s), limited to 1 free web service |
| **Google Cloud Run** | $0 (free tier) | 2M req/month free, 60-min timeout | More setup (gcloud CLI, IAM), serverless (no persistent cache) |
| **Async job pattern on Vercel** | $0 | No new hosting | High complexity (job queue, polling, external state store) |

**Path taken:**
1. First chose **Render free tier** because it was the simplest free option
2. Discovered a pre-warming trick (see Decision 4) that would hide cold starts
3. Hit a blocker: Render free tier limits you to **1 web service**, and an existing project already occupies that slot
4. Pivoted to **Fly.io** (~$3/month) as the lowest-friction paid option

**Final choice:** Fly.io, `shared-cpu-1x` with 512MB RAM, Toronto (yyz) region.

---

## Decision 3: Server Architecture

**Decision:** Flask + gunicorn, 1 worker + 2 threads.

**Rationale:**
- 1 worker (not multiple) so that the in-memory cache dict is shared across all requests
- 2 threads allow concurrent requests without blocking on I/O
- 512MB Fly.io machine handles this comfortably (~150MB actual usage)
- gunicorn timeout set to 120s — won't kill long Claude responses

---

## Decision 4: Pre-warm API on Page Load

**Insight from user:** Users spend 30-60+ seconds filling in the form (brand, aliases, competitors, keywords, subreddits) before hitting "Analyze". That's more than enough time to wake up a sleeping server.

**Implementation:** Single line of JavaScript fires on page load:
```javascript
fetch('https://redditmonitor-api.fly.dev/health').catch(() => {});
```

**Why this matters:** This was originally discovered when evaluating Render's free tier (which spins down after 15 min of inactivity). The cold start (~30s) would be completely hidden behind natural user input time. Although we moved to Fly.io (which has `auto_start_machines`), the pre-warm is still useful — it ensures the machine is fully warm before the actual request hits.

---

## Decision 5: In-Memory Cache

**Decision:** Cache successful responses in a Python dict with threading lock.

**Specs:**
- TTL: 1 hour
- Max entries: 500 (expired entries evicted when cap is hit)
- Cache key: SHA-256 of normalized input (brand, aliases, competitors, keywords, subreddits — all lowercased, sorted, deterministic JSON)
- Only successful responses (with a report) are cached. Errors are NOT cached.
- Response includes `"cached": true/false` flag

**Why not Redis/external store:** Fly.io runs a persistent process. The dict survives across requests. No need for external dependencies, network latency, or additional cost.

**Trade-off:** Cache is lost on deploy or machine restart. Acceptable — cache is a performance optimization, not a correctness requirement.

---

## Decision 6: Server-Side Rate Limiting

**Decision:** 10 requests per IP per hour, enforced in-memory.

**Implementation:**
- IP extracted from `X-Forwarded-For` header (Fly.io sets this)
- IPs are hashed with SHA-256 (don't store raw IPs)
- Returns HTTP 429 with clear message when exceeded
- Separate from the client-side 2/day localStorage limit (which is easily bypassed)

---

## Decision 7: PullPush.io Retry Logic

**Decision:** 3 total attempts (1 original + 2 retries) with exponential backoff (1s, 2s).

**Rules:**
- Retry on 429 (rate limit) and 5xx (server errors)
- Do NOT retry on 400/404 (client errors — retrying won't help)
- No circuit breaker needed — Fly.io has no timeout to fight

---

## Decision 8: Reduce PullPush API Calls

**Changes:**
- `TOP_POSTS_FOR_COMMENTS`: 5 → 3 (saves 2 comment-fetching calls)
- Subreddit-specific searches: `subreddits[:3]` → `subreddits[:2]` (saves 1 call)
- Total calls per request: ~12 → ~9

**Rationale:** Fewer calls = less chance of hitting PullPush rate limits, faster total execution. The marginal value of the 4th and 5th comment set and 3rd subreddit search is low.

---

## Decision 9: Claude Timeout Reduction

**Change:** `timeout=120` → `timeout=90` for the Claude API call.

**Rationale:** 90 seconds is plenty for Claude to generate the report. On Fly.io there's no hard deadline, but we don't want requests hanging indefinitely if Claude is unresponsive.

---

## Decision 10: CORS Policy

**Decision:** Lock CORS to `https://redditmonitor.jaskaranbedi.com` only (not `*`).

**Rationale:** The old Vercel function used `Access-Control-Allow-Origin: *` because it was same-origin. Now that the API is on a different domain, we restrict it to only the actual frontend to prevent unauthorized usage from other sites.

---

## Decision 11: Cached Responses Don't Count Toward Daily Limit

**Decision:** The frontend's 2-runs-per-day localStorage counter only increments for fresh (non-cached) responses.

**Rationale:** If someone re-runs the exact same query, they get a cached result that costs nothing (no PullPush calls, no Claude API call). No reason to penalize them for it.

---

## Decision 12: Keep Vercel Handler Intact

**Decision:** The `handler` class in `api/analyze.py` (Vercel serverless entry point) is kept as-is.

**Rationale:** The frontend now points to Fly.io, so the Vercel endpoint won't receive traffic. But keeping the code means the Vercel deployment still technically works. The old endpoint is disabled by removing `ANTHROPIC_API_KEY` from Vercel's environment variables (returns 502), not by deleting code.

---

## Post-Migration Checklist

- [ ] Create Fly.io account and install CLI
- [ ] `fly launch` + `fly secrets set ANTHROPIC_API_KEY=...` + `fly deploy`
- [ ] Verify `curl https://redditmonitor-api.fly.dev/health` returns `{"status": "ok"}`
- [ ] Test full pipeline via the live frontend
- [ ] Verify cache works (same request twice → second is instant with `cached: true`)
- [ ] Verify rate limiting (11th rapid request → HTTP 429)
- [ ] Remove `ANTHROPIC_API_KEY` from Vercel dashboard
- [ ] Set monthly spending cap on Anthropic account
- [ ] Check `fly logs` for request logging
