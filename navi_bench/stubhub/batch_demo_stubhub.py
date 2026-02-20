#!/usr/bin/env python
"""
StubHub Batch Verification Runner

Production-level batch testing system for StubHub verification.
Runs multiple test scenarios with automated navigation and comprehensive reporting.

Features:
- Configurable test scenarios (no hardcoded team names)
- Multi-tab support with real-time tracking
- Parallel execution support
- Comprehensive result reporting
- JSON export for CI/CD integration

Usage:
    python batch_demo_stubhub.py              # Run all scenarios
    python batch_demo_stubhub.py --count 3    # Run first 3 scenarios
    python batch_demo_stubhub.py --headless   # Run headless
    python batch_demo_stubhub.py --export     # Export results to JSON
"""

import asyncio
import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import Page, BrowserContext, async_playwright
from loguru import logger

# Import verifier
from navi_bench.stubhub.stubhub_info_gathering import StubHubInfoGathering


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class TestScenario:
    """Defines a test scenario for batch execution."""
    name: str
    description: str
    search_term: str
    queries: list
    category: str = "general"
    expected_result: str = "available"  # available, sold_out, not_found


@dataclass
class BatchConfig:
    """Configuration for batch execution."""
    headless: bool = False
    max_concurrent: int = 1
    timeout_per_test_ms: int = 30000
    wait_between_tests_ms: int = 1000
    export_results: bool = False
    export_path: str = "batch_results.json"


@dataclass
class BrowserConfig:
    """Browser configuration."""
    viewport_width: int = 1366
    viewport_height: int = 768
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    locale: str = "en-US"
    timezone: str = "America/New_York"
    launch_args: list = field(default_factory=lambda: [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--no-sandbox",
    ])


# =============================================================================
# TEST SCENARIOS - Using generic category searches (no hardcoded team names)
# =============================================================================

SCENARIOS: list[TestScenario] = [
    TestScenario(
        name="NBA Basketball Search",
        description="Search for NBA basketball games",
        search_term="NBA",
        queries=[[{
            "event_names": ["nba", "basketball"],
            "event_categories": ["sports"],
        }]],
        category="sports",
    ),
    TestScenario(
        name="NFL Football Search",
        description="Search for NFL football games",
        search_term="NFL",
        queries=[[{
            "event_names": ["nfl", "football"],
            "event_categories": ["sports"],
        }]],
        category="sports",
    ),
    TestScenario(
        name="Concert Search",
        description="Search for any concert events",
        search_term="Concert",
        queries=[[{
            "event_categories": ["concerts"],
        }]],
        category="concerts",
    ),
    TestScenario(
        name="Broadway Theater Search",
        description="Search for Broadway shows",
        search_term="Broadway",
        queries=[[{
            "event_names": ["broadway"],
            "event_categories": ["theater"],
        }]],
        category="theater",
    ),
    TestScenario(
        name="Comedy Show Search",
        description="Search for comedy shows",
        search_term="Comedy",
        queries=[[{
            "event_names": ["comedy", "standup"],
            "event_categories": ["comedy"],
        }]],
        category="comedy",
    ),
    TestScenario(
        name="MLB Baseball Search",
        description="Search for MLB baseball games",
        search_term="MLB",
        queries=[[{
            "event_names": ["mlb", "baseball"],
            "event_categories": ["sports"],
        }]],
        category="sports",
    ),
    TestScenario(
        name="Music Festival Search",
        description="Search for music festivals",
        search_term="Festival",
        queries=[[{
            "event_names": ["festival", "fest"],
            "event_categories": ["festivals"],
        }]],
        category="festivals",
    ),
    TestScenario(
        name="NHL Hockey Search",
        description="Search for NHL hockey games",
        search_term="NHL",
        queries=[[{
            "event_names": ["nhl", "hockey"],
            "event_categories": ["sports"],
        }]],
        category="sports",
    ),
]


# =============================================================================
# NAVIGATION TRACKER
# =============================================================================

class NavigationTracker:
    """Tracks navigation for a single test."""
    
    def __init__(self, evaluator: StubHubInfoGathering):
        self.evaluator = evaluator
        self.navigation_count = 0
        self._lock = asyncio.Lock()
    
    async def attach_to_page(self, page: Page) -> None:
        async def on_navigate(frame):
            if frame != page.main_frame:
                return
            async with self._lock:
                self.navigation_count += 1
                try:
                    await self.evaluator.update(page=page)
                except Exception:
                    pass
        
        page.on("framenavigated", lambda f: asyncio.create_task(on_navigate(f)))
    
    async def handle_new_page(self, new_page: Page) -> None:
        try:
            await new_page.wait_for_load_state("domcontentloaded", timeout=5000)
            await self.attach_to_page(new_page)
        except Exception:
            pass
    
    def attach_to_context(self, context: BrowserContext) -> None:
        context.on("page", lambda p: asyncio.create_task(self.handle_new_page(p)))


# =============================================================================
# TEST RUNNER
# =============================================================================

@dataclass
class TestResult:
    """Result from a single test run."""
    scenario_name: str
    category: str
    search_term: str
    passed: bool
    score: float
    queries_covered: int
    total_queries: int
    pages_navigated: int
    duration_ms: float
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class BatchRunner:
    """Runs batch tests with comprehensive tracking and reporting."""
    
    def __init__(self, config: BatchConfig, browser_config: BrowserConfig):
        self.config = config
        self.browser_config = browser_config
        self.results: list[TestResult] = []
    
    async def run_single_test(
        self, 
        scenario: TestScenario, 
        browser
    ) -> TestResult:
        """Run a single test scenario."""
        start_time = datetime.now()
        
        try:
            # Create evaluator
            evaluator = StubHubInfoGathering(queries=scenario.queries)
            tracker = NavigationTracker(evaluator)
            
            # Create context
            context = await browser.new_context(
                viewport={
                    "width": self.browser_config.viewport_width,
                    "height": self.browser_config.viewport_height
                },
                user_agent=self.browser_config.user_agent,
                locale=self.browser_config.locale,
                timezone_id=self.browser_config.timezone,
            )
            
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """)
            
            page = await context.new_page()
            tracker.attach_to_context(context)
            await tracker.attach_to_page(page)
            
            # Navigate and search
            await page.goto("https://www.stubhub.com", timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            
            # Find search box
            search_performed = False
            for selector in ['input[placeholder*="Search"]', 'input[type="search"]', 'input[aria-label*="Search"]']:
                try:
                    search_box = await page.wait_for_selector(selector, timeout=3000)
                    if search_box:
                        await search_box.click()
                        await asyncio.sleep(0.3)
                        await search_box.fill(scenario.search_term)
                        await asyncio.sleep(0.3)
                        await page.keyboard.press("Enter")
                        search_performed = True
                        break
                except Exception:
                    continue
            
            if not search_performed:
                # Fallback to URL search
                encoded = scenario.search_term.replace(" ", "+")
                await page.goto(f"https://www.stubhub.com/secure/Search?q={encoded}", timeout=60000)
            
            await asyncio.sleep(3)
            
            # Evaluate
            await evaluator.reset()
            await evaluator.update(page=page)
            result = await evaluator.compute()
            
            await context.close()
            
            duration = (datetime.now() - start_time).total_seconds() * 1000
            
            return TestResult(
                scenario_name=scenario.name,
                category=scenario.category,
                search_term=scenario.search_term,
                passed=result.score >= 1.0,
                score=result.score,
                queries_covered=result.n_covered,
                total_queries=result.n_queries,
                pages_navigated=tracker.navigation_count,
                duration_ms=duration,
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds() * 1000
            return TestResult(
                scenario_name=scenario.name,
                category=scenario.category,
                search_term=scenario.search_term,
                passed=False,
                score=0.0,
                queries_covered=0,
                total_queries=len(scenario.queries),
                pages_navigated=0,
                duration_ms=duration,
                error=str(e),
            )
    
    async def run_batch(self, scenarios: list[TestScenario]) -> list[TestResult]:
        """Run all scenarios in batch."""
        
        logger.info(f"Starting batch run with {len(scenarios)} scenarios")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.config.headless,
                args=self.browser_config.launch_args,
            )
            
            for i, scenario in enumerate(scenarios, 1):
                logger.info(f"[{i}/{len(scenarios)}] Running: {scenario.name}")
                
                result = await self.run_single_test(scenario, browser)
                self.results.append(result)
                
                status = "✅ PASS" if result.passed else ("❌ ERROR" if result.error else "⚠️ FAIL")
                logger.info(f"  {status} - Score: {result.score:.0%}")
                
                if i < len(scenarios):
                    await asyncio.sleep(self.config.wait_between_tests_ms / 1000)
            
            await browser.close()
        
        return self.results
    
    def print_summary(self) -> None:
        """Print batch run summary."""
        
        print("\n" + "=" * 80)
        print("BATCH VERIFICATION RESULTS")
        print("=" * 80)
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed and not r.error)
        errors = sum(1 for r in self.results if r.error)
        
        print(f"\nTotal Tests:    {total}")
        print(f"  ✅ Passed:    {passed}")
        print(f"  ⚠️ Failed:    {failed}")
        print(f"  ❌ Errors:    {errors}")
        print(f"\nPass Rate:      {passed/total*100:.1f}%")
        
        print("\n" + "-" * 80)
        print("DETAILED RESULTS:")
        print("-" * 80)
        
        for r in self.results:
            if r.error:
                status = "❌ ERROR"
            elif r.passed:
                status = "✅ PASS"
            else:
                status = "⚠️ FAIL"
            
            print(f"  {status:10} | {r.scenario_name:25} | Score: {r.score:.0%} | {r.duration_ms/1000:.1f}s")
        
        print("=" * 80)
    
    def export_results(self, path: str) -> None:
        """Export results to JSON."""
        data = {
            "timestamp": datetime.now().isoformat(),
            "total_tests": len(self.results),
            "passed": sum(1 for r in self.results if r.passed),
            "failed": sum(1 for r in self.results if not r.passed),
            "results": [
                {
                    "name": r.scenario_name,
                    "category": r.category,
                    "search_term": r.search_term,
                    "passed": r.passed,
                    "score": r.score,
                    "queries_covered": r.queries_covered,
                    "total_queries": r.total_queries,
                    "pages_navigated": r.pages_navigated,
                    "duration_ms": r.duration_ms,
                    "error": r.error,
                    "timestamp": r.timestamp,
                }
                for r in self.results
            ]
        }
        
        Path(path).write_text(json.dumps(data, indent=2))
        logger.info(f"Results exported to: {path}")


# =============================================================================
# MAIN
# =============================================================================

async def main():
    """Main entry point."""
    
    parser = argparse.ArgumentParser(description="StubHub Batch Verification Runner")
    parser.add_argument("--count", "-c", type=int, default=len(SCENARIOS), help="Number of tests to run")
    parser.add_argument("--headless", "-hl", action="store_true", help="Run headless")
    parser.add_argument("--export", "-e", action="store_true", help="Export results to JSON")
    parser.add_argument("--output", "-o", type=str, default="batch_results.json", help="Output file path")
    args = parser.parse_args()
    
    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    
    print("\n" + "=" * 80)
    print("STUBHUB BATCH VERIFICATION RUNNER")
    print("=" * 80)
    print(f"Total Scenarios:  {len(SCENARIOS)}")
    print(f"Tests to Run:     {min(args.count, len(SCENARIOS))}")
    print(f"Headless Mode:    {args.headless}")
    print(f"Export Results:   {args.export}")
    print("=" * 80 + "\n")
    
    # Run batch
    config = BatchConfig(headless=args.headless, export_results=args.export)
    runner = BatchRunner(config, BrowserConfig())
    
    scenarios_to_run = SCENARIOS[:min(args.count, len(SCENARIOS))]
    
    try:
        await runner.run_batch(scenarios_to_run)
        runner.print_summary()
        
        if args.export:
            runner.export_results(args.output)
            
    except KeyboardInterrupt:
        print("\n\nInterrupted.")
    except Exception as e:
        logger.exception(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
