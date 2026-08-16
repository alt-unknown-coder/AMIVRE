"""
Module: research_pipeline.py

Dual-tier web research pipeline optimized for Docker memory and CPU limits.

Tier 1: Search-only snippet retrieval via SearXNG (fast, no browser)
Tier 2: Targeted micro-crawling of only the top 1-2 URLs when deep_scan=True

The pipeline is intentionally defensive: it never allows a deep crawl to starve
Celery workers or exhaust Docker resources. It falls back to the Tier 1 snippets
if the deep crawl fails or exceeds the hard 30s execution limit.
"""

import asyncio
import html
import logging
import re
from typing import Any, Dict, List, Tuple

import httpx
from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig

from app.config import settings

logger = logging.getLogger(__name__)

MAX_SEARCH_RESULTS = 5
MAX_URLS_PER_AGENT = 5
MAX_SNIPPET_CHARS = 1600
GLOBAL_TIMEOUT_SECONDS = 30
CRAWL_TIMEOUT_SECONDS = 15

# Rate limiting and retry settings
SEARXNG_REQUEST_TIMEOUT = 5.0  # Increased from 0.8s to allow server processing
SEARXNG_MAX_RETRIES = 3  # Number of retry attempts
SEARXNG_BACKOFF_FACTOR = 2.0  # Exponential backoff multiplier (increased for rate limits)
SEARXNG_INITIAL_DELAY = 1.0  # Initial delay in seconds (increased)
QUERY_DELAY_SECONDS = 1.0  # Delay between sequential queries (increased to avoid bot detection)
BOT_DETECTION_DELAY = 3.0  # Extra delay after 403/bot detection errors

# User agents to rotate between requests
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0",
]

_user_agent_index = 0


def _get_next_user_agent() -> str:
    """Rotate through user agents to avoid detection."""
    global _user_agent_index
    agent = USER_AGENTS[_user_agent_index % len(USER_AGENTS)]
    _user_agent_index += 1
    return agent


def _safe_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def _search_searxng_query_with_retry(query: str, client: httpx.AsyncClient) -> List[Dict[str, str]]:
    """Query SearXNG with exponential backoff retry logic for handling rate limits and timeouts.
    
    Includes:
    - Rotating user agents to avoid bot detection
    - Proper X-Forwarded-For headers
    - Exponential backoff on 403 errors
    - Extra delays after bot detection
    """
    params = {
        "q": query,
        "format": "json",
        "engines": "google,bing,duckduckgo",
    }
    
    for attempt in range(SEARXNG_MAX_RETRIES):
        try:
            logger.debug("SearXNG request attempt %d/%d for query: %s", attempt + 1, SEARXNG_MAX_RETRIES, query)
            
            # Prepare headers to avoid bot detection
            headers = {
                "User-Agent": _get_next_user_agent(),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "X-Forwarded-For": "127.0.0.1",
                "X-Real-IP": "127.0.0.1",
            }
            
            response = await client.get(
                settings.SEARXNG_URL,
                params=params,
                timeout=SEARXNG_REQUEST_TIMEOUT,
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
            logger.debug("SearXNG request succeeded for query: %s", query)
            
            results: List[Dict[str, str]] = []
            for item in payload.get("results", [])[:MAX_SEARCH_RESULTS]:
                title = _safe_text(item.get("title") or item.get("source") or "Untitled")
                url = _safe_text(item.get("url") or "")
                snippet = _safe_text(item.get("content") or item.get("snippet") or item.get("description") or "")
                if not url:
                    continue
                if len(snippet) > MAX_SNIPPET_CHARS:
                    snippet = snippet[:MAX_SNIPPET_CHARS].rstrip() + "..."
                results.append({"title": title, "url": url, "snippet": snippet})
            return results
            
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            delay = SEARXNG_INITIAL_DELAY * (SEARXNG_BACKOFF_FACTOR ** attempt)
            if attempt < SEARXNG_MAX_RETRIES - 1:
                logger.warning(
                    "SearXNG timeout/connection error for query '%s' (attempt %d/%d). Retrying in %.1fs...",
                    query, attempt + 1, SEARXNG_MAX_RETRIES, delay
                )
                await asyncio.sleep(delay)
            else:
                logger.warning(
                    "SearXNG timeout/connection error for query '%s' after %d attempts: %s",
                    query, SEARXNG_MAX_RETRIES, exc
                )
                return []
                
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 403:
                # 403 often indicates bot detection - use longer backoff
                delay = max(BOT_DETECTION_DELAY, SEARXNG_INITIAL_DELAY * (SEARXNG_BACKOFF_FACTOR ** attempt))
                if attempt < SEARXNG_MAX_RETRIES - 1:
                    logger.warning(
                        "SearXNG 403 Forbidden/Bot Detection for query '%s' (attempt %d/%d). Retrying in %.1fs...",
                        query, attempt + 1, SEARXNG_MAX_RETRIES, delay
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.warning(
                        "SearXNG 403 Forbidden after %d attempts for query '%s'. Bot detection may be blocking requests.",
                        SEARXNG_MAX_RETRIES, query
                    )
                    return []
            else:
                logger.warning(
                    "SearXNG HTTP error for query '%s': %s (status %d)",
                    query, exc, exc.response.status_code
                )
                return []
                
        except Exception as exc:
            logger.warning(
                "SearXNG unexpected error for query '%s': %s",
                query, exc
            )
            return []
    
    return []


async def _search_searxng_query(query: str, client: httpx.AsyncClient) -> List[Dict[str, str]]:
    """Tier 1: Query SearXNG for lightweight search snippets only."""
    return await _search_searxng_query_with_retry(query, client)


def _dedupe_results(results: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    deduped: List[Dict[str, str]] = []
    for item in results:
        url = item.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(item)
    return deduped[:MAX_URLS_PER_AGENT]


def _build_tier1_context(results: List[Dict[str, str]]) -> Tuple[str, List[Dict[str, str]]]:
    if not results:
        return "", []

    parts: List[str] = []
    for item in results:
        title = item.get("title", "Untitled")
        url = item.get("url", "")
        snippet = item.get("snippet", "")
        if not title and not snippet:
            continue
        parts.append(f"### Source URL: {url}\nTitle: {title}\nSnippet: {snippet}")

    context = "\n\n---\n\n".join(parts)
    return context, results


async def _run_tier1_search(queries: List[str], progress_callback=None) -> Tuple[str, List[Dict[str, str]]]:
    """Run a fast SearXNG-only search tier without any browser or Crawl4AI work.
    
    Implements rate limiting with sequential query execution and delays between requests
    to avoid overwhelming the SearXNG server and triggering rate limits and bot detection.
    """
    if not queries:
        return "", []

    if progress_callback:
        progress_callback("Searching web via SearXNG...")

    async with httpx.AsyncClient(follow_redirects=True, limits=httpx.Limits(max_connections=1)) as client:
        # Execute queries sequentially with delays to avoid rate limiting and bot detection
        search_results = []
        for i, query in enumerate(queries):
            result = await _search_searxng_query(query, client)
            search_results.append(result)
            # Add delay between queries except after the last one
            if i < len(queries) - 1:
                logger.debug("Waiting %.1fs before next SearXNG query to avoid rate limiting", QUERY_DELAY_SECONDS)
                await asyncio.sleep(QUERY_DELAY_SECONDS)

    combined: List[Dict[str, str]] = []
    for result in search_results:
        if isinstance(result, list):
            combined.extend(result)

    deduped = _dedupe_results(combined)
    context, raw_data = _build_tier1_context(deduped)
    return context, raw_data


async def _run_deep_micro_crawl(
    urls: List[str],
    progress_callback=None,
) -> str:
    """Tier 2: Deep scan only the top 1-2 critical URLs selected from Tier 1."""
    if not urls:
        return ""

    critical_urls = list(dict.fromkeys(urls))[:2]
    if progress_callback:
        progress_callback(f"Running micro-crawl on {len(critical_urls)} high-priority source(s)...")

    crawl_config = CrawlerRunConfig(
        magic_mode=False,
        scan_full_page=False,
        process_iframes=False,
        cache_mode=CacheMode.ENABLED,
        excluded_tags=["nav", "footer", "header", "script", "style", "svg", "img", "form", "video"],
    )

    markdown_sections: List[str] = []
    semaphore = asyncio.Semaphore(2)

    async def _crawl_one(url: str) -> str:
        async with semaphore:
            try:
                async with AsyncWebCrawler(verbose=False) as crawler:
                    result = await asyncio.wait_for(
                        crawler.arun(url=url, config=crawl_config),
                        timeout=CRAWL_TIMEOUT_SECONDS,
                    )

                if not result or not getattr(result, "success", False):
                    logger.warning("Deep crawl did not succeed for %s: %s", url, getattr(result, "error_message", "unknown error"))
                    return ""

                content = _safe_text(getattr(result, "markdown", ""))
                if not content:
                    return ""
                return f"### Source URL: {url}\n\n{content}"
            except asyncio.TimeoutError:
                logger.warning("Crawl4AI timed out after %ss for %s", CRAWL_TIMEOUT_SECONDS, url)
                return ""
            except Exception as exc:
                logger.warning("Deep crawl failed for %s: %s", url, exc)
                return ""

    results = await asyncio.gather(*[_crawl_one(url) for url in critical_urls], return_exceptions=True)
    for item in results:
        if isinstance(item, str) and item.strip():
            markdown_sections.append(item)

    return "\n\n---\n\n".join(markdown_sections)


async def _run_pipeline_inner(
    queries: List[str],
    deep_scan: bool = False,
    progress_callback=None,
) -> Tuple[str, List[Dict[str, str]]]:
    tier1_context, tier1_results = await _run_tier1_search(queries, progress_callback)
    if not tier1_context.strip():
        return "", []

    if not deep_scan:
        return tier1_context, tier1_results

    try:
        deep_context = await asyncio.wait_for(
            _run_deep_micro_crawl([item.get("url", "") for item in tier1_results if item.get("url")], progress_callback),
            timeout=30,
        )
        if deep_context.strip():
            return deep_context, tier1_results
        return tier1_context, tier1_results
    except asyncio.TimeoutError:
        logger.warning("Deep crawl exceeded the 30s hard timeout; returning Tier 1 snippet fallback.")
        return tier1_context, tier1_results
    except Exception as exc:
        logger.warning("Deep crawl failed; returning Tier 1 snippet fallback: %s", exc)
        return tier1_context, tier1_results


async def run_pipeline(
    queries: List[str],
    deep_scan: bool = False,
    progress_callback=None,
) -> Tuple[str, List[Dict[str, str]]]:
    """Hard timeout wrapper around the full pipeline with tiered fallback logic."""
    if not queries:
        return "", []

    try:
        return await asyncio.wait_for(
            _run_pipeline_inner(queries, deep_scan=deep_scan, progress_callback=progress_callback),
            timeout=GLOBAL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("Research pipeline exceeded the 30s global timeout; returning empty context to keep the worker alive.")
        return "", []
    except Exception as exc:
        logger.warning("Research pipeline failed globally and returned empty fallback context: %s", exc)
        return "", []
