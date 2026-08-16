"""
Production-grade free search module for AMIVRE.
This module is the canonical implementation for domain-agnostic search discovery.
Legacy imports remain supported via app.scrapers.free_search.
"""

import asyncio
import logging
from typing import List
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class DuckDuckGoSearch:
    """Free URL search using DuckDuckGo HTML fallback."""

    @staticmethod
    def _clean_url(raw_url: str) -> str:
        if not raw_url:
            return ""
        try:
            parsed = urlparse(raw_url)
            if parsed.scheme and parsed.netloc:
                return raw_url
            if raw_url.startswith("//"):
                return "https:" + raw_url
            if raw_url.startswith("/"):
                return "https://duckduckgo.com" + raw_url
            return raw_url
        except Exception:
            return raw_url

    @staticmethod
    def _normalize_url(url: str) -> str:
        cleaned = DuckDuckGoSearch._clean_url(url)
        if not cleaned:
            return ""
        parsed = urlparse(cleaned)
        if parsed.netloc == "duckduckgo.com" and parsed.path == "/l/":
            qs = parse_qs(parsed.query)
            target = qs.get("uddg", [""])[0]
            if target:
                return target
        return cleaned

    async def _search_html(self, query: str, max_results: int = 5) -> List[str]:
        urls: List[str] = []
        seen = set()
        try:
            async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "Mozilla/5.0"}) as client:
                response = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    follow_redirects=True,
                )
                if response.status_code != 200:
                    return urls

                soup = BeautifulSoup(response.text, "html.parser")
                for anchor in soup.select("a.result-link, a.result__a")[: max_results * 4]:
                    href = anchor.get("href")
                    if not href:
                        continue
                    normalized = self._normalize_url(href)
                    if normalized and normalized not in seen and "duckduckgo.com" not in normalized.lower():
                        urls.append(normalized)
                        seen.add(normalized)
                    if len(urls) >= max_results:
                        break
        except Exception as e:
            logger.warning(f"DuckDuckGo HTML search failed for '{query}': {e}")
        return urls

    async def search(self, query: str, max_results: int = 5) -> List[str]:
        urls: List[str] = []
        seen = set()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                params = {
                    "q": query,
                    "format": "json",
                    "kl": "us-en",
                    "no_redirect": 1,
                }

                response = await client.get("https://api.duckduckgo.com/", params=params)
                if response.status_code == 200:
                    data = response.json()

                    for item in data.get("RelatedTopics", [])[: max_results * 3]:
                        first_url = item.get("FirstURL") if isinstance(item, dict) else None
                        if first_url and first_url not in seen and "duckduckgo.com" not in first_url.lower():
                            urls.append(first_url)
                            seen.add(first_url)

                    abstract_url = data.get("AbstractURL")
                    if abstract_url and abstract_url not in seen and "duckduckgo.com" not in abstract_url.lower():
                        urls.append(abstract_url)
                        seen.add(abstract_url)

                    for result in data.get("Results", [])[: max_results * 2]:
                        result_url = result.get("FirstURL") if isinstance(result, dict) else None
                        if result_url and result_url not in seen and "duckduckgo.com" not in result_url.lower():
                            urls.append(result_url)
                            seen.add(result_url)
        except Exception as e:
            logger.warning(f"DuckDuckGo search failed for '{query}': {e}")

        if len(urls) < max_results:
            for fallback_url in await self._search_html(query, max_results=max_results):
                if fallback_url not in seen:
                    urls.append(fallback_url)
                    seen.add(fallback_url)
                if len(urls) >= max_results:
                    break

        return urls[:max_results]


class HackerNewsSearch:
    """Search Hacker News via Algolia free API."""

    async def search(self, query: str, max_results: int = 3) -> List[str]:
        urls = []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    "https://hn.algolia.com/api/v1/search",
                    params={
                        "query": query,
                        "hitsPerPage": max_results,
                        "restrictSearchableAttributes": "title,url",
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    for hit in data.get("hits", [])[:max_results]:
                        if "url" in hit and hit["url"]:
                            urls.append(hit["url"])
        except Exception as e:
            logger.warning(f"HackerNews search failed for '{query}': {e}")
        return urls


class GooglePlayStoreSearch:
    """Search Google Play Store for app URLs without API keys."""

    async def search(self, query: str, max_results: int = 3) -> List[str]:
        urls = []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    "https://play.google.com/store/search",
                    params={"q": query, "c": "apps"},
                    headers={"User-Agent": "Mozilla/5.0"},
                    follow_redirects=True,
                )
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "html.parser")
                    for link in soup.find_all("a", href=True)[:max_results]:
                        href = link.get("href")
                        if href and "/apps/details" in href:
                            full_url = f"https://play.google.com{href}" if href.startswith("/") else href
                            if full_url not in urls:
                                urls.append(full_url)
        except Exception as e:
            logger.warning(f"Play Store search failed for '{query}': {e}")
        return urls


class TrustpilotSearch:
    """Search Trustpilot reviews without official API access."""

    async def search(self, query: str, max_results: int = 3) -> List[str]:
        urls = []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    "https://www.trustpilot.com/search",
                    params={"query": query},
                    headers={"User-Agent": "Mozilla/5.0"},
                    follow_redirects=True,
                )
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "html.parser")
                    for link in soup.find_all("a", href=True)[:max_results]:
                        href = link.get("href")
                        if href and "/review/" in href:
                            urls.append(href if href.startswith("http") else f"https://trustpilot.com{href}")
        except Exception as e:
            logger.warning(f"Trustpilot search failed for '{query}': {e}")
        return urls


async def smart_search(
    query: str,
    sources: List[str] = None,
    max_urls: int = 5,
) -> List[str]:
    if sources is None:
        sources = ["duckduckgo", "hackernews", "playstore", "trustpilot"]

    all_urls = []
    seen = set()
    tasks = []

    ddg = DuckDuckGoSearch()
    hn = HackerNewsSearch()
    ps = GooglePlayStoreSearch()
    tp = TrustpilotSearch()

    for source in sources:
        if source == "duckduckgo":
            tasks.append(("duckduckgo", ddg.search(query, max_results=5)))
        elif source == "hackernews":
            tasks.append(("hackernews", hn.search(query, max_results=3)))
        elif source == "playstore":
            tasks.append(("playstore", ps.search(query, max_results=3)))
        elif source == "trustpilot":
            tasks.append(("trustpilot", tp.search(query, max_results=3)))

    results = await asyncio.gather(*[task[1] for task in tasks], return_exceptions=True)
    for (source_name, _), result in zip(tasks, results):
        if isinstance(result, list):
            for url in result:
                if url and url not in seen:
                    all_urls.append(url)
                    seen.add(url)
                    if len(all_urls) >= max_urls:
                        break
        else:
            logger.warning(f"Error from {source_name}: {result}")

    return all_urls[:max_urls]


async def search_multiple_queries(
    queries: List[str],
    max_urls_per_query: int = 5,
) -> List[str]:
    all_urls = []
    seen = set()
    tasks = [smart_search(q, max_urls=max_urls_per_query) for q in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, list):
            for url in result:
                if url and url not in seen:
                    all_urls.append(url)
                    seen.add(url)
    return all_urls
