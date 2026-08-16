#!/usr/bin/env python3
"""
Quick SearXNG connectivity test - validates bot detection is fixed.

This test verifies:
1. SearXNG is accessible from Docker network
2. Proper headers are being sent
3. No 403 Forbidden errors
4. Responses are valid

Usage: python verify_searxng_fix.py
"""

import asyncio
import httpx
import logging
import json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_searxng_connectivity():
    """Test direct SearXNG connectivity."""
    logger.info("=" * 70)
    logger.info("SEARXNG CONNECTIVITY TEST")
    logger.info("=" * 70)
    
    searxng_url = "http://searxng:8080/search"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "X-Forwarded-For": "127.0.0.1",
        "X-Real-IP": "127.0.0.1",
    }
    
    params = {
        "q": "test query",
        "format": "json",
        "engines": "google,bing,duckduckgo",
    }
    
    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"Testing SearXNG at: {searxng_url}")
            logger.info(f"Headers: {json.dumps(headers, indent=2)}")
            
            response = await client.get(
                searxng_url,
                params=params,
                headers=headers,
                timeout=5.0,
            )
            
            logger.info(f"Response Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                result_count = len(data.get("results", []))
                logger.info(f"✓ SUCCESS: SearXNG returned {result_count} results")
                logger.info(f"✓ Response contains: {list(data.keys())}")
                return True
            elif response.status_code == 403:
                logger.error("✗ FAILED: Still getting 403 Forbidden")
                logger.error(f"Response: {response.text[:500]}")
                return False
            else:
                logger.warning(f"⚠ Unexpected status code: {response.status_code}")
                logger.warning(f"Response: {response.text[:500]}")
                return False
                
    except Exception as e:
        logger.error(f"✗ Connection error: {e}")
        return False


async def test_sequential_queries():
    """Test that sequential queries with delays work."""
    logger.info("\n" + "=" * 70)
    logger.info("SEQUENTIAL QUERY TEST (Rate Limiting)")
    logger.info("=" * 70)
    
    searxng_url = "http://searxng:8080/search"
    queries = ["bike repair", "electric scooter", "last mile delivery"]
    
    headers_template = {
        "Accept": "application/json",
        "X-Forwarded-For": "127.0.0.1",
        "X-Real-IP": "127.0.0.1",
    }
    
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    ]
    
    try:
        async with httpx.AsyncClient() as client:
            results = []
            for i, query in enumerate(queries):
                headers = headers_template.copy()
                headers["User-Agent"] = user_agents[i % len(user_agents)]
                
                logger.info(f"\nQuery {i+1}/{len(queries)}: '{query}'")
                
                response = await client.get(
                    searxng_url,
                    params={"q": query, "format": "json", "engines": "google,bing,duckduckgo"},
                    headers=headers,
                    timeout=5.0,
                )
                
                if response.status_code == 200:
                    data = response.json()
                    count = len(data.get("results", []))
                    logger.info(f"✓ Got {count} results")
                    results.append(True)
                else:
                    logger.error(f"✗ Status {response.status_code}")
                    results.append(False)
                
                # Delay between queries
                if i < len(queries) - 1:
                    logger.info("Waiting 1.0s before next query...")
                    await asyncio.sleep(1.0)
            
            if all(results):
                logger.info(f"\n✓ SUCCESS: All {len(queries)} sequential queries succeeded")
                return True
            else:
                logger.error(f"\n✗ FAILED: {sum(not r for r in results)} queries failed")
                return False
                
    except Exception as e:
        logger.error(f"✗ Error during sequential test: {e}")
        return False


async def main():
    """Run all verification tests."""
    logger.info("\n" + "=" * 70)
    logger.info("SEARXNG BOT DETECTION FIX - VERIFICATION TESTS")
    logger.info("=" * 70 + "\n")
    
    results = []
    
    try:
        # Test 1: Basic connectivity
        logger.info("\nTest 1/2: Basic Connectivity")
        results.append(("Connectivity", await test_searxng_connectivity()))
        
        # Test 2: Sequential queries
        logger.info("\nTest 2/2: Sequential Queries")
        results.append(("Sequential Queries", await test_sequential_queries()))
        
    except Exception as e:
        logger.error(f"Test suite error: {e}", exc_info=True)
        return False
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("VERIFICATION SUMMARY")
    logger.info("=" * 70)
    
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"{status}: {test_name}")
    
    all_passed = all(passed for _, passed in results)
    
    if all_passed:
        logger.info("\n✓ All tests passed! Bot detection issue is fixed.")
        logger.info("\nNext steps:")
        logger.info("1. Run: docker compose -f docker/docker-compose.yml up --build")
        logger.info("2. Monitor logs: docker compose -f docker/docker-compose.yml logs -f worker")
        logger.info("3. Start your analysis jobs")
    else:
        logger.warning("\n⚠ Some tests failed. Check SearXNG container logs for details:")
        logger.warning("   docker compose -f docker/docker-compose.yml logs searxng")
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
