#!/usr/bin/env python3
"""
Auto Demo StubHub - Automated Task Runner with HTML Report Generation

This script:
1. Reads tasks from tasks.json
2. Runs each task interactively
3. Generates an HTML report with all results
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from playwright.async_api import async_playwright, Page, Browser
from navi_bench.stubhub.stubhub_info_gathering import StubHubInfoGathering


@dataclass
class TaskResult:
    """Result of a single task execution."""
    task_id: str
    name: str
    task_type: str
    expected_result: str
    actual_result: str
    score: float
    passed: bool
    correct_prediction: bool  # Did actual match expected?
    events_scraped: list = field(default_factory=list)
    pages_navigated: int = 0
    error: Optional[str] = None
    duration_seconds: float = 0.0


class HTMLReportGenerator:
    """Generates beautiful HTML reports for test results."""
    
    @staticmethod
    def generate(results: list[TaskResult], output_path: str) -> str:
        """Generate HTML report and save to file."""
        
        # Calculate statistics
        total = len(results)
        correct = sum(1 for r in results if r.correct_prediction)
        incorrect = total - correct
        accuracy = (correct / total * 100) if total > 0 else 0
        
        tp_results = [r for r in results if r.task_type == "true_positive"]
        tn_results = [r for r in results if r.task_type == "true_negative"]
        fp_results = [r for r in results if r.task_type == "false_positive_check"]
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>StubHub Verifier Test Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #eee;
            padding: 20px;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        header {{
            text-align: center;
            padding: 30px 0;
            border-bottom: 2px solid #4a4a6a;
            margin-bottom: 30px;
        }}
        h1 {{
            font-size: 2.5rem;
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 10px;
        }}
        .timestamp {{ color: #888; font-size: 0.9rem; }}
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}
        .stat-card {{
            background: rgba(255,255,255,0.1);
            border-radius: 15px;
            padding: 25px;
            text-align: center;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .stat-card h3 {{ font-size: 2.5rem; margin-bottom: 10px; }}
        .stat-card.accuracy h3 {{ color: #00ff88; }}
        .stat-card.correct h3 {{ color: #4ade80; }}
        .stat-card.incorrect h3 {{ color: #f87171; }}
        .stat-card.total h3 {{ color: #60a5fa; }}
        .section {{ margin-bottom: 40px; }}
        .section-title {{
            font-size: 1.5rem;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #4a4a6a;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .badge {{
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: bold;
        }}
        .badge-tp {{ background: #22c55e; color: #000; }}
        .badge-tn {{ background: #ef4444; color: #fff; }}
        .badge-fp {{ background: #f59e0b; color: #000; }}
        .task-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 15px;
            border-left: 4px solid #666;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .task-card:hover {{
            transform: translateX(5px);
            box-shadow: 0 5px 20px rgba(0,0,0,0.3);
        }}
        .task-card.correct {{ border-left-color: #22c55e; }}
        .task-card.incorrect {{ border-left-color: #ef4444; }}
        .task-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }}
        .task-title {{ font-size: 1.2rem; font-weight: bold; }}
        .task-id {{ color: #888; font-size: 0.9rem; }}
        .result-badge {{
            padding: 8px 20px;
            border-radius: 25px;
            font-weight: bold;
            font-size: 0.9rem;
        }}
        .result-badge.pass {{ background: linear-gradient(135deg, #22c55e, #16a34a); color: #fff; }}
        .result-badge.fail {{ background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff; }}
        .task-details {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }}
        .detail-item {{
            background: rgba(0,0,0,0.2);
            padding: 10px 15px;
            border-radius: 8px;
        }}
        .detail-label {{
            font-size: 0.75rem;
            color: #888;
            text-transform: uppercase;
            margin-bottom: 5px;
        }}
        .detail-value {{ font-size: 1rem; font-weight: 500; }}
        .events-list {{
            margin-top: 15px;
            background: rgba(0,0,0,0.2);
            border-radius: 8px;
            padding: 15px;
            max-height: 200px;
            overflow-y: auto;
        }}
        .event-item {{
            padding: 8px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            font-size: 0.85rem;
        }}
        .event-item:last-child {{ border-bottom: none; }}
        .prediction-match {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 10px;
            font-size: 0.8rem;
            margin-left: 10px;
        }}
        .prediction-match.correct {{ background: #22c55e; color: #000; }}
        .prediction-match.incorrect {{ background: #ef4444; color: #fff; }}
        footer {{
            text-align: center;
            padding: 30px;
            color: #666;
            border-top: 1px solid #333;
            margin-top: 40px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎫 StubHub Verifier Test Report</h1>
            <p class="timestamp">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        </header>
        
        <div class="summary-grid">
            <div class="stat-card accuracy">
                <h3>{accuracy:.1f}%</h3>
                <p>Accuracy</p>
            </div>
            <div class="stat-card correct">
                <h3>{correct}</h3>
                <p>Correct Predictions</p>
            </div>
            <div class="stat-card incorrect">
                <h3>{incorrect}</h3>
                <p>Incorrect Predictions</p>
            </div>
            <div class="stat-card total">
                <h3>{total}</h3>
                <p>Total Tests</p>
            </div>
        </div>
"""
        
        # Add sections
        if tp_results:
            html += HTMLReportGenerator._generate_section("True Positive Tests", "Tests where PASS is expected", "badge-tp", tp_results)
        if tn_results:
            html += HTMLReportGenerator._generate_section("True Negative Tests", "Tests where FAIL is expected", "badge-tn", tn_results)
        if fp_results:
            html += HTMLReportGenerator._generate_section("False Positive Checks", "Edge cases to verify", "badge-fp", fp_results)
        
        html += """
        <footer>
            <p>StubHub Verifier Test Framework v2.0</p>
            <p>Navigation Stack-Based Verification System</p>
        </footer>
    </div>
</body>
</html>"""
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        return output_path
    
    @staticmethod
    def _generate_section(title: str, description: str, badge_class: str, results: list[TaskResult]) -> str:
        html = f"""
        <div class="section">
            <h2 class="section-title">
                <span class="badge {badge_class}">{len(results)}</span>
                {title}
            </h2>
            <p style="color: #888; margin-bottom: 20px;">{description}</p>
"""
        for r in results:
            correct_class = "correct" if r.correct_prediction else "incorrect"
            result_badge = "pass" if r.actual_result == "PASS" else "fail"
            prediction_text = "✓ Correct" if r.correct_prediction else "✗ Incorrect"
            prediction_class = "correct" if r.correct_prediction else "incorrect"
            
            events_html = ""
            for event in r.events_scraped[:10]:
                event_name = str(event.get('eventName', 'Unknown'))[:50]
                city = event.get('city', '?')
                events_html += f'<div class="event-item">📍 {city} | {event_name}</div>\n'
            
            html += f"""
            <div class="task-card {correct_class}">
                <div class="task-header">
                    <div>
                        <span class="task-id">{r.task_id}</span>
                        <h3 class="task-title">{r.name}</h3>
                    </div>
                    <div>
                        <span class="result-badge {result_badge}">{r.actual_result}</span>
                        <span class="prediction-match {prediction_class}">{prediction_text}</span>
                    </div>
                </div>
                <div class="task-details">
                    <div class="detail-item">
                        <div class="detail-label">Expected</div>
                        <div class="detail-value">{r.expected_result}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Actual</div>
                        <div class="detail-value">{r.actual_result}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Score</div>
                        <div class="detail-value">{r.score*100:.1f}%</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Pages</div>
                        <div class="detail-value">{r.pages_navigated}</div>
                    </div>
                </div>
                <div class="events-list">
                    <div class="detail-label">Events Scraped ({len(r.events_scraped)})</div>
                    {events_html}
                </div>
            </div>
"""
        html += "        </div>\n"
        return html


class AutoDemoRunner:
    """Runs tasks from tasks.json automatically."""
    
    def __init__(self, tasks_file: str = "tasks.json"):
        self.tasks_file = Path(__file__).parent / tasks_file
        self.results: list[TaskResult] = []
        self.page_count = 0
    
    def load_tasks(self) -> list[dict]:
        with open(self.tasks_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('tasks', [])
    
    async def run_single_task(self, task: dict, browser: Browser) -> TaskResult:
        start_time = datetime.now()
        self.page_count = 0
        events = []
        
        try:
            queries = [[task['query']]]
            verifier = StubHubInfoGathering(queries=queries)
            await verifier.reset()
            
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id=task.get('timezone', 'America/Los_Angeles'),
            )
            
            # Remove webdriver property to avoid detection
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            page = await context.new_page()
            
            # Use verifier's built-in tracking (handles new tabs automatically)
            verifier.attach_to_context(context)
            
            print(f"\n{'='*60}")
            print(f"Task: {task['name']}")
            print(f"ID: {task['id']} | Type: {task['type']}")
            print(f"Expected: {task['expected_result']}")
            print(f"Hint: {task.get('navigation_hint', 'Navigate freely')}")
            print(f"{'='*60}")
            
            await page.goto(task['url'], wait_until='domcontentloaded')
            await asyncio.sleep(2)
            
            print("\n🌐 Browser ready - complete the task manually.")
            print("Press ENTER when done...")
            await asyncio.get_event_loop().run_in_executor(None, input)
            
            # Final update on ALL open pages
            for p in context.pages:
                try:
                    await verifier.update(page=p)
                except:
                    pass
            
            self.page_count = len(verifier._navigation_stack)
            result = await verifier.compute()
            
            for page_infos in verifier._all_infos:
                events.extend(page_infos)
            
            await context.close()
            
            actual_result = "PASS" if result.score >= 0.5 else "FAIL"
            correct_prediction = (actual_result == task['expected_result'])
            duration = (datetime.now() - start_time).total_seconds()
            
            return TaskResult(
                task_id=task['id'],
                name=task['name'],
                task_type=task['type'],
                expected_result=task['expected_result'],
                actual_result=actual_result,
                score=result.score,
                passed=result.score >= 0.5,
                correct_prediction=correct_prediction,
                events_scraped=events,
                pages_navigated=self.page_count,
                duration_seconds=duration
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return TaskResult(
                task_id=task['id'],
                name=task['name'],
                task_type=task['type'],
                expected_result=task['expected_result'],
                actual_result="ERROR",
                score=0.0,
                passed=False,
                correct_prediction=False,
                events_scraped=events,
                pages_navigated=self.page_count,
                error=str(e),
                duration_seconds=duration
            )
    
    async def run_all(self):
        tasks = self.load_tasks()
        print(f"\n{'='*60}")
        print("STUBHUB VERIFIER - AUTO DEMO")
        print(f"{'='*60}")
        print(f"Loaded {len(tasks)} tasks from {self.tasks_file.name}")
        
        print("\nAvailable Tasks:")
        for i, task in enumerate(tasks, 1):
            print(f"  [{i}] {task['id']} - {task['name']} ({task['type']})")
        
        print("\nOptions:")
        print("  [A] Run ALL tasks")
        print("  [1-N] Run specific task")
        print("  [Q] Quit")
        
        choice = input("\nSelect: ").strip().upper()
        
        if choice == 'Q':
            print("Goodbye!")
            return
        
        if choice == 'A':
            tasks_to_run = tasks
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(tasks):
                tasks_to_run = [tasks[idx]]
            else:
                print("Invalid selection")
                return
        else:
            print("Invalid selection")
            return
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                ]
            )
            
            for task in tasks_to_run:
                result = await self.run_single_task(task, browser)
                self.results.append(result)
                
                status = "✅" if result.correct_prediction else "❌"
                print(f"\n{status} Result: {result.actual_result} (Expected: {result.expected_result})")
                print(f"   Score: {result.score*100:.1f}% | Pages: {result.pages_navigated}")
            
            await browser.close()
        
        report_path = Path(__file__).parent / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        HTMLReportGenerator.generate(self.results, str(report_path))
        
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        total = len(self.results)
        correct = sum(1 for r in self.results if r.correct_prediction)
        accuracy = (correct / total * 100) if total > 0 else 0
        
        print(f"Total Tests: {total}")
        print(f"Correct: {correct}")
        print(f"Accuracy: {accuracy:.1f}%")
        print(f"\n📊 HTML Report: {report_path}")
        print(f"{'='*60}")
        
        os.startfile(str(report_path))


async def main():
    runner = AutoDemoRunner()
    await runner.run_all()


if __name__ == "__main__":
    asyncio.run(main())
