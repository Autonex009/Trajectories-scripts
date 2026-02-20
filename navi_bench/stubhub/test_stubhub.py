"""
Test script for StubHub verifier.
Run with: python navi_bench/stubhub/test_stubhub.py
Or: pytest navi_bench/stubhub/test_stubhub.py -v
"""

import asyncio
import json
import pytest
from playwright.async_api import async_playwright

from navi_bench.base import DatasetItem, instantiate


@pytest.mark.asyncio
async def test_scraper_on_real_page():
    """Test the JavaScript scraper on a real StubHub page."""
    print("=" * 60)
    print("Testing StubHub JavaScript Scraper")
    print("=" * 60)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Test 1: Navigate to StubHub search
        print("\n[Test 1] Loading StubHub search page...")
        await page.goto("https://www.stubhub.com/")
        await page.wait_for_timeout(2000)
        
        # Search for Lakers
        print("[Test 1] Searching for 'Lakers'...")
        search_box = await page.query_selector('input[type="search"]')
        if search_box:
            await search_box.fill("Lakers")
            await search_box.press("Enter")
            await page.wait_for_timeout(3000)
        
        # Load and execute the scraper
        print("[Test 1] Running JavaScript scraper...")
        with open("navi_bench/stubhub/stubhub_info_gathering.js", "r") as f:
            js_script = f.read()
        
        results = await page.evaluate(js_script)
        print(f"[Test 1] Extracted {len(results)} results")
        
        if results:
            print("\n[Test 1] Sample result:")
            print(json.dumps(results[0], indent=2))
        else:
            print("\n[Test 1] [WARN] No results extracted - may need selector updates")
        
        await browser.close()
    
    print("\n" + "=" * 60)
    print("Scraper Test Complete")
    print("=" * 60)


@pytest.mark.asyncio
async def test_verifier_with_dataset():
    """Test the Python verifier with a dataset item."""
    print("\n" + "=" * 60)
    print("Testing StubHub Python Verifier")
    print("=" * 60)
    
    # Import directly to avoid DatasetItem validation issues
    from navi_bench.stubhub.stubhub_info_gathering import (
        StubHubInfoGathering,
        generate_task_config_deterministic,
    )
    
    # Create evaluator directly
    queries = [[{
        "event_names": ["lakers", "los angeles lakers", "la lakers"],
        "event_categories": ["sports", "basketball", "nba"],
        "require_available": False,
    }]]
    
    print("\n[Test] Creating evaluator...")
    evaluator = StubHubInfoGathering(queries=queries)
    
    print("[Test] Evaluator created:", evaluator)
    
    # Test with Playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        print("\n[Test] Navigating to StubHub...")
        await page.goto("https://www.stubhub.com/")
        await page.wait_for_timeout(2000)
        
        # Search for Lakers
        search_box = await page.query_selector('input[type="search"]')
        if search_box:
            await search_box.fill("Lakers December 20")
            await search_box.press("Enter")
            await page.wait_for_timeout(3000)
        
        print("[Test] Updating evaluator with page data...")
        await evaluator.update(page=page)
        
        print("[Test] Computing result...")
        result = await evaluator.compute()
        
        print("\n" + "=" * 60)
        print("VERIFICATION RESULT")
        print("=" * 60)
        print(f"Score: {result.score}")
        print(f"Queries covered: {result.n_covered}/{result.n_queries}")
        print(f"Coverage: {result.score * 100:.1f}%")
        
        if result.score == 1.0:
            print("[PASS] SUCCESS: All queries covered!")
        else:
            print("[WARN] PARTIAL: Some queries not covered")
        
        await browser.close()
    
    print("=" * 60)


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("STUBHUB VERIFIER TEST SUITE")
    print("=" * 60)
    
    try:
        # Test 1: Scraper
        await test_scraper_on_real_page()
        
        # Test 2: Verifier
        await test_verifier_with_dataset()
        
        print("\n" + "=" * 60)
        print("ALL TESTS COMPLETE")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
