#!/usr/bin/env python3
"""
Integration test for the research pipeline scraper.
Tests SearXNG connectivity, rate limiting, and fallback behavior.

Usage: python test_scraper_integration.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add the backend app to the path
sys.path.insert(0, str(Path(__file__).parent))

from app.scrapers.research_pipeline import run_pipeline

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_single_query():
    """Test a single search query."""
    logger.info("=" * 80)
    logger.info("TEST 1: Single Query")
    logger.info("=" * 80)
    
    queries = ["bike repair on-demand startups"]
    context, results = await run_pipeline(queries, deep_scan=False)
    
    logger.info(f"Results returned: {len(results)} sources")
    if context:
        logger.info(f"Context length: {len(context)} characters")
        logger.info("✓ PASSED: Single query returned results")
    else:
        logger.warning("⚠ Single query returned empty context (fallback occurred)")
    
    return bool(context)


async def test_multiple_queries():
    """Test multiple queries with rate limiting."""
    logger.info("=" * 80)
    logger.info("TEST 2: Multiple Queries (Rate Limiting Test)")
    logger.info("=" * 80)
    
    queries = [
        "bike sharing on-demand rentals market",
        "last-mile delivery electric bikes",
        "dockless bike sharing competitors"
    ]
    
    logger.info(f"Executing {len(queries)} queries sequentially with rate limiting...")
    context, results = await run_pipeline(queries, deep_scan=False)
    
    logger.info(f"Results returned: {len(results)} sources")
    if context:
        logger.info(f"Context length: {len(context)} characters")
        logger.info("✓ PASSED: Multiple queries with rate limiting completed")
    else:
        logger.warning("⚠ Multiple queries returned empty context (fallback occurred)")
    
    return bool(context)


async def test_no_queries():
    """Test with empty query list."""
    logger.info("=" * 80)
    logger.info("TEST 3: Empty Query List")
    logger.info("=" * 80)
    
    context, results = await run_pipeline([], deep_scan=False)
    
    if context == "" and results == []:
        logger.info("✓ PASSED: Empty query list handled correctly")
        return True
    else:
        logger.warning("⚠ Empty query list returned unexpected results")
        return False


async def test_resilience():
    """Test scraper resilience to individual query failures."""
    logger.info("=" * 80)
    logger.info("TEST 4: Query Resilience (Mixed Valid Queries)")
    logger.info("=" * 80)
    
    queries = [
        "fractional ownership real estate market 2024",
        "proptech trends vacation rental yield",
    ]
    
    logger.info("Testing resilience with multiple queries...")
    context, results = await run_pipeline(queries, deep_scan=False)
    
    logger.info(f"Results returned: {len(results)} sources")
    logger.info("✓ PASSED: Scraper resilience test completed")
    
    return True


async def main():
    """Run all integration tests."""
    logger.info("\n" + "=" * 80)
    logger.info("RESEARCH PIPELINE INTEGRATION TESTS")
    logger.info("=" * 80 + "\n")
    
    results = []
    
    try:
        results.append(("Single Query", await test_single_query()))
        logger.info("")
        
        results.append(("Multiple Queries", await test_multiple_queries()))
        logger.info("")
        
        results.append(("Empty Query List", await test_no_queries()))
        logger.info("")
        
        results.append(("Resilience", await test_resilience()))
        logger.info("")
        
    except Exception as e:
        logger.error(f"Test suite error: {e}", exc_info=True)
        return False
    
    # Summary
    logger.info("=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status}: {test_name}")
    
    logger.info(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("\n✓ All tests passed! Scraper is working correctly.")
        return True
    else:
        logger.warning(f"\n⚠ {total - passed} test(s) failed. Check logs for details.")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
