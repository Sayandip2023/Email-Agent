"""
AI News Agent — True ReAct agent with planning, self-correction, and evaluation.

Key fix: the orchestrator accumulates articles directly from search_and_extract
tool results. The agent cannot "save" articles it invented — it can only add
articles that came back from an actual search tool call.

Install: pip install google-genai requests
"""

import os
import json
import re
import time
import requests as http
from datetime import datetime
from dotenv import load_dotenv

from google import genai
from google.genai import types

from email_sender import send_digest_email

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL        = "gemini-2.5-flash"
TODAY        = datetime.now().strftime("%B %d, %Y")
MAX_ACT_LOOPS = 40

# ─────────────────────────────────────────────────────────────────────────────
# Rate-limit-aware API wrapper
# Free tier: 5 req/min for gemini-2.5-flash. Retries on 429 with backoff.
# ─────────────────────────────────────────────────────────────────────────────

def gemini_call(**kwargs):
    """Call client.models.generate_content with automatic 429 retry/backoff."""
    wait = 15       # initial wait seconds after first 429
    max_wait = 120  # cap at 2 minutes
    for attempt in range(8):
        try:
            return gemini_call(**kwargs)
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                print(f"    [rate limit] waiting {wait}s (attempt {attempt+1})...")
                time.sleep(wait)
                wait = min(wait * 2, max_wait)
            else:
                raise
    raise RuntimeError("Exceeded retry budget for Gemini API calls.")


# ─────────────────────────────────────────────────────────────────────────────
# URL resolver
# ─────────────────────────────────────────────────────────────────────────────

_url_cache: dict[str, str] = {}

def resolve_url(url: str) -> tuple[str, str]:
    if not url:
        return "", ""
    if url in _url_cache:
        resolved = _url_cache[url]
    elif "vertexaisearch" in url or "googleapis" in url:
        try:
            r = http.head(url, allow_redirects=True, timeout=6,
                          headers={"User-Agent": "Mozilla/5.0"})
            resolved = r.url
        except Exception:
            try:
                r = http.get(url, allow_redirects=True, timeout=6, stream=True,
                             headers={"User-Agent": "Mozilla/5.0"})
                r.close()
                resolved = r.url
            except Exception:
                resolved = url
        _url_cache[url] = resolved
    else:
        resolved = url
    domain = resolved.split("/")[2].replace("www.", "") if "://" in resolved else ""
    return resolved, domain

def resolve_chunks(response) -> list[dict]:
    out = []
    try:
        for chunk in response.candidates[0].grounding_metadata.grounding_chunks:
            if chunk.web and chunk.web.uri:
                url, domain = resolve_url(chunk.web.uri)
                out.append({"url": url, "domain": domain or chunk.web.title or ""})
    except (IndexError, AttributeError):
        pass
    return out

# ─────────────────────────────────────────────────────────────────────────────
# JSON helpers
# ─────────────────────────────────────────────────────────────────────────────

def extract_json(text: str):
    for s in [text.strip(), re.sub(r"```(?:json)?", "", text).strip().rstrip("`")]:
        try:
            p = json.loads(s)
            return p if isinstance(p, list) else [p]
        except json.JSONDecodeError:
            pass
    m = re.search(r"\[.*?\]", text, re.DOTALL)
    if m:
        try:
            p = json.loads(m.group(0))
            return p if isinstance(p, list) else [p]
        except json.JSONDecodeError:
            pass
    return None

def dedupe(articles: list[dict]) -> list[dict]:
    seen, out = set(), []
    for a in articles:
        key = re.sub(r"\W+", "", a.get("title", "")).lower()[:60]
        if key and key not in seen:
            seen.add(key)
            out.append(a)
    return out

# ─────────────────────────────────────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────────────────────────────────────

# Accumulated by the orchestrator — NOT written by the agent directly
_collected: list[dict] = []

def search_and_extract(query: str, category: str) -> str:
    """Search Google for recent AI news and return structured articles.

    Performs a live Google Search and returns a JSON object with the articles
    found. You MUST read the returned articles field before deciding next steps.
    The articles are NOT saved automatically — you must call add_to_digest for
    each article you want to keep after reviewing the results.

    Args:
        query: A specific, targeted search query string.
        category: One of: LLM / Model Releases, AI Tools & Frameworks,
                  Research Papers, Industry News.
    """
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
    )
    prompt = f"""Search for: {query}

Today is {TODAY}. Find 2-3 genuinely recent (last 4 weeks) results.
Return ONLY a raw JSON array, no markdown fences, no preamble.
Each object must have exactly these keys:
  "title": article/paper title
  "url": direct source URL or empty string
  "summary": 3-4 sentences covering what it is, what changed, and concrete numbers/details
  "why_interesting": one sentence of practical significance for a developer

Do not fabricate titles or URLs. If no genuinely recent results exist, return [].
"""
    try:
        response = gemini_call(
            model=MODEL, contents=prompt, config=config
        )
        raw = response.text or ""
        articles = extract_json(raw)
        if articles is None:
            return json.dumps({"status": "parse_error", "raw_preview": raw[:300],
                               "instruction": "JSON parsing failed. Retry with a different query."})
        chunks = resolve_chunks(response)
        for i, a in enumerate(articles):
            a["category"] = category
            url = a.get("url", "")
            if url and ("vertexaisearch" in url or "googleapis" in url):
                a["url"], _ = resolve_url(url)
            if not a.get("url") and i < len(chunks):
                a["url"] = chunks[i]["url"]
            a["sources"] = chunks
        return json.dumps({
            "status": "ok",
            "count": len(articles),
            "articles": articles,
            "instruction": (
                f"Found {len(articles)} articles. Review each one. "
                "Call add_to_digest for articles worth keeping. "
                "Call evaluate_article first if unsure about quality."
            )
        })
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


def add_to_digest(title: str, url: str, summary: str,
                  why_interesting: str, category: str) -> str:
    """Add a single reviewed article to the digest.

    Only call this after you have read the article from search_and_extract
    results and decided it is worth keeping. Do NOT invent article details —
    only pass values that came from an actual search result.

    Args:
        title: The article title exactly as returned by search_and_extract.
        url: The article URL exactly as returned by search_and_extract.
        summary: The article summary exactly as returned by search_and_extract.
        why_interesting: The why_interesting field from search_and_extract.
        category: The category this article belongs to.
    """
    if not title or not summary:
        return json.dumps({"status": "error", "message": "title and summary are required"})
    article = {
        "title":          title,
        "url":            url,
        "summary":        summary,
        "why_interesting": why_interesting,
        "category":       category,
        "sources":        [],
    }
    _collected.append(article)
    return json.dumps({
        "status": "added",
        "total_so_far": len(_collected),
        "instruction": (
            f"Article added. You now have {len(_collected)} articles. "
            "Keep searching until you have 8-12 total, then call finish_digest."
        )
    })


def evaluate_article(title: str, summary: str, why_interesting: str) -> str:
    """Evaluate whether an article is worth including. Use when quality is uncertain.

    Args:
        title: The article title.
        summary: The article summary.
        why_interesting: The why_interesting field.
    """
    prompt = f"""You are a strict editor for an AI research digest read by senior engineers.

Evaluate this article:
Title: {title}
Summary: {summary}
Why interesting: {why_interesting}

Reject if ANY of:
- It is marketing or PR fluff with no technical substance
- It is older than 4 weeks from today ({TODAY})
- The summary is vague with no concrete numbers, techniques, or outcomes
- It duplicates something most developers already know

Return ONLY this exact JSON: {{"verdict": "accept", "reason": "one sentence"}}
or: {{"verdict": "reject", "reason": "one sentence"}}"""
    try:
        resp = gemini_call(model=MODEL, contents=prompt)
        raw = resp.text or ""
        result = extract_json(raw)
        if result:
            return json.dumps(result[0])
        # try direct dict parse
        try:
            return json.dumps(json.loads(raw.strip()))
        except Exception:
            return json.dumps({"verdict": "accept", "reason": "evaluation inconclusive"})
    except Exception as e:
        return json.dumps({"verdict": "accept", "reason": f"eval error: {e}"})


def find_source_url(title: str, description: str) -> str:
    """Search for the source URL of a specific article when the URL is missing.

    Args:
        title: The exact article or paper title.
        description: A short description to help locate the right source.
    """
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
    )
    prompt = f'Find the original source URL for: "{title}". Description: {description}. Return only the URL, nothing else.'
    try:
        response = gemini_call(
            model=MODEL, contents=prompt, config=config
        )
        raw = (response.text or "").strip()
        chunks = resolve_chunks(response)
        url_match = re.search(r'https?://\S+', raw)
        if url_match:
            url, _ = resolve_url(url_match.group(0).rstrip(".,)"))
            return json.dumps({"url": url})
        if chunks:
            return json.dumps({"url": chunks[0]["url"]})
        return json.dumps({"url": ""})
    except Exception as e:
        return json.dumps({"url": "", "error": str(e)})


def finish_digest() -> str:
    """Signal that curation is complete. Call only when you have 8-12 articles.

    No arguments needed. The orchestrator will send the email with whatever
    has been added via add_to_digest so far.
    """
    return json.dumps({
        "status": "done",
        "total": len(_collected),
        "message": f"Digest finalised with {len(_collected)} articles. Email will be sent."
    })


TOOL_MAP = {
    "search_and_extract": search_and_extract,
    "add_to_digest":      add_to_digest,
    "evaluate_article":   evaluate_article,
    "find_source_url":    find_source_url,
    "finish_digest":      finish_digest,
}

# ─────────────────────────────────────────────────────────────────────────────
# System prompt
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""You are an autonomous AI research analyst. Today is {TODAY}.

Your goal: curate 8-12 high-quality recent AI developments across four categories:
  1. LLM / Model Releases
  2. AI Tools & Frameworks
  3. Research Papers
  4. Industry News

Your tools and the EXACT workflow you must follow:

STEP 1 — SEARCH: Call search_and_extract(query, category).
  - Choose your own specific queries. Run 2-3 searches per category minimum.
  - WAIT for the tool result before doing anything else.

STEP 2 — REVIEW: Read the "articles" array in the tool result carefully.
  - Each article has title, url, summary, why_interesting.
  - These are real search results. Do not skip reading them.

STEP 3 — EVALUATE (optional): If an article looks like marketing fluff or is vague,
  call evaluate_article before deciding. Otherwise use your judgment.

STEP 4 — ADD: For each article you want to keep, call add_to_digest with the exact
  values from the search result. Do not modify or invent values.
  - If url is empty, call find_source_url first.

STEP 5 — REPEAT steps 1-4 for each category until you have 8-12 articles total.

STEP 6 — FINISH: Call finish_digest() once and stop.

Critical rules:
- You MUST read search tool results before adding articles. Never add articles
  from your own knowledge — only from search_and_extract results.
- Do not repeat the same query twice.
- If a search returns parse_error or 0 results, retry with a different query.
- Aim for 2-3 articles per category minimum.
"""

# ─────────────────────────────────────────────────────────────────────────────
# ReAct loop
# ─────────────────────────────────────────────────────────────────────────────

def run_react_loop(recipient_email: str):
    print(f"\nAI News Agent (ReAct)  |  {TODAY}  |  {MODEL}\n")

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[search_and_extract, add_to_digest, evaluate_article,
               find_source_url, finish_digest],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    contents: list[types.Content] = [
        types.Content(role="user", parts=[types.Part(text=(
            f"Today is {TODAY}. Begin curating the AI digest. "
            f"Start with LLM / Model Releases, search first, read the results, "
            f"then add the good articles. Then move to the next category."
        ))])
    ]

    tool_calls_made  = 0
    finish_called    = False
    nudges_sent      = 0
    MAX_NUDGES       = 3

    for step in range(MAX_ACT_LOOPS):
        response = gemini_call(
            model=MODEL, contents=contents, config=config
        )
        contents.append(response.candidates[0].content)

        fn_calls = response.function_calls
        if not fn_calls:
            text = response.text or ""
            print(f"\n[Step {step+1}] Agent: {text[:180]}...")
            if finish_called:
                break
            if nudges_sent < MAX_NUDGES:
                nudges_sent += 1
                nudge = (
                    f"You have {len(_collected)} articles so far. "
                    "Keep searching and adding until you reach 8-12, then call finish_digest."
                    if _collected else
                    "You haven't added any articles yet. Call search_and_extract now, "
                    "then read the result and call add_to_digest for each good article."
                )
                print(f"  [Nudge {nudges_sent}] {nudge[:80]}")
                contents.append(types.Content(
                    role="user", parts=[types.Part(text=nudge)]
                ))
            continue

        tool_response_parts: list[types.Part] = []
        for fn in fn_calls:
            name = fn.name
            args = dict(fn.args) if fn.args else {}
            tool_calls_made += 1

            if name == "search_and_extract":
                print(f"  [{step+1}] SEARCH   → \"{args.get('query','')[:65]}\"  [{args.get('category','')}]")
            elif name == "add_to_digest":
                print(f"  [{step+1}] ADD      → \"{args.get('title','')[:65]}\"")
            elif name == "evaluate_article":
                print(f"  [{step+1}] EVALUATE → \"{args.get('title','')[:65]}\"")
            elif name == "find_source_url":
                print(f"  [{step+1}] FIND URL → \"{args.get('title','')[:65]}\"")
            elif name == "finish_digest":
                finish_called = True
                print(f"  [{step+1}] FINISH   → {len(_collected)} articles collected")

            result = TOOL_MAP[name](**args) if name in TOOL_MAP else json.dumps({"error": f"Unknown tool: {name}"})

            tool_response_parts.append(
                types.Part.from_function_response(name=name, response={"result": result})
            )

        contents.append(types.Content(role="user", parts=tool_response_parts))

        if finish_called:
            break

    print(f"\nTotal tool calls : {tool_calls_made}")
    print(f"Articles collected: {len(_collected)}")

    if not _collected:
        print("No articles collected. Check GEMINI_API_KEY and network.")
        return

    final = dedupe(_collected)
    print(f"After dedup      : {len(final)} articles. Sending email...")
    send_digest_email(recipient_email, final)
    print("Email sent.")


if __name__ == "__main__":
    load_dotenv()
    recipient = os.getenv("RECIPIENT_EMAIL") or input("Gmail address: ").strip()
    run_react_loop(recipient)