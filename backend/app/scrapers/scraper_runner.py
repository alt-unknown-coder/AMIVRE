"""
Module: scraper_runner.py

Lightweight agent wrapper layer for the dual-tier research pipeline.
Each agent chooses whether to perform a deep-crawl micro-scan or remain strictly
snippet-only to preserve Docker resource limits.
"""

import logging
from typing import Dict, List, Tuple

from app.scrapers.research_pipeline import run_pipeline

logger = logging.getLogger(__name__)


async def build_market_scout_context(
    queries: List[str],
    progress_callback=None,
    deep_scan: bool = True,
) -> Tuple[str, List[Dict]]:
    """Runs the research pipeline for Market Scout with deep micro-crawling enabled."""
    context, raw_data = await run_pipeline(queries, deep_scan=deep_scan, progress_callback=progress_callback)
    if not context.strip():
        return "", raw_data
    return f"=== LIVE WEB INTELLIGENCE (Market Data) ===\n{context}", raw_data


async def build_sentiment_context(
    queries: List[str],
    progress_callback=None,
    deep_scan: bool = False,
) -> Tuple[str, List[Dict]]:
    """Sentiment analysis remains snippet-only to preserve compute footprint."""
    context, raw_data = await run_pipeline(queries, deep_scan=deep_scan, progress_callback=progress_callback)
    if not context.strip():
        return "", raw_data
    return f"=== LIVE WEB INTELLIGENCE (User Sentiment) ===\n{context}", raw_data


async def build_competitor_context(
    queries: List[str],
    progress_callback=None,
    deep_scan: bool = True,
) -> Tuple[str, List[Dict]]:
    """Competitor research can use the targeted deep micro-crawl."""
    context, raw_data = await run_pipeline(queries, deep_scan=deep_scan, progress_callback=progress_callback)
    if not context.strip():
        return "", raw_data
    return f"=== LIVE WEB INTELLIGENCE (Competitor Data) ===\n{context}", raw_data


async def build_trend_context(
    queries: List[str],
    progress_callback=None,
    deep_scan: bool = False,
) -> Tuple[str, List[Dict]]:
    """Trend forecasting stays on lightweight snippet search for lower resource use."""
    context, raw_data = await run_pipeline(queries, deep_scan=deep_scan, progress_callback=progress_callback)
    if not context.strip():
        return "", raw_data
    return f"=== LIVE WEB INTELLIGENCE (Trend Data) ===\n{context}", raw_data
