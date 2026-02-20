#!/usr/bin/env python
"""
StubHub Ticket Availability Verification Demo

Human-in-the-loop verification system for StubHub events.
Supports multi-tab browsing, real-time navigation tracking, and comprehensive
evaluation of agent navigation behavior.

Features:
- Real-time page state tracking via navigation events
- Multi-tab/popup window support
- Stealth browser configuration (anti-detection)
- Comprehensive scraper with LD+JSON extraction
- Flexible query-based verification
- Debug output showing scraped events

Author: NaviBench Team
"""

import asyncio
import json
import sys
from datetime import datetime
from typing import Any, Callable, Optional
from dataclasses import dataclass, field

from playwright.async_api import Page, BrowserContext, async_playwright
from loguru import logger

# Import our evaluator
from navi_bench.stubhub.stubhub_info_gathering import (
    StubHubInfoGathering,
    generate_task_config_deterministic,
)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class BrowserConfig:
    """Browser launch configuration for stealth operation."""
    headless: bool = False
    viewport_width: int = 1366
    viewport_height: int = 768
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    locale: str = "en-US"
    
    # Anti-detection arguments
    launch_args: list = field(default_factory=lambda: [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--start-maximized",
        "--no-sandbox",
    ])


@dataclass
class TaskScenario:
    """Defines a verification task scenario."""
    task_id: str
    name: str
    description: str
    url: str
    task_prompt: str
    queries: list
    location: str
    timezone: str
    category: str
    tags: list = field(default_factory=list)
    
    def __post_init__(self):
        """Validate scenario configuration."""
        assert self.task_id, "task_id is required"
        assert self.queries, "queries cannot be empty"


# =============================================================================
# TASK SCENARIOS - Define your test cases here
# =============================================================================

SCENARIOS: list[TaskScenario] = [
    # PRIMARY TASK: Coldplay Israel
    # NOTE: This task verifies BOTH event name AND location (Israel)
    TaskScenario(
        task_id="stubhub/concerts/coldplay/001",
        name="Coldplay Concert - Israel",
        description="Search for Coldplay concert tickets in Israel",
        url="https://www.stubhub.com/",
        task_prompt=(
            "Search for Coldplay concert tickets in Israel. "
            "Find any upcoming Coldplay event and check ticket availability."
        ),
        queries=[[{
            "event_names": ["coldplay"],  # Match any event with "coldplay" in name
            "cities": ["haifa", "tel aviv", "jerusalem", "israel"],  # MUST be in Israel!
            "require_available": False,   # Sold out still counts as success
        }]],
        location="Israel",
        timezone="Asia/Jerusalem",
        category="concerts",
        tags=["coldplay", "concert", "music", "israel"],
    ),
    # Zakir Khan - Pune (Comedy Concert)
    TaskScenario(
        task_id="stubhub/comedy/zakirkhan/001",
        name="Zakir Khan Concert - Pune",
        description="Search for Zakir Khan comedy show tickets in Pune",
        url="https://www.stubhub.com/",
        task_prompt=(
            "Search for Zakir Khan comedy show tickets in Pune, India. "
            "Find any upcoming Zakir Khan event and check ticket availability."
        ),
        queries=[[{
            "event_names": ["zakir khan", "zakir"],  # Match Zakir Khan events
            "cities": ["pune", "पुणे"],  # Must be in Pune
            "require_available": False,
        }]],
        location="India",
        timezone="Asia/Kolkata",
        category="comedy",
        tags=["zakir khan", "comedy", "standup", "pune", "india"],
    ),
    # Generic concert task
    TaskScenario(
        task_id="stubhub/concerts/general/001",
        name="Concert Ticket Verification",
        description="Verify any concert ticket availability",
        url="https://www.stubhub.com/",
        task_prompt=(
            "Search for any upcoming concert. "
            "Find an event and verify ticket availability."
        ),
        queries=[[{
            "event_categories": ["concerts", "music"],
            "require_available": False,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="concerts",
        tags=["music", "concert", "live"],
    ),
    # Sports task  
    TaskScenario(
        task_id="stubhub/sports/nba/001",
        name="NBA Game Tickets",
        description="Verify NBA basketball game ticket availability",
        url="https://www.stubhub.com/",
        task_prompt=(
            "Search for a NBA Los Angeles Lakers basketball game. "
            "Navigate to an event page and verify ticket availability."
        ),
        queries=[[{
            "event_names": ["nba", "basketball", "lakers"],
            "event_categories": ["sports"],
            "require_available": False,
        }]],
        location="United States",
        timezone="America/New_York",
        category="sports",
        tags=["nba", "basketball", "sports"],
    ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/sports/f1_austin_friday/001",
    #     name="US F1 GP Friday Pass",
    #     description="Find tickets for a specific F1 race day",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Find tickets for the United States F1 GP Friday Only Pass in Austin on October 23, 2026."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["united states f1 gp", "friday only pass"],
    #             "cities": ["austin"],
    #             "dates": ["2026-10-23"],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="sports",
    #     tags=["formula 1", "racing", "friday pass"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/sports/f1_austin_budget/001",
    #     name="F1 Austin Budget Group",
    #     description="Find multiple tickets within a price limit",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "I need 3 tickets for the US F1 Grand Prix in Austin which are priced under 11,000 IUSDR each."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["united states f1 gp"],
    #             "cities": ["austin"],
    #             "ticket_quantities": [3],
    #             "max_price": 11000, 
    #             "currency": "INR",
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="sports",
    #     tags=["budget", "group booking", "f1"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/sports/f1_austin_section/001",
    #     name="F1 Austin Turn 12 Seats",
    #     description="Find tickets in a specific grandstand section",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Check for ticket availability in Section T12 for the United States F1 GP Friday event in Austin."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["united states f1 gp"],
    #             "cities": ["austin"],
    #             "sections": ["t12", "turn 12"], 
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="sports",
    #     tags=["seating", "grandstand", "specifics"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/concerts/post_malone_kc/001",
    #     name="Post Malone Kansas City",
    #     description="Find tickets for a specific stadium concert",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Find tickets for Post Malone at Kauffman Stadium in Kansas City on July 15, 2026."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["post malone"],
    #             "cities": ["kansas city"],
    #             "venues": ["kauffman stadium"],
    #             "dates": ["2026-07-15"],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="concerts",
    #     tags=["concert", "post malone", "stadium"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/concerts/post_malone_gbp/001",
    #     name="Post Malone Budget (GBP)",
    #     description="Find tickets with specific currency constraint",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Find availability of Post Malone tickets in Kansas City for July 15, 2026 that are priced under 400 GBP."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["post malone"],
    #             "cities": ["kansas city"],
    #             "dates": ["2026-07-15"],
    #             "max_price": 400, 
    #             "currency": "GBP",
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="concerts",
    #     tags=["budget", "currency", "gbp"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/concerts/post_malone_section/001",
    #     name="Post Malone Section 131",
    #     description="Find tickets in a specific section",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Check for ticket availability in Section 131, Row M for the Post Malone concert in Kansas City."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["post malone"],
    #             "cities": ["kansas city"],
    #             "sections": ["131", "section 131"], 
    #             "rows": ["m"],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="concerts",
    #     tags=["seating", "specifics", "post malone"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/theater/gatsby_kc_group/001",
    #     name="Great Gatsby Group Tickets",
    #     description="Find tickets for a large group",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "I need 6 tickets for The Great Gatsby theatre event in Kansas City on March 19, 2026."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["the great gatsby"],
    #             "cities": ["kansas city"],
    #             "dates": ["2026-03-19"],
    #             "ticket_quantities": [6],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="theater",
    #     tags=["group booking", "theater", "quantity"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/theater/gatsby_kc_budget/001",
    #     name="Great Gatsby Budget (GBP)",
    #     description="Find affordable tickets with specific currency",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Find tickets for The Great Gatsby at the Music Hall in Kansas City for under 80 GBP."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["the great gatsby"],
    #             "cities": ["kansas city"],
    #             "venues": ["municipal auditorium music hall", "music hall"],
    #             "max_price": 80, 
    #             "currency": "GBP",
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="theater",
    #     tags=["budget", "currency", "gbp"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/theater/gatsby_kc_section/001",
    #     name="Great Gatsby Balcony Seats",
    #     description="Find tickets in a specific section",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Check for tickets availability in the CBAL section (Row U) for The Great Gatsby in Kansas City."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["the great gatsby"],
    #             "cities": ["kansas city"],
    #             "sections": ["cbal", "balcony"], 
    #             "rows": ["u"],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="theater",
    #     tags=["seating", "specifics", "balcony"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/concerts/charlie_puth_sd/001",
    #     name="Charlie Puth San Diego Concert",
    #     description="Find tickets for a specific concert event",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Find tickets for Charlie Puth at Viejas Arena in San Diego on April 22, 2026."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["charlie puth"],
    #             "cities": ["san diego"],
    #             "venues": ["viejas arena"],
    #             "dates": ["2026-04-22"],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="concerts",
    #     tags=["concert", "charlie puth", "san diego"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/concerts/charlie_puth_budget/001",
    #     name="Charlie Puth Budget Ticket",
    #     description="Find a single ticket within a budget",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "I need 1 ticket for the Charlie Puth concert in San Diego on April 22, 2026 for under $140."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["charlie puth"],
    #             "cities": ["san diego"],
    #             "dates": ["2026-04-22"],
    #             "ticket_quantities": [1],
    #             "max_price": 140, 
    #             "currency": "USD",
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="concerts",
    #     tags=["budget", "single ticket", "usd"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/concerts/charlie_puth_bench/001",
    #     name="Charlie Puth Bench Seats",
    #     description="Find tickets in a specific seating section",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Check for ticket availability in the section of Bench D (Row 31) for the Charlie Puth concert in San Diego."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["charlie puth"],
    #             "cities": ["san diego"],
    #             "sections": ["bench d", "bench"], 
    #             "rows": ["31"],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="concerts",
    #     tags=["seating", "specifics", "bench"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/concerts/charlie_puth_instant/001",
    #     name="Charlie Puth Instant Download",
    #     description="Find tickets with specific delivery method",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Find tickets for Charlie Puth in San Diego on April 22, 2026 that can be downloadled instantly."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["charlie puth"],
    #             "cities": ["san diego"],
    #             "dates": ["2026-04-22"],
    #             "delivery_options": ["instant_download", "instant"],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="concerts",
    #     tags=["concert", "instant download", "delivery"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/concerts/charlie_puth_premium/001",
    #     name="Charlie Puth Premium Ticket",
    #     description="Find premium tier tickets within budget",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Find a premium ticket for the Charlie Puth concert in San Diego priced below or equal to $400."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["charlie puth"],
    #             "cities": ["san diego"],
    #             "dates": ["2026-04-22"],
    #             "max_price": 400, 
    #             "currency": "USD",
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="concerts",
    #     tags=["budget", "premium", "usd"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/concerts/charlie_puth_row_specific/001",
    #     name="Charlie Puth Row Specific",
    #     description="Find tickets in a specific row and section",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Check if there is a ticket available in Section EEE, Row 2 for Charlie Puth in San Diego."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["charlie puth"],
    #             "cities": ["san diego"],
    #             "sections": ["eee", "eeerow", "section eee"], 
    #             "rows": ["2"],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="concerts",
    #     tags=["seating", "specifics", "row"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/sports/nfl_browns_future/001",
    #     name="Cleveland Browns Future Game",
    #     description="Find tickets for a specific future dated listing",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Check whether 4 tickets are available for the Cleveland Browns game listed for March 3, 2027."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["cleveland browns", "cleveland browns tickets"],
    #             "dates": ["2027-03-03"],
    #             "ticket_quantities": [4],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="sports",
    #     tags=["nfl", "football", "group booking"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/sports/nfl_browns_budget/001",
    #     name="Cleveland Browns Budget",
    #     description="Find tickets within a price range",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Find tickets for the Cleveland Browns game in Cleveland and they should not cost more than $200."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["cleveland browns", "cleveland browns tickets"],
    #             "cities": ["cleveland"],
    #             "max_price": 200,
    #             "currency": "USD",
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="sports",
    #     tags=["budget", "nfl", "cleveland"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/sports/nfl_browns_section/001",
    #     name="Cleveland Browns Section 543",
    #     description="Find tickets in a specific stadium section",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Check for tickets in Section 543 for the Cleveland Browns event."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["cleveland browns", "cleveland browns tickets"],
    #             "cities": ["cleveland"],
    #             "sections": ["543", "section 543"],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="sports",
    #     tags=["seating", "specifics", "section"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/sports/nba_celtics_mavs/001",
    #     name="Celtics vs Mavericks Tickets",
    #     description="Verify availability for a specific NBA game",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Find tickets for the Dallas Mavericks vs Boston Celtics game at TD Garden on March 6, 2026."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["dallas mavericks", "boston celtics"],
    #             "cities": ["boston"],
    #             "venues": ["td garden"],
    #             "dates": ["2026-03-06"],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="sports",
    #     tags=["nba", "basketball", "boston"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/sports/world_cup_haiti_scotland/001",
    #     name="World Cup Haiti vs Scotland",
    #     description="Find tickets for a World Cup group stage match",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Check availability of tickets for the World Cup Group C match between Haiti and Scotland in Foxborough on June 13, 2026."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["haiti", "scotland"],
    #             "cities": ["foxborough"],
    #             "dates": ["2026-06-13"],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="sports",
    #     tags=["world cup", "soccer", "international"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/concerts/noah_kahan_fenway/001",
    #     name="Noah Kahan Fenway Park",
    #     description="Find tickets for a specific concert",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Are there any Noah Kahan tickets available for his Fenway Park show on July 10, 2026?"
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["noah kahan"],
    #             "cities": ["boston"],
    #             "venues": ["fenway park"],
    #             "dates": ["2026-07-10"],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="concerts",
    #     tags=["concert", "music", "boston"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/classical/la_phil_disney/001",
    #     name="LA Philharmonic Disney Hall",
    #     description="Find tickets for a specific classical concert",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Find tickets for the Los Angeles Philharmonic at Walt Disney Concert Hall "
    #         "on February 10, 2026."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["los angeles philharmonic", "la phil"],
    #             "venues": ["walt disney concert hall"],
    #             "dates": ["2026-02-10"],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="classical",
    #     tags=["concert", "classical", "los angeles"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/comedy/russell_peters_irvine/001",
    #     name="Russell Peters Comedy Check",
    #     description="Find comedy tickets near a specific area",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Check if Russell Peters is performing near Long Beach in April 2026."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["russell peters"],
    #             "cities": ["irvine", "long beach"],
    #             "dates": ["2026-04-23", "2026-04-24", "2026-04-25", "2026-04-26"],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="comedy",
    #     tags=["comedy", "standup", "near me"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/classical/long_beach_symphony/001",
    #     name="Long Beach Symphony Tickets",
    #     description="Find tickets for a specific local symphony event",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Find Long Beach Symphony tickets for the 'Pepe Romero Returns' event on Feb 28, 2026."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["long beach symphony", "pepe romero returns"],
    #             "cities": ["long beach"],
    #             "dates": ["2026-02-28"],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="classical",
    #     tags=["symphony", "local", "long beach"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/concerts/bts_tampa_budget/001",
    #     name="BTS Tampa Budget Tickets",
    #     description="Find tickets within a specific budget",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Search for BTS concert tickets in Tampa for under $150 on April 25, 2026."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["bts"],
    #             "cities": ["tampa"],
    #             "dates": ["2026-04-25"],
    #             "max_price": 150,
    #             "currency": "USD",
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="concerts",
    #     tags=["budget", "concert", "tampa"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/concerts/bts_tampa_parking/001",
    #     name="BTS Tampa Parking Pass",
    #     description="Find parking for a concert event",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Find a parking pass for the BTS concert in Tampa on April 25, 2026."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["parking passes only", "bts"],
    #             "cities": ["tampa"],
    #             "dates": ["2026-04-25"],
    #             "parking_only": True,
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="concerts",
    #     tags=["parking", "logistics", "bts"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/concerts/ed_sheeran_milwaukee/001",
    #     name="Ed Sheeran Milwaukee Concert",
    #     description="Find tickets for a specific concert event",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Find tickets for the Ed Sheeran concert in Milwaukee on June 25, 2026."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["ed sheeran"],
    #             "cities": ["milwaukee"],
    #             "dates": ["2026-06-25"],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="concerts",
    #     tags=["concert", "ed sheeran", "milwaukee"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/concerts/ed_sheeran_lawn_budget/001",
    #     name="Ed Sheeran Lawn Seats Budget",
    #     description="Find GA tickets within a specific price range",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Check for General Admission Lawn tickets for Ed Sheeran in Milwaukee under $170."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["ed sheeran"],
    #             "cities": ["milwaukee"],
    #             "sections": ["ga lawn", "lawn", "general admission"],
    #             "max_price": 200, 
    #             "currency": "USD",
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="concerts",
    #     tags=["budget", "lawn seats", "general admission"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/concerts/ed_sheeran_quantity/001",
    #     name="Ed Sheeran Group Booking",
    #     description="Find a specific quantity of tickets for a venue",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Check for the availability of 2 tickets for Ed Sheeran at the American Family Insurance Amphitheater on June 25, 2026."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["ed sheeran"],
    #             "venues": ["american family insurance amphitheater", "summerfest grounds"],
    #             "dates": ["2026-06-25"],
    #             "ticket_quantities": [2],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="concerts",
    #     tags=["quantity", "venue specific", "summerfest"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/sports/mlb_twins_broad/001",
    #     name="Minnesota Twins Any Game",
    #     description="Search for any available tickets for a specific team",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Find any available spring training tickets for the Minnesota Twins."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["minnesota twins"],
    #             "event_categories": ["sports"],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="sports",
    #     tags=["mlb", "minnesota twins", "flexible"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/sports/mlb_fort_myers_broad/001",
    #     name="Fort Myers Baseball Search",
    #     description="Find baseball games in a specific city",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Check for any tickets of the baseball games happening in Fort Myers, available in late February 2026."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["spring training", "baseball"],
    #             "cities": ["fort myers"],
    #             "dates": ["2026-02-20", "2026-02-21"], 
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="sports",
    #     tags=["mlb", "fort myers", "location search"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/festivals/tacos_tequila_group/001",
    #     name="Tacos & Tequila Group Tickets",
    #     description="Find tickets for a large group",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "I need 7 tickets for the Tacos and Tequila Festival in Milwaukee on May 30, 2026."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["tacos and tequila festival"],
    #             "cities": ["franklin", "milwaukee"],
    #             "dates": ["2026-05-30"],
    #             "ticket_quantities": [7],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="festivals",
    #     tags=["group booking", "quantity", "festival"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/festivals/tacos_tequila_budget/001",
    #     name="Tacos & Tequila GA Budget",
    #     description="Find GA tickets within a specific budget",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Check for General Admission tickets for the Tacos and Tequila Festival near Milwaukee for under 200 USD."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["tacos and tequila festival"],
    #             "cities": ["franklin", "milwaukee"],
    #             "sections": ["general admission", "ga"],
    #             "max_price": 200, 
    #             "currency": "USD",
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="festivals",
    #     tags=["budget", "general admission", "festival"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/sports/world_cup_match_60/001",
    #     name="World Cup Match 60 Search",
    #     description="Find a World Cup match using its specific match number",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Find tickets for the World Cup Group D Match 60 scheduled for June 25, 2026 in Santa Clara."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["world cup", "match 60", "paraguay", "australia"],
    #             "cities": ["santa clara"],
    #             "dates": ["2026-06-25"],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="sports",
    #     tags=["world cup", "soccer", "match number"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/sports/nba_warriors_lakers_budget/001",
    #     name="Warriors vs Lakers Budget",
    #     description="Find tickets for a marquee NBA matchup within a price range",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "I need 2 tickets for the Los Angeles Lakers at Golden State Warriors game in San Francisco on Feb 28, 2026, priced not more than 250 USD per ticket."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["los angeles lakers", "golden state warriors"],
    #             "cities": ["san francisco"],
    #             "venues": ["chase center"],
    #             "dates": ["2026-02-28"],
    #             "ticket_quantities": [2],
    #             "max_price": 250,
    #             "currency": "USD",
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="sports",
    #     tags=["nba", "basketball", "budget"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/theater/notebook_sf_valentines/001",
    #     name="The Notebook Musical Valentine's",
    #     description="Find theater tickets for a specific holiday date",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Find tickets for The Notebook musical at the Orpheum Theatre in San Francisco for the Valentine's Day show in 2026."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["the notebook"],
    #             "cities": ["san francisco"],
    #             "venues": ["orpheum theatre"],
    #             "dates": ["2026-02-14"],
    #             "require_available": True,
    #         }
    #     ]],
    #     location="United States",
    #     timezone="America/New_York",
    #     category="theater",
    #     tags=["theater", "musical", "holiday"],
    # ),
    # TaskScenario(
    #     task_id="navi_bench/stubhub/concerts/kid_cudi_budget/001",
    #     name="Kid Cudi Mountain View Deal",
    #     description="Find affordable concert tickets for a specific artist",
    #     url="https://www.stubhub.com/",
    #     task_prompt=(
    #         "Find tickets for Kid Cudi at Shoreline Amphitheatre in Mountain View on June 23, 2026 that are under 40 USD."
    #     ),
    #     queries=[[
    #         {
    #             "event_names": ["kid cudi"],
    #             "cities": ["mountain view"],
    #             "venues": ["shoreline amphitheatre"],
    #             "dates": ["2026-06-23"],
    #             "max_price": 40,
    #             "currency": "USD",
    #             "require_available": True,
    #         }
    #     ]],
    #     location="Pune, Maharashtra, India",
    #     timezone="Asia/Kolkata",
    #     category="concerts",
    #     tags=["concert", "budget", "hip hop"],
    # ),

]





# =============================================================================
# BROWSER MANAGER - Stealth browser configuration
# =============================================================================

class BrowserManager:
    """Manages browser lifecycle with stealth configuration."""
    
    def __init__(self, config: BrowserConfig = None):
        self.config = config or BrowserConfig()
        self.browser = None
        self.context = None
        self.page = None
    
    async def launch(self, playwright) -> tuple:
        """Launch browser with stealth configuration."""
        self.browser = await playwright.chromium.launch(
            headless=self.config.headless,
            args=self.config.launch_args,
        )
        
        self.context = await self.browser.new_context(
            viewport={
                "width": self.config.viewport_width,
                "height": self.config.viewport_height
            },
            user_agent=self.config.user_agent,
            locale=self.config.locale,
        )
        
        # Anti-detection scripts
        await self.context.add_init_script("""
            // Hide webdriver property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Override chrome.runtime
            window.chrome = { runtime: {} };
            
            // Override permissions query
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)
        
        self.page = await self.context.new_page()
        
        return self.browser, self.context, self.page
    
    async def close(self) -> None:
        """Close browser and cleanup."""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()


# =============================================================================
# RESULT REPORTER - Format and display results
# =============================================================================

class ResultReporter:
    """Formats and displays verification results."""
    
    @staticmethod
    def print_header(scenario: TaskScenario) -> None:
        """Print task header."""
        print("\n" + "=" * 80)
        print(f"STUBHUB VERIFICATION: {scenario.name}")
        print("=" * 80)
        print(f"Task ID:     {scenario.task_id}")
        print(f"Category:    {scenario.category}")
        print(f"Location:    {scenario.location}")
        print(f"Timezone:    {scenario.timezone}")
        print("-" * 80)
        print(f"TASK: {scenario.task_prompt}")
        print("-" * 80)
        print(f"Looking for: {scenario.queries[0][0]}")
        print("=" * 80)
    
    @staticmethod
    def print_instructions() -> None:
        """Print user instructions."""
        print("\n" + "-" * 40)
        print("INSTRUCTIONS:")
        print("-" * 40)
        print("1. Use the StubHub website to complete the task")
        print("2. Search for events and navigate to listings")
        print("3. The system tracks your navigation automatically")
        print("4. Press ENTER when ready to see verification results")
        print("-" * 40 + "\n")
    
    @staticmethod
    def print_result(result, evaluator: StubHubInfoGathering, scenario: TaskScenario) -> None:
        """Print verification result with debugging info."""
        print("\n" + "=" * 80)
        print("VERIFICATION RESULT")
        print("=" * 80)
        
        score_pct = result.score * 100
        status = "✅ PASS" if result.score >= 1.0 else "⚠️ PARTIAL" if result.score > 0 else "❌ FAIL"
        
        print(f"Status:           {status}")
        print(f"Score:            {score_pct:.1f}%")
        print(f"Queries Matched:  {result.n_covered}/{result.n_queries}")
        print(f"Pages Navigated:  {len(evaluator._navigation_stack)}")
        print("-" * 80)
        
        for i, covered in enumerate(result.is_query_covered):
            status_icon = "✓" if covered else "✗"
            print(f"  Query {i+1}: [{status_icon}] {'Matched' if covered else 'Not matched'}")
        
        # Show what we were looking for
        print("-" * 80)
        print("QUERY DETAILS:")
        query = scenario.queries[0][0]
        if "event_names" in query:
            print(f"  Looking for event names: {query['event_names']}")
        if "cities" in query:
            print(f"  Looking for cities: {query['cities']}")
        if "event_categories" in query:
            print(f"  Looking for categories: {query['event_categories']}")
        
        # Show scraped events for debugging
        print("-" * 80)
        print("EVENTS SCRAPED DURING SESSION:")
        all_events = []
        for page_infos in evaluator._all_infos:
            for event in page_infos:
                if event.get("eventName") and event not in all_events:
                    all_events.append(event)
        
        if all_events:
            for i, event in enumerate(all_events[:10], 1):  # Show first 10
                name = event.get("eventName", "unknown")
                city = event.get("city") or "?"
                venue = event.get("venue") or "?"
                date = event.get("date") or "?"
                price = event.get("price")
                source = event.get("source") or event.get("info") or "?"
                
                price_str = f"${price}" if price else "?"
                print(f"  {i}. {name}")
                print(f"     📍 {city} | 🏟️ {venue} | 📅 {date} | 💰 {price_str} | 🔗 {source}")
        else:
            print("  No events scraped (try navigating to more pages)")
        
        print("=" * 80 + "\n")
    
    @staticmethod
    def print_summary(results: list) -> None:
        """Print summary of all results."""
        if not results:
            return
        
        print("\n" + "=" * 80)
        print("SESSION SUMMARY")
        print("=" * 80)
        
        total = len(results)
        passed = sum(1 for r in results if r["score"] >= 1.0)
        
        print(f"Total Scenarios:  {total}")
        print(f"Passed:           {passed}")
        print(f"Success Rate:     {passed/total*100:.1f}%")
        print("=" * 80 + "\n")


# =============================================================================
# MAIN RUNNER
# =============================================================================

async def run_scenario(scenario: TaskScenario) -> dict:
    """Run a single verification scenario."""
    
    # Create evaluator
    task_config = generate_task_config_deterministic(
        mode="any",
        task=scenario.task_prompt,
        queries=scenario.queries,
        location=scenario.location,
        timezone=scenario.timezone,
        url=scenario.url,
    )
    
    evaluator = StubHubInfoGathering(queries=scenario.queries)
    reporter = ResultReporter()
    
    # Display task info
    reporter.print_header(scenario)
    reporter.print_instructions()
    
    input("Press ENTER to launch browser...")
    
    async with async_playwright() as p:
        # Launch browser
        browser_mgr = BrowserManager()
        browser, context, page = await browser_mgr.launch(p)
        
        # Initialize evaluator and attach context tracking
        await evaluator.reset()
        evaluator.attach_to_context(context)
        
        # Navigate to start URL
        logger.info(f"Opening {scenario.url}")
        await page.goto(scenario.url, timeout=60000, wait_until="domcontentloaded")
        
        # Initial page update
        await evaluator.update(page=page)
        
        print("\n🌐 Browser ready - you are now the agent!")
        print("Navigate through StubHub to complete the task.\n")
        
        # Wait for user completion
        await asyncio.to_thread(
            input, 
            "Press ENTER when you've completed the task... "
        )
        
        # Final evaluation
        try:
            await evaluator.update(page=page)
        except Exception as e:
            logger.warning(f"Final update failed: {e}")
        
        result = await evaluator.compute()
        
        # Close browser
        await browser_mgr.close()
    
    # Display results with scenario context
    reporter.print_result(result, evaluator, scenario)
    
    return {
        "task_id": scenario.task_id,
        "score": result.score,
        "n_covered": result.n_covered,
        "n_queries": result.n_queries,
        "pages_navigated": len(evaluator._navigation_stack),
    }


async def run_interactive_menu() -> None:
    """Run interactive scenario selection menu."""
    
    print("\n" + "=" * 80)
    print("STUBHUB TICKET VERIFICATION SYSTEM")
    print("=" * 80)
    print("\nAvailable scenarios:\n")
    
    for i, scenario in enumerate(SCENARIOS, 1):
        print(f"  [{i}] {scenario.name}")
        print(f"      {scenario.description}")
        print()
    
    print(f"  [A] Run all scenarios")
    print(f"  [Q] Quit")
    print()
    
    choice = input("Select scenario (1-{}, A, or Q): ".format(len(SCENARIOS))).strip().upper()
    
    results = []
    
    if choice == "Q":
        print("Goodbye!")
        return
    
    elif choice == "A":
        for scenario in SCENARIOS:
            result = await run_scenario(scenario)
            results.append(result)
            
            if scenario != SCENARIOS[-1]:
                cont = input("\nContinue to next scenario? (y/n): ").strip().lower()
                if cont != "y":
                    break
    
    elif choice.isdigit() and 1 <= int(choice) <= len(SCENARIOS):
        idx = int(choice) - 1
        result = await run_scenario(SCENARIOS[idx])
        results.append(result)
    
    else:
        print("Invalid choice. Please try again.")
        return
    
    # Print summary
    ResultReporter.print_summary(results)


async def main():
    """Main entry point."""
    
    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    
    try:
        await run_interactive_menu()
    except KeyboardInterrupt:
        print("\n\nInterrupted. Goodbye!")
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
