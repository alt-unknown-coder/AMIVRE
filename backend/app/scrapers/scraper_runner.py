"""
Module: scraper_runner.py

Compatibility layer for the agentic research pipeline.
This file keeps the old public API stable while routing requests to the
free DuckDuckGo + BeautifulSoup implementation.
"""

import logging
from typing import List, Tuple, Dict

from app.scrapers.free_research_pipeline import (
    build_market_scout_context as _build_market_scout_context,
    build_sentiment_context as _build_sentiment_context,
    build_competitor_context as _build_competitor_context,
    build_trend_context as _build_trend_context,
)

logger = logging.getLogger(__name__)


async def build_market_scout_context(queries: List[str], progress_callback=None) -> Tuple[str, List[Dict]]:
    """Runs the free research pipeline for Market Scout."""
    return await _build_market_scout_context(queries, progress_callback)


async def build_sentiment_context(queries: List[str], progress_callback=None) -> Tuple[str, List[Dict]]:
    """Runs the free research pipeline for Sentiment Analyst."""
    return await _build_sentiment_context(queries, progress_callback)


async def build_competitor_context(queries: List[str], progress_callback=None) -> Tuple[str, List[Dict]]:
    """Runs the free research pipeline for Competitor Tracker."""
    return await _build_competitor_context(queries, progress_callback)


async def build_trend_context(queries: List[str], progress_callback=None) -> Tuple[str, List[Dict]]:
    """Runs the free research pipeline for Trend Forecaster."""
    return await _build_trend_context(queries, progress_callback)
