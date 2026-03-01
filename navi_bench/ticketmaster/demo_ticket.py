#!/usr/bin/env python
"""
Ticketmaster Ticket Availability Verification Demo

Human-in-the-loop verification system for Ticketmaster events.
Supports multi-tab browsing, real-time navigation tracking, and comprehensive
evaluation of agent navigation behavior, including anti-bot detection.

Features:
- Real-time page state tracking via navigation events
- Multi-tab/popup window support
- Stealth browser configuration (anti-detection)
- Ticketmaster-specific JS scraper (handles React classes & LD+JSON)
- Flexible query-based verification (e.g., exclude_resale)
- Debug output showing scraped events and bot-protection states

Author: NaviBench Team
"""

import asyncio
import sys
from dataclasses import dataclass, field

from playwright.async_api import async_playwright
from loguru import logger

# Import our new Ticketmaster evaluator
from navi_bench.ticketmaster.ticket_info_gathering import (
    TicketmasterInfoGathering,
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
    
    # Anti-detection arguments (Crucial for Ticketmaster)
    launch_args: list = field(default_factory=lambda: [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--start-maximized",
        "--no-sandbox",
        "--disable-web-security",
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
# TASK SCENARIOS - Ticketmaster Specific
# =============================================================================

SCENARIOS: list[TaskScenario] = [
    # PRIMARY TASK: General Concert Check
    TaskScenario(
        task_id="ticketmaster/concerts/coldplay/001",
        name="Coldplay Concert - Any Availability",
        description="Search for Coldplay concert tickets",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for Coldplay concert tickets. Find any upcoming Coldplay event and check ticket availability."
        ),
        queries=[[{
            "event_names": ["coldplay"],  
            "require_available": False,   # Sold out still counts as finding the right page
        }]],
        location="United States",
        timezone="America/New_York",
        category="concerts",
        tags=["coldplay", "concert", "music"],
    ),
    # TASK: Ticketmaster Specific - Primary Tickets Only (No Resale)
    TaskScenario(
        task_id="ticketmaster/sports/lakers/no_resale",
        name="LA Lakers - Primary Tickets Only",
        description="Search for Lakers tickets, excluding Verified Resale",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for a Los Angeles Lakers home game and find standard tickets only (filter out Verified Resale)."
        ),
        queries=[[{
            "event_names": ["lakers"], 
            "exclude_resale": True,       # Ticketmaster specific constraint!
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="sports",
        tags=["nba", "basketball", "primary_only"],
    ),
    # TASK: Budget constraint
    TaskScenario(
        task_id="ticketmaster/theater/hamilton/budget",
        name="Hamilton - Budget Tickets",
        description="Find affordable theater tickets",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for Hamilton theater tickets priced under $350."
        ),
        queries=[[{
            "event_names": ["hamilton"],
            "event_categories": ["theater", "arts"],
            "max_price": 350.0,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="theater",
        tags=["theater", "broadway", "budget"],
    ),
    TaskScenario(
        task_id="ticketmaster/comedy/jokoy_chappelle_soundcheck",
        name="Jo Koy & Dave Chappelle - Soundcheck Series",
        description="Search for the niche Soundcheck Series comedy show in Yellow Springs.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the 'Soundcheck Series' comedy event featuring Jo Koy and hosted by Dave Chappelle scheduled for either July 24 or July 25, 2026."
        ),
        queries=[[{
            "event_names": ["jo koy", "dave chappelle", "soundcheck series"], 
            "cities": ["yellow springs"],
            "dates": ["2026-07-24", "2026-07-25"],
            "require_available": False, 
        }]],
        location="United States",
        timezone="America/New_York",
        category="comedy",
        tags=["comedy", "standup", "specific_dates", "niche_location"],
    ),
    TaskScenario(
        task_id="ticketmaster/comedy/jo_koy_chappelle/yellow_springs",
        name="Jo Koy & Dave Chappelle - Yellow Springs",
        description="Find the specific Soundcheck Series comedy show in Ohio.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the 'Soundcheck Series' comedy event featuring Jo Koy and Dave Chappelle in Yellow Springs, OH. Navigate to the event page and check ticket availability."
        ),
        queries=[[{
            "event_names": ["jo koy", "dave chappelle"], 
            "cities": ["yellow springs"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="comedy",
        tags=["comedy", "jo koy", "dave chappelle", "location_filter"],
    ),
    TaskScenario(
        task_id="ticketmaster/festivals/bottlerock/saturday",
        name="BottleRock Napa Valley - Saturday Ticket",
        description="Find tickets for the middle day of a 3-day festival.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the BottleRock Napa Valley festival. Find the event specifically for the Saturday, May 23, 2026 date."
        ),
        queries=[[{
            "event_names": ["bottlerock napa valley"], 
            "dates": ["2026-05-23"],
            "cities": ["napa"],
            "require_available": False,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="festivals",
        tags=["festival", "music", "bottlerock", "date_constraint"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/backstreet_boys/standard_show",
        name="Backstreet Boys Sphere - Standard Concert",
        description="Navigate to the standard concert listing, avoiding the Suite Reservation page.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Backstreet Boys 'Into The Millennium' concert at the Sphere in Las Vegas. Find tickets for the Friday, July 17, 2026 show. Make sure you are looking at the actual concert tickets, not the Suite Reservations."
        ),
        queries=[[{
            "event_names": ["backstreet boys: into the millennium"],
            "dates": ["2026-07-17"],
            "cities": ["las vegas"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="concerts",
        tags=["concerts", "pop", "backstreet boys", "exact_match"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/backstreet_boys/suite_reservation",
        name="Backstreet Boys Sphere - Suite Reservation",
        description="Find the premium Suite Reservation listing for opening night.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Backstreet Boys at the Sphere in Las Vegas. Navigate specifically to the 'Suite Reservation' event page for their opening night on July 16, 2026."
        ),
        queries=[[{
            "event_names": ["suite reservation", "backstreet boys at sphere - suite reservation"],
            "dates": ["2026-07-16"],
            "cities": ["las vegas"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="concerts",
        tags=["concerts", "pop", "backstreet boys", "vip_suite"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/wwe/raw_seattle",
        name="WWE Monday Night Raw - Seattle",
        description="Navigate to a specific Monday Night Raw show on the tour schedule.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find tickets for WWE Monday Night Raw in Seattle. Verify ticket availability for the show on March 9, 2026."
        ),
        queries=[[{
            "event_names": ["monday night raw", "wwe"],
            "dates": ["2026-03-09"],
            "cities": ["seattle"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="sports",
        tags=["sports", "wrestling", "wwe", "date_constraint"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/wwe/smackdown_pittsburgh_standard",
        name="WWE SmackDown - Primary Tickets Pittsburgh",
        description="Find standard tickets for a Friday Night SmackDown show.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the WWE Friday Night Smackdown event in Pittsburgh on March 27, 2026. Look for only the standard admission tickets."
        ),
        queries=[[{
            "event_names": ["smackdown", "friday night smackdown"],
            "dates": ["2026-03-27"],
            "cities": ["pittsburgh"],
            "exclude_resale": True,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="sports",
        tags=["sports", "wrestling", "wwe", "primary_only"],
    ),
    TaskScenario(
        task_id="ticketmaster/family/monster_jam/discovery_dates",
        name="Monster Jam - Discovery Date Range",
        description="Test the date range filter on the discovery page.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for Monster Jam on Ticketmaster and use the date filter to show events from March 15 to March 27, 2026."
        ),
        queries=[[{
            "event_names": ["monster jam"], 
            "dates": ["2026-03-15"], # The is_date_satisfied fallback will pass this
            "require_available": False,
        }]],
        location="United States",
        timezone="America/New_York",
        category="family",
        tags=["family", "motorsports", "monster jam", "date_filter", "discovery"],
    ),
    TaskScenario(
        task_id="ticketmaster/family/monster_jam/grand_rapids_freestyle",
        name="Monster Jam Freestyle Mania - Grand Rapids",
        description="Find the 'Freestyle Mania' specific variant in Grand Rapids.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for 'Monster Jam Freestyle Mania' in Grand Rapids."
        ),
        queries=[[{
            "event_names": ["monster jam freestyle mania"],
            "cities": ["grand rapids"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Detroit",
        category="family",
        tags=["family", "motorsports", "monster jam", "location_filter"],
    ),
    TaskScenario(
        task_id="ticketmaster/family/monster_jam/hartford_exact",
        name="Monster Jam - Hartford March 21",
        description="Navigate to the exact Saturday show in Hartford.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find tickets for the Monster Jam event in Hartford exactly on March 21, 2026."
        ),
        queries=[[{
            "event_names": ["monster jam"],
            "cities": ["hartford"],
            "dates": ["2026-03-21"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="family",
        tags=["family", "motorsports", "monster jam", "exact_match"],
    ),
    TaskScenario(
        task_id="ticketmaster/family/monster_jam/tucson_budget",
        name="Monster Jam - Tucson Budget Tickets",
        description="Find affordable tickets using price filters in Tucson.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Look for Monster Jam tickets in Tucson on March 20, 2026. Adjust the maximum price filter to $60 or find individual tickets listed under $60."
        ),
        queries=[[{
            "event_names": ["monster jam"],
            "cities": ["tucson"],
            "dates": ["2026-03-20"],
            "max_price": 60.0,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Phoenix",
        category="family",
        tags=["family", "motorsports", "monster jam", "budget", "price_filter"],
    ),
    TaskScenario(
        task_id="ticketmaster/family/monster_jam/biloxi_standard",
        name="Monster Jam - Biloxi Standard Only",
        description="Ensure verified resale is unchecked for the Biloxi show.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for Monster Jam in Biloxi on March 15, 2026. Ensure you filter out verified resale tickets and verify standard ticket availability."
        ),
        queries=[[{
            "event_names": ["monster jam"],
            "cities": ["biloxi"],
            "dates": ["2026-03-15"],
            "exclude_resale": True,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Chicago",
        category="family",
        tags=["family", "motorsports", "monster jam", "primary_only"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/dodgers/royals_budget",
        name="Dodgers @ Royals - Under $40",
        description="Find budget tickets for the Dodgers away game in Kansas City.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Los Angeles Dodgers away game against the Kansas City Royals on March 17, 2026. Find tickets priced less than $40."
        ),
        queries=[[{
            "event_names": ["dodgers", "royals"], 
            "dates": ["2026-03-17"],
            "max_price": 40.00,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="sports",
        tags=["mlb", "baseball", "dodgers", "budget"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/dodgers/spring_training_surprise",
        name="Dodgers Spring Training - Surprise AZ",
        description="Find the specific Spring Training game in Surprise, Arizona.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for Los Angeles Dodgers tickets for their Spring Training game against the Chicago White Sox happening at Surprise Stadium in Arizona on March 15, 2026."
        ),
        queries=[[{
            "event_names": ["dodgers", "white sox"],
            "dates": ["2026-03-15"],
            "cities": ["surprise"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="sports",
        tags=["mlb", "spring_training", "location_filter"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/dodgers/vs_athletics",
        name="Dodgers vs. The A's - May 13",
        description="Navigate to a specific home game against The A's.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find tickets for the Los Angeles Dodgers home game against The A's on May 13, 2026."
        ),
        queries=[[{
            "event_names": ["dodgers", "a's", "athletics"],
            "dates": ["2026-05-13"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="sports",
        tags=["mlb", "dodgers", "exact_match"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/dodgers/vs_diamondbacks_flexible",
        name="Dodgers vs. Diamondbacks - Flexible Date",
        description="Find a game against the Diamondbacks on either May 19 or May 21.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Look for an upcoming Los Angeles Dodgers game against the Arizona Diamondbacks. Check availability for either the May 19 or May 21, 2026 game."
        ),
        queries=[[{
            "event_names": ["dodgers", "diamondbacks"],
            "dates": ["2026-05-19", "2026-05-21"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="sports",
        tags=["mlb", "dodgers", "flexible_dates"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/dodgers/royals_4_tickets",
        name="Dodgers @ Royals - Exactly 4 Tickets",
        description="Ensure the agent selects exactly 4 tickets from the filter dropdown.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find exactly 4 tickets for the Los Angeles Dodgers at Kansas City Royals game on March 17, 2026."
        ),
        queries=[[{
            "event_names": ["dodgers", "royals"],
            "dates": ["2026-03-17"],
            "ticket_quantities": [4],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Chicago",
        category="sports",
        tags=["mlb", "quantity_filter", "group_tickets"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/dodgers/white_sox_primary",
        name="Dodgers vs White Sox - Standard Tickets",
        description="Find standard admission tickets, excluding verified resale.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find tickets for the March 15, 2026 game between the Dodgers and White Sox. Filter the results to exclude 'Verified Resale' and only show Standard tickets."
        ),
        queries=[[{
            "event_names": ["dodgers", "white sox"],
            "dates": ["2026-03-15"],
            "exclude_resale": True,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Phoenix",
        category="sports",
        tags=["mlb", "primary_only", "spring_training"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/mlb/kansas_city_discovery",
        name="MLB Discovery - Kansas City March 17",
        description="Verify location and date filters on the sports discovery page.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for any Dodgers/Royals game in Kansas City happening on 17th March 2026."
        ),
        queries=[[{
            "event_categories": ["sports"],
            "cities": ["kansas city"],
            "dates": ["2026-03-17"],
            "require_available": False, # Agent passes just by setting the UI filters correctly
        }]],
        location="United States",
        timezone="America/Chicago",
        category="sports",
        tags=["sports", "discovery", "location_filter", "date_filter"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/bruno_mars/strict_budget_pair",
        name="Bruno Mars - Pair between $600 and $1000",
        description="Find exactly 2 tickets within a specific high-end price range.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Bruno Mars 'The Romantic Tour' concert on April 18, 2026 for exactly 2 tickets priced between $600 and $1000."
        ),
        queries=[[{
            "event_names": ["bruno mars", "the romantic tour"], 
            "dates": ["2026-04-18"],
            "ticket_quantities": [2],
            "min_price": 600.00,
            "max_price": 1000.00,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="concerts",
        tags=["pop", "bruno mars", "price_range", "quantity_filter"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/bruno_mars/premium_resale",
        name="Bruno Mars - Premium Resale Tickets",
        description="Find high-end verified resale tickets over $700.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for Bruno Mars tickets for his April 18, 2026 show. Ensure the 'Verified Resale' filter is active, and find tickets priced over $700."
        ),
        queries=[[{
            "event_names": ["bruno mars"],
            "dates": ["2026-04-18"],
            "require_resale": True,
            "min_price": 700.00,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="concerts",
        tags=["pop", "bruno mars", "resale_only", "premium_price"],
    ),
    # 3. Tests row-specific matching
    TaskScenario(
        task_id="ticketmaster/concerts/bruno_mars/front_rows",
        name="Bruno Mars - Rows 9 or 10",
        description="Find tickets specifically in Row 9 or Row 10.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Bruno Mars concert on April 18, 2026. Find available tickets specifically located in Row 9 or Row 10."
        ),
        queries=[[{
            "event_names": ["bruno mars"],
            "dates": ["2026-04-18"],
            "rows": ["9", "10"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Chicago",
        category="concerts",
        tags=["pop", "bruno mars", "row_constraint"],
    ),
    TaskScenario(
        task_id="ticketmaster/theater/mj/matinee",
        name="MJ The Musical - 1:00 PM Matinee",
        description="Navigate to a specific matinee performance of a Broadway show.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for 'MJ' the musical at the Neil Simon Theatre in New York on March 18, 2026 and check availability."
        ),
        queries=[[{
            "event_names": ["mj"],
            "cities": ["new york"],
            "dates": ["2026-03-18"],
            "times": ["13:00"], # Evaluator parses 1:00 PM as 13:00
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="theater",
        tags=["theater", "broadway", "mj", "time_constraint"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/bruno_mars/cheap_ticket",
        name="Bruno Mars - Under $650",
        description="Find a budget ticket for a high-demand concert.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for Bruno Mars 'The Romantic Tour' for April 18, 2026. Find any available ticket that costs less than $650."
        ),
        queries=[[{
            "event_names": ["bruno mars"],
            "dates": ["2026-04-18"],
            "max_price": 650.00,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="concerts",
        tags=["pop", "bruno mars", "budget", "max_price"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/jonas_brothers/lincoln_budget",
        name="Jonas Brothers Lincoln - Under $250",
        description="Find budget tickets for the Jonas Brothers concert in Lincoln, CA.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Jonas Brothers concert at The Venue at Thunder Valley Casino Resort in Lincoln, CA on May 29, 2026. Find tickets that cost less than $250."
        ),
        queries=[[{
            "event_names": ["jonas brothers"], 
            "dates": ["2026-05-29"],
            "cities": ["lincoln"],
            "max_price": 250.00,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="concerts",
        tags=["pop", "jonas brothers", "budget"],
    ),
    TaskScenario(
        task_id="ticketmaster/festivals/boots_and_hearts/friday_pass",
        name="Boots And Hearts Festival - Friday Pass",
        description="Find a single-day festival pass featuring the Jonas Brothers.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Boots And Hearts Music Festival in Oro-Medonte, ON, Canada on Friday, August 7, 2026 and check ticket availability."
        ),
        queries=[[{
            "event_names": ["boots and hearts"],
            "dates": ["2026-08-07"],
            "cities": ["oro-medonte"],
            "require_available": True,
        }]],
        location="Canada",
        timezone="America/Toronto",
        category="festivals",
        tags=["festival", "country", "jonas brothers", "single_day"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/jonas_brothers/hometown_jacksonville",
        name="Jonas Brothers - Greetings From Your Hometown",
        description="Find the specifically named 'Hometown' variant event in Jacksonville.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Jonas Brothers 'Greetings From Your Hometown' concert happening at Daily's Place Amphitheater in Jacksonville on December 30, 2025."
        ),
        queries=[[{
            "event_names": ["jonas 20", "greetings from your hometown"],
            "dates": ["2025-12-30"],
            "cities": ["jacksonville"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="concerts",
        tags=["pop", "jonas brothers", "exact_match", "special_event"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/jonas_brothers/aspen_private",
        name="Jonas Brothers - Aspen Private Venue",
        description="Locate a concert happening at an undisclosed or private venue.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Jonas Brothers concert scheduled for October 4, 2025, in Aspen, CO."
        ),
        queries=[[{
            "event_names": ["jonas brothers"],
            "dates": ["2025-10-04"],
            "cities": ["aspen"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Denver",
        category="concerts",
        tags=["pop", "jonas brothers", "location_filter", "private_venue"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/jonas_brothers/ziegfeld_new_york",
        name="Jonas Brothers - Ziegfeld Ballroom NY",
        description="Find standard admission tickets for the New York ballroom show.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find tickets for the Jonas Brothers performance at the Ziegfeld Ballroom in New York on November 15, 2025, specifically standard tickets."
        ),
        queries=[[{
            "event_names": ["jonas brothers"],
            "dates": ["2025-11-15"],
            "cities": ["new york"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="concerts",
        tags=["pop", "jonas brothers", "new_york", "standard_tickets"],
    )

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
        
        # Anti-detection scripts - highly important for PerimeterX/DataDome
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
            
            // WebGL fingerprint spoofing
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                return getParameter.call(this, parameter);
            };
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
        print(f"TICKETMASTER VERIFICATION: {scenario.name}")
        print("=" * 80)
        print(f"Task ID:     {scenario.task_id}")
        print(f"Category:    {scenario.category}")
        print(f"Location:    {scenario.location}")
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
        print("1. Use the Ticketmaster website to complete the task")
        print("2. Search for events and navigate to listings")
        print("3. Watch out for 'Pardon the Interruption' anti-bot screens")
        print("4. Press ENTER in this terminal when ready to see verification results")
        print("-" * 40 + "\n")
    
    @staticmethod
    def print_result(result, evaluator: TicketmasterInfoGathering, scenario: TaskScenario) -> None:
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
        
        # Check for bot blocks in the stack
        bot_blocks = [p for p in evaluator._navigation_stack if p.get("anti_bot") == "blocked_perimeterx"]
        if bot_blocks:
            print("🚨 WARNING: PerimeterX Anti-Bot Block Detected during session! 🚨")
            print("-" * 80)

        for i, covered in enumerate(result.is_query_covered):
            status_icon = "✓" if covered else "✗"
            print(f"  Query {i+1}: [{status_icon}] {'Matched' if covered else 'Not matched'}")
        
        # Show scraped events for debugging
        print("-" * 80)
        print("EVENTS SCRAPED DURING SESSION:")
        all_events = []
        for page_infos in evaluator._all_infos:
            for event in page_infos:
                if event.get("eventName") and event.get("eventName") != "unknown" and event not in all_events:
                    all_events.append(event)
        
        if all_events:
            for i, event in enumerate(all_events, 1):  # Show first 10
                name = event.get("eventName", "unknown").title()
                city = event.get("city") or "?"
                date = event.get("date") or "?"
                price = event.get("price")
                is_resale = event.get("isResale", False)
                source = event.get("source") or "?"
                
                price_str = f"${price}" if price else "?"
                resale_str = "🔄 Resale" if is_resale else "🎫 Standard"
                print(f"  {i}. {name}")
                print(f"     📍 {city} | 📅 {date} | 💰 {price_str} | {resale_str} | 🔗 {source}")
        else:
            print("  No usable events scraped (Check if blocked by anti-bot)")
        
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
    
    evaluator = TicketmasterInfoGathering(queries=scenario.queries)
    reporter = ResultReporter()
    
    reporter.print_header(scenario)
    reporter.print_instructions()
    
    input("Press ENTER to launch browser...")
    
    async with async_playwright() as p:
        browser_mgr = BrowserManager()
        browser, context, page = await browser_mgr.launch(p)
        
        await evaluator.reset()
        evaluator.attach_to_context(context)
        
        logger.info(f"Opening {scenario.url}")
        # Ticketmaster load times can be rough, handle timeouts gracefully
        try:
            await page.goto(scenario.url, timeout=60000, wait_until="domcontentloaded")
        except Exception as e:
            logger.warning(f"Initial navigation timeout/error (normal for TM): {e}")
            
        await evaluator.update(page=page)
        
        print("\n🌐 Browser ready - you are now the agent!")
        print("Navigate through Ticketmaster to complete the task.\n")
        
        await asyncio.to_thread(
            input, 
            "Press ENTER when you've completed the task... "
        )
        
        try:
            await evaluator.update(page=page)
        except Exception as e:
            logger.warning(f"Final update failed: {e}")
        
        result = await evaluator.compute()
        await browser_mgr.close()
    
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
    print("TICKETMASTER TICKET VERIFICATION SYSTEM")
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
    
    ResultReporter.print_summary(results)


async def main():
    """Main entry point."""
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