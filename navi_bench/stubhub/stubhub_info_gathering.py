"""StubHub info gathering verifier for event ticket searches.

This module provides functionality to verify AI agent ticket search results on StubHub
by gathering event information through JavaScript scraping and matching against expected queries.
"""

import functools
import itertools
import random
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from beartype import beartype
from loguru import logger
from playwright.async_api import Page
from pydantic import BaseModel
from typing_extensions import TypedDict

from navi_bench.base import BaseMetric, BaseTaskConfig, UserMetadata, get_import_path
from navi_bench.dates import initialize_placeholder_map, initialize_user_metadata, render_task_statement


class SingleCandidateQuery(TypedDict, total=False):
    """Single event query with specific criteria."""
    # Event Search Filters
    event_name: str | None
    event_category: str | None  # concerts, sports, theater, comedy, festivals
    date: str | None
    time: str | None
    venue: str | None
    city: str | None
    
    # Ticket Listing Filters
    min_tickets: int | None
    max_price: float | None
    min_price: float | None
    section: str | None
    zone: str | None
    row: str | None
    aisle_seat: bool | None
    
    # Ticket Type Filters
    ticket_type: str | None  # standard, vip, premium, general_admission, standing, seated
    parking_only: bool | None
    accessible_seating: bool | None
    
    # Delivery Filters
    delivery_type: str | None  # instant_download, electronic, mobile_transfer, physical, will_call
    instant_download_only: bool | None
    
    # Special Filters
    vip_packages: bool | None
    includes_extras: bool | None
    price_with_fees: bool | None
    
    # Sorting
    sort_order: str | None  # recommended, price_low_to_high, price_high_to_low, best_value, best_seats
    
    # Availability (NEW: if False, sold-out events still count as matches)
    require_available: bool | None  # Default False - agent gets credit even if event is sold out


class MultiCandidateQuery(TypedDict, total=False):
    """Multi-option event query allowing alternatives."""
    # Event Search Filters
    event_names: list[str] | None
    event_categories: list[str] | None  # concerts, sports, theater, comedy, festivals
    domain: list[str] | None  # Alias for event_categories (concerts, sports, theater)
    dates: list[str] | None
    date_range: str | None  # today, this-weekend, this-week, this-month
    times: list[str] | None
    venues: list[str] | None
    cities: list[str] | None
    
    # Ticket Listing Filters
    min_tickets: int | None
    max_tickets: int | None
    ticket_quantities: list[int] | None  # Exact quantities: [2] means exactly 2 tickets
    max_price: float | None
    min_price: float | None
    currency: str | None  # USD, INR, EUR, GBP - for currency-aware matching
    sections: list[str] | None
    zones: list[str] | None  # Lower Level, Upper Deck, Floor, etc.
    rows: list[str] | None
    aisle_seat: bool | None
    
    # Ticket Type Filters
    ticket_types: list[str] | None  # standard, vip, premium, general_admission, standing, seated
    parking_only: bool | None
    accessible_seating: bool | None
    
    # Delivery Filters
    delivery_types: list[str] | None  # instant_download, electronic, mobile_transfer, physical, will_call
    instant_download_only: bool | None
    
    # Special Filters
    vip_packages: bool | None
    includes_extras: bool | None
    price_with_fees: bool | None
    
    # Sorting
    sort_order: str | None  # recommended, price_low_to_high, price_high_to_low, best_value, best_seats
    
    # Availability (NEW: if False, sold-out events still count as matches)
    require_available: bool | None  # Default False - agent gets credit even if event is sold out
    
    # URL-based verification (verify agent applied correct filters via URL)
    url_sections: list[str] | None  # Verify agent clicked correct map section(s)
    url_quantity: int | None  # Verify agent set correct ticket quantity
    url_ticket_classes: list[str] | None  # Verify agent selected correct ticket class/zone
    
    # Auth requirement
    require_login: bool | None  # Task requires logged-in state
    
    # Page type requirement (can be single string or list of acceptable types)
    require_page_type: str | list[str] | None  # event_listing, event_modal, search_results, checkout, etc.
    
    # Availability status filter
    availability_statuses: list[str] | None  # available, presale, limited, sold_out, waitlist


class InputDict(TypedDict, total=False):
    """Input for update method."""
    page: Page


class InfoDict(TypedDict, total=False):
    """Scraped event information from JavaScript - comprehensive."""
    # Basic Info
    url: str
    eventName: str
    eventCategory: str  # concerts, sports, theater, comedy, festivals
    
    # Date/Time
    date: str
    time: str
    dateRange: str  # today, this-weekend, this-week, this-month
    
    # Location
    venue: str
    city: str
    state: str
    country: str
    
    # Ticket Details
    section: str
    zone: str
    row: str
    seat: str
    aisleSeat: bool
    
    # Pricing
    price: float
    priceWithFees: float
    faceValue: float
    
    # Quantity
    ticketCount: int
    availableQuantities: list[int]
    
    # Ticket Type
    ticketType: str  # standard, vip, premium, general_admission
    isVIP: bool
    isAccessible: bool
    isParkingPass: bool
    
    # Delivery
    deliveryType: str  # instant_download, electronic, mobile_transfer, physical, will_call
    isInstantDownload: bool
    
    # Extras
    includesExtras: bool
    extraDetails: str
    
    # Availability Status
    info: str  # available, sold_out, limited, waitlist, presale
    totalListings: int
    
    # Seller Info
    sellerRating: float
    sellerType: str  # individual, professional
    
    # URL Filter State (scraped from URL params)
    urlSections: list[str]  # Section IDs from sections= param
    urlQuantity: int  # Quantity from quantity= param
    urlTicketClasses: list[str]  # Ticket class IDs from ticketClasses= param
    urlListingId: str  # Specific listing from listingId= param
    urlRows: list[str]  # Row filters from rows= param
    urlSeatTypes: list[str]  # Seat type filters from seatTypes= param
    urlMinPrice: float  # Min price filter from URL
    urlMaxPrice: float  # Max price filter from URL
    urlSort: str  # Sort order from URL
    
    # Page Metadata
    loginStatus: str  # logged_in, logged_out, unknown
    pageType: str  # event_listing, search_results, checkout, home, other
    currency: str  # USD, INR, EUR, GBP
    parsedTime: str  # Normalized time in HH:MM format
    eventId: str  # Event ID extracted from URL
    
    # Price Classification
    priceTier: str  # budget, mid, premium, luxury
    
    # Row and Seat Info
    extractedRow: str  # Row number/letter extracted from text
    extractedSeats: str  # Seat numbers extracted from text
    
    # Additional Flags
    isResale: bool  # True if resale ticket
    faceValue: float  # Face value of ticket if shown
    ticketsTogether: bool  # True if seats are consecutive
    isPresale: bool  # True if presale event
    
    # Gap-Bridging Fields
    recommendedToggleOn: bool  # True if Recommended toggle is ON
    filterPanelState: dict  # {isOpen, hasActiveFilters, activeFilterCount, hasClearButton}
    loadingState: dict  # {isLoading, spinnerCount, noResults}
    obstructedView: bool  # True if obstructed view, False if clear view
    ageRestriction: str  # 21+, 18+, all_ages, restricted
    listingAgeHours: int  # Listing age in hours
    isQuickPick: bool  # True if featured/quick pick listing
    dealRating: str  # best_value, fair, expensive
    viewQuality: float  # View quality 0-100 scale
    
    # Availability Status (detected from page content)
    availabilityStatus: str  # available, sold_out, presale, waitlist, limited, cancelled, rescheduled
    
    # LD+JSON Structured Data Fields
    source: str  # "ld+json", "dom", "structured_data", "category_page"
    country: str  # Country from LD+JSON location data
    priceRange: dict  # {low, high, currency} from LD+JSON offers


class FinalResult(BaseModel):
    """Final verification result."""
    score: float
    n_queries: int
    n_covered: int
    queries: list[list[MultiCandidateQuery]]
    is_query_covered: list[bool]


@beartype
class StubHubInfoGathering(BaseMetric):
    """Gather event ticket information from StubHub to evaluate query coverage."""

    def __init__(self, queries: list[list[MultiCandidateQuery]]) -> None:
        super().__init__()
        self.queries = queries
        self._all_infos: list[list[InfoDict]] = []
        self._is_query_covered: list[bool] = [False] * len(queries)
        self._unavailable_evidences: list[list[list[InfoDict]]] = [
            [[] for _ in alternative_conditions] for alternative_conditions in queries
        ]
        self._navigation_stack: list[dict] = [] 
        self._tracked_pages: set = set()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(queries={self.queries})"

    @functools.cached_property
    def js_script(self) -> str:
        """Load the JavaScript scraper."""
        with open(Path(__file__).parent / "stubhub_info_gathering.js", "r") as f:
            return f.read()

    async def reset(self) -> None:
        """Reset all tracking state."""
        self._all_infos = []
        self._is_query_covered = [False] * len(self.queries)
        self._unavailable_evidences = [[[] for _ in alternative_conditions] for alternative_conditions in self.queries]
        # Navigation stack for page-type based matching (walk backwards to find event_listing)
        # Each entry: {"url": str, "page_type": str, "infos": list[InfoDict]}
        self._navigation_stack: list[dict] = []
        # Track pages for attach_to_context
        self._tracked_pages: set = set()
    
    def attach_to_context(self, context) -> None:
        """
        Attach automatic navigation tracking to a browser context.
        
        This enables self-contained tracking - all page navigations and new tabs
        will be automatically tracked without the caller needing to set up handlers.
        
        Usage:
            verifier = StubHubInfoGathering(queries=queries)
            await verifier.reset()
            verifier.attach_to_context(context)  # Auto-tracks everything
            
            # ... user navigates ...
            
            result = await verifier.compute()
        
        Args:
            context: Playwright BrowserContext to attach tracking to
        """
        import asyncio
        
        async def track_page(page) -> None:
            """Attach navigation tracking to a single page."""
            page_id = id(page)
            if page_id in self._tracked_pages:
                return
            self._tracked_pages.add(page_id)
            
            async def on_frame_navigated(frame):
                """Handle navigation events on this page."""
                if frame != page.main_frame:
                    return  # Only track main frame
                
                try:
                    logger.info(f"[NAV] {page.url[:80]}...")
                    await self.update(page=page)
                except Exception as e:
                    logger.warning(f"Update failed: {e}")
            
            page.on("framenavigated", lambda f: asyncio.create_task(on_frame_navigated(f)))
            logger.info(f"Tracking attached to page: {page.url[:60]}...")
        
        # Track existing pages
        for page in context.pages:
            import asyncio
            asyncio.create_task(track_page(page))
        
        # Track new pages (tabs/popups)
        context.on("page", lambda p: asyncio.create_task(track_page(p)))

    async def update(self, **kwargs) -> None:
        """Update with new page information."""
        inputs: InputDict = kwargs
        page = inputs["page"]
        url = page.url
        
        # ========== WAIT FOR ELEMENTS (from friend's approach) ==========
        # This prevents empty results on dynamic pages by waiting for content to load
        
        # On event/listings pages: wait for ticket listings to appear
        if "/event/" in url:
            try:
                await page.wait_for_selector(
                    '[data-listing-id], [aria-label*="ticket"], [data-testid*="listing"], [class*="listing"]',
                    timeout=15000
                )
                logger.info("Found ticket listings on event page")
            except Exception:
                logger.info("No ticket listings found yet, proceeding anyway")
        
        # On search pages: wait for search results grid
        if "/secure/Search" in url:
            try:
                await page.wait_for_selector(
                    '[data-testid="primaryGrid"] li[data-expanded], [data-testid="primaryGrid"] li',
                    timeout=15000
                )
                logger.info("Found search results grid")
            except Exception:
                logger.info("No search grid found, proceeding anyway")
        
        # On performer/category pages: wait for event cards
        if "/performer/" in url or "/grouping/" in url or "-tickets" in url:
            try:
                await page.wait_for_selector(
                    'a[href*="/event/"], [class*="EventItem"], [data-testid*="event"]',
                    timeout=15000
                )
                logger.info("Found event cards on category page")
            except Exception:
                logger.info("No event cards found, proceeding anyway")
        
        # ========== RUN JAVASCRIPT SCRAPER ==========
        infos: list[InfoDict] = await page.evaluate(self.js_script)
        logger.info(f"StubHubInfoGathering.update gathered {len(infos)} intermediate infos: {infos}")

        self._all_infos.append(infos)
        
        # ========== DETERMINE PAGE TYPE ==========
        if "/event/" in url and any(info.get("pageType") == "event_listing" for info in infos):
            page_type = "event_listing"
        elif "/secure/Search" in url:
            page_type = "search_results"
        elif "/performer/" in url or "/grouping/" in url or "-tickets" in url:
            page_type = "event_category"
        else:
            page_type = infos[0].get("pageType", "unknown") if infos else "unknown"
        
        # ========== SMART STACK MANAGEMENT (Multi-Tab Safe) ==========
        # Normalize URL by removing query params for dedup (keep path)
        base_url = url.split("?")[0]
        
        # Check if this page (by base URL and type) already exists in stack
        existing_idx = None
        for idx, entry in enumerate(self._navigation_stack):
            if entry["base_url"] == base_url and entry["page_type"] == page_type:
                existing_idx = idx
                break
        
        page_entry = {
            "url": url,
            "base_url": base_url,
            "page_type": page_type,
            "infos": infos,
            "timestamp": len(self._navigation_stack)  # Ordering for priority
        }
        
        if existing_idx is not None:
            # Update existing entry with fresh data (same page revisited)
            self._navigation_stack[existing_idx] = page_entry
            logger.info(f"Page type: {page_type} (updated existing, stack depth: {len(self._navigation_stack)})")
        else:
            # New page - push to stack
            self._navigation_stack.append(page_entry)
            logger.info(f"Page type: {page_type} (new page, stack depth: {len(self._navigation_stack)})")
        
        # Log info for debugging (limit to avoid spam)
        for info in infos[:5]:
            logger.info(f"    📋 Found: {info.get('eventName', 'unknown')}")

        # ========== NO IMMEDIATE MATCHING ==========
        # All matching is deferred to compute() for accurate final-state evaluation

    async def compute(self) -> FinalResult:
        """
            Compute final coverage score by walking backwards through navigation stack.
            
            STACK TRAVERSAL LOGIC:
            The agent might visit many pages: Home -> Search -> Event A -> Event B -> Checkout.
            To verify success, we need to know the state of the *last valid event* the user viewed.
            
            1. We iterate the stack in REVERSE (LIFO).
            2. We look for the first 'event_listing' page type. This represents the final 
            event selection the agent arrived at.
            3. If no 'event_listing' is found (e.g., agent only searched but didn't click),
            we fall back to 'category_page' data to check if they at least found the
            right list of events (useful for validating "sold out" detection).
        """
        
        logger.info(f"Computing with {len(self._navigation_stack)} pages in navigation stack")
        
        # ========== WALK BACKWARDS THROUGH STACK ==========
        # Priority 1: Find most recent event_listing page and check strictly
        # Priority 2: Fall back to category pages for sold-out support
        
        event_listing_found = False
        category_page_infos: list[InfoDict] = []
        
        # Walk backwards (most recent first)
        for page_visit in reversed(self._navigation_stack):
            page_type = page_visit["page_type"]
            page_url = page_visit["url"]
            page_infos = page_visit["infos"]
            
            if page_type == "event_listing" and not event_listing_found:
                # Found an event listing page - check STRICTLY
                event_listing_found = True
                logger.info(f"Found event_listing in stack, checking strictly: {page_url[:80]}...")
                
                for i, alternative_conditions in enumerate(self.queries):
                    if self._is_query_covered[i]:
                        continue
                    
                    for info in page_infos:
                        if self._check_alternative_conditions(i, alternative_conditions, info):
                            logger.info(
                                f"StubHubInfoGathering.compute: Query {i} MATCHED on event page: {info.get('eventName')}"
                            )
                            self._is_query_covered[i] = True
                            break
                        else:
                            # Log why it didn't match
                            city = info.get("city", "?")
                            event_name = info.get("eventName", "?")
                            logger.info(f"Event page event '{event_name}' (city={city}) did NOT match query")
                
                # Stop looking - we found an event_listing page
                break
            
            elif page_type in ["event_category", "search_results"]:
                # Collect category page infos for fallback
                category_page_infos.extend(page_infos)
        
        # ========== FALLBACK: Check category pages (for sold-out support) ==========
        # Only if no event_listing page was found in the stack
        if not event_listing_found and category_page_infos:
            logger.info(f"No event_listing found, falling back to {len(category_page_infos)} events from category pages")
            
            for i, alternative_conditions in enumerate(self.queries):
                if self._is_query_covered[i]:
                    continue
                
                for info in category_page_infos:
                    if self._check_alternative_conditions(i, alternative_conditions, info):
                        logger.info(
                            f"StubHubInfoGathering.compute: Query {i} MATCHED on category page: {info.get('eventName')}"
                        )
                        self._is_query_covered[i] = True
                        break
        
        # Check for exhausted queries (sold out handling)
        for i, alternative_conditions in enumerate(self.queries):
            if self._is_query_covered[i]:
                continue
            for j, alternative_condition in enumerate(alternative_conditions):
                if not self._is_exhausted(alternative_condition, self._unavailable_evidences[i][j]):
                    break
            else:
                logger.info(f"StubHubInfoGathering.compute found {i}-th query exhausted: {alternative_conditions=}")
                self._is_query_covered[i] = True

        n_queries = len(self.queries)
        n_covered = sum(self._is_query_covered)
        final_result = FinalResult(
            score=n_covered / max(n_queries, 1),
            n_queries=n_queries,
            n_covered=n_covered,
            queries=self.queries,
            is_query_covered=self._is_query_covered,
        )
        logger.info(f"StubHubInfoGathering.compute final result: {final_result}")
        return final_result

    def _check_alternative_conditions(
        self, i: int, alternative_conditions: list[MultiCandidateQuery], info: InfoDict
    ) -> bool:
        """Check if any alternative condition is covered by the info."""
        for j, alternative_condition in enumerate(alternative_conditions):
            evidences = self._unavailable_evidences[i][j]
            if self._check_multi_candidate_query(alternative_condition, info, evidences):
                return True
        return False

    @classmethod
    def _check_multi_candidate_query(
        cls, query: MultiCandidateQuery, info: InfoDict, evidences: list[InfoDict]
    ) -> bool:
        """Check if the multi-candidate query matches the info - comprehensive filter matching."""
        
        # ========== EVENT SEARCH FILTERS ==========
        
        # Check event names using SUBSTRING matching
        if query_names := query.get("event_names"):
            query_names = [name.lower() for name in query_names]
            event_name = info.get("eventName", "").lower()
            if not any(qname in event_name for qname in query_names):
                return False

        # Check event categories
        if query_categories := query.get("event_categories"):
            query_categories = [c.lower() for c in query_categories]
            event_category = info.get("eventCategory", "").lower()
            if event_category and not any(c in event_category for c in query_categories):
                return False

        # Check domain (alias for event_categories)
        if query_domain := query.get("domain"):
            query_domain = [d.lower() for d in query_domain]
            event_category = info.get("eventCategory", "").lower()
            if event_category and not any(d in event_category for d in query_domain):
                return False

        # Check venues using SUBSTRING matching
        if venues := query.get("venues"):
            venues = [v.lower() for v in venues]
            venue = info.get("venue", "").lower()
            if venue and not any(v in venue for v in venues):
                return False

        # Check cities using SUBSTRING matching
        # IMPORTANT: If query requires cities, info MUST have a city to match
        if cities := query.get("cities"):
            cities = [c.lower() for c in cities]
            city = (info.get("city") or "").lower()  # Handle None values
            # If no city in info, it can't match the cities filter
            if not city:
                return False  # Must have city to match cities query
            if not any(c in city for c in cities):
                return False

        # ========== TICKET LISTING FILTERS ==========
        
        # Check minimum tickets
        if min_tickets := query.get("min_tickets"):
            ticket_count = info.get("ticketCount", 0)
            if ticket_count and ticket_count < min_tickets:
                return False

        # Check maximum tickets
        if max_tickets := query.get("max_tickets"):
            ticket_count = info.get("ticketCount", 0)
            if ticket_count and ticket_count > max_tickets:
                return False

        # Check exact ticket quantities (e.g., [2] means exactly 2 tickets)
        if ticket_quantities := query.get("ticket_quantities"):
            ticket_count = info.get("ticketCount", 0)
            if ticket_count and ticket_count not in ticket_quantities:
                return False

        # Check maximum price
        if max_price := query.get("max_price"):
            # Check both regular price and price with fees
            price = info.get("price") or info.get("priceWithFees")
            if price is not None and price > max_price:
                return False

        # Check minimum price
        if min_price := query.get("min_price"):
            price = info.get("price") or info.get("priceWithFees")
            if price is not None and price < min_price:
                return False

        # Check sections using SUBSTRING matching
        if sections := query.get("sections"):
            sections = [s.lower() for s in sections]
            section = info.get("section", "").lower()
            if section and not any(s in section for s in sections):
                return False

        # Check zones using SUBSTRING matching
        if zones := query.get("zones"):
            zones = [z.lower() for z in zones]
            zone = info.get("zone", "").lower()
            if zone and not any(z in zone for z in zones):
                return False

        # Check rows using SUBSTRING matching
        if rows := query.get("rows"):
            rows = [r.lower() for r in rows]
            row = info.get("row", "").lower()
            if row and not any(r in row for r in rows):
                return False

        # Check aisle seat requirement
        if query.get("aisle_seat") is True:
            if not info.get("aisleSeat", False):
                return False

        # ========== TICKET TYPE FILTERS ==========
        
        # Check ticket types
        if ticket_types := query.get("ticket_types"):
            ticket_types = [t.lower() for t in ticket_types]
            ticket_type = info.get("ticketType", "").lower()
            if ticket_type and not any(t in ticket_type for t in ticket_types):
                return False

        # Check parking only filter
        if query.get("parking_only") is True:
            if not info.get("isParkingPass", False):
                return False

        # Check accessible seating requirement
        if query.get("accessible_seating") is True:
            if not info.get("isAccessible", False):
                return False

        # ========== DELIVERY FILTERS ==========
        
        # Check delivery types
        if delivery_types := query.get("delivery_types"):
            delivery_types = [d.lower() for d in delivery_types]
            delivery_type = info.get("deliveryType", "").lower()
            if delivery_type and not any(d in delivery_type for d in delivery_types):
                return False

        # Check instant download only
        if query.get("instant_download_only") is True:
            if not info.get("isInstantDownload", False):
                return False

        # ========== SPECIAL FILTERS ==========
        
        # Check VIP packages
        if query.get("vip_packages") is True:
            if not info.get("isVIP", False):
                return False

        # Check includes extras
        if query.get("includes_extras") is True:
            if not info.get("includesExtras", False):
                return False

        # ========== URL-BASED VERIFICATION (NEW) ==========
        # Verify agent applied correct filters via URL parameters
        
        # Check URL sections (verify agent clicked correct map section)
        if url_sections := query.get("url_sections"):
            info_url_sections = info.get("urlSections", [])
            # At least one required section must be in URL
            if info_url_sections and not any(s in info_url_sections for s in url_sections):
                return False
        
        # Check URL quantity (verify agent set correct ticket quantity)
        if url_quantity := query.get("url_quantity"):
            info_url_quantity = info.get("urlQuantity")
            if info_url_quantity and info_url_quantity != url_quantity:
                return False
        
        # Check URL ticket classes/zones
        if url_ticket_classes := query.get("url_ticket_classes"):
            info_url_classes = info.get("urlTicketClasses", [])
            if info_url_classes and not any(c in info_url_classes for c in url_ticket_classes):
                return False

        # ========== AUTH & PAGE TYPE (NEW) ==========
        
        # Check login requirement
        if query.get("require_login") is True:
            login_status = info.get("loginStatus", "unknown")
            if login_status == "logged_out":
                return False
        
        # Check page type requirement (can be single string or list of acceptable types)
        if require_page_type := query.get("require_page_type"):
            page_type = info.get("pageType", "")
            if page_type:
                # Convert to list if single string
                acceptable_types = require_page_type if isinstance(require_page_type, list) else [require_page_type]
                if page_type not in acceptable_types:
                    return False

        # ========== AVAILABILITY STATUS FILTER (NEW) ==========
        
        # Check availability statuses
        if availability_statuses := query.get("availability_statuses"):
            availability_statuses = [s.lower() for s in availability_statuses]
            info_availability = info.get("availabilityStatus", info.get("info", "")).lower()
            if info_availability and not any(s in info_availability for s in availability_statuses):
                return False

        # ========== DATE/TIME FILTERS ==========
        
        query_dates = query.get("dates")
        query_times = query.get("times")
        query_date_range = query.get("date_range")
        
        # NEW: Check if availability is required (default: False)
        require_available = query.get("require_available", False)

        available_info = info.get("info", "").lower()

        # Handle date range (today, this-weekend, this-week, this-month)
        if query_date_range:
            info_date_range = info.get("dateRange", "").lower()
            if info_date_range and query_date_range.lower() not in info_date_range:
                # If no match on date range text, skip this check
                pass

        # Check if event is sold out / unavailable
        is_sold_out = "sold_out" in available_info or "unavailable" in available_info or "get notified" in available_info
        
        # IMPORTANT: If require_available is False (default), sold-out events STILL count as matches!
        # This ensures the agent gets credit for finding the correct event, even if tickets aren't available.
        if is_sold_out:
            if require_available:
                # User explicitly requires available tickets - reject sold-out events
                if query_dates:
                    if info.get("date") in query_dates:
                        evidences.append(info)
                        return False
                if query_times:
                    if info.get("time") in query_times:
                        evidences.append(info)
                        return False
                return False
            else:
                # require_available is False (default) - ACCEPT sold-out events as valid matches!
                # Agent found the correct event, so they get full credit
                if query_dates:
                    if info.get("date") not in query_dates:
                        return False
                if query_times:
                    if info.get("time") not in query_times:
                        return False
                return True  # Success! Event matches even though it's sold out
        else:
            # Event is available - check date/time match
            if query_dates:
                if info.get("date") not in query_dates:
                    return False
            if query_times:
                if info.get("time") not in query_times:
                    return False
            return True


    @classmethod
    def _check_single_candidate_query(cls, query: SingleCandidateQuery, info: InfoDict) -> bool:
        """Check if single-candidate query matches the info."""
        if (query_name := query.get("event_name")) is not None:
            if info.get("eventName", "").lower() != query_name.lower():
                return False

        if (query_venue := query.get("venue")) is not None:
            if info.get("venue", "").lower() != query_venue.lower():
                return False

        if (query_city := query.get("city")) is not None:
            if info.get("city", "").lower() != query_city.lower():
                return False

        if (query_min_tickets := query.get("min_tickets")) is not None:
            if info.get("ticketCount", 0) < query_min_tickets:
                return False

        if (query_max_price := query.get("max_price")) is not None:
            if info.get("price", float('inf')) > query_max_price:
                return False

        query_date = query.get("date")
        query_time = query.get("time")

        if "sold_out" in info.get("info", "").lower():
            if query_date:
                if info.get("date") == query_date:
                    return True
            if query_time:
                if info.get("time") == query_time:
                    return True
            return False
        else:
            if query_date:
                if info.get("date") != query_date:
                    return False
            if query_time:
                if info.get("time") != query_time:
                    return False
            return True

    @classmethod
    def _is_exhausted(cls, query: MultiCandidateQuery, evidences: list[InfoDict]) -> bool:
        """Check if we've exhausted searching for the query."""
        query_names = query.get("event_names") or [None]
        query_venues = query.get("venues") or [None]
        query_cities = query.get("cities") or [None]
        query_dates = query.get("dates") or [None]
        query_times = query.get("times") or [None]

        for query_name, query_venue, query_city, query_date, query_time in itertools.product(
            query_names, query_venues, query_cities, query_dates, query_times
        ):
            found_match = False
            for info in evidences:
                if cls._check_single_candidate_query(
                    SingleCandidateQuery(
                        event_name=query_name,
                        venue=query_venue,
                        city=query_city,
                        date=query_date,
                        time=query_time,
                    ),
                    info,
                ):
                    found_match = True
                    break

            if not found_match:
                return False

        return True


# NOTE: Event categories and city/venue mappings are now dynamically extracted
# from StubHub's LD+JSON structured data in the JavaScript scraper.
# This eliminates the need for hardcoded mappings.


def get_next_weekend_dates() -> list[str]:
    """Get dates for the next weekend (Saturday and Sunday)."""
    today = datetime.now()
    days_until_saturday = (5 - today.weekday()) % 7
    if days_until_saturday == 0:
        days_until_saturday = 7
    
    saturday = today + timedelta(days=days_until_saturday)
    sunday = saturday + timedelta(days=1)
    
    return [
        saturday.strftime("%Y-%m-%d"),
        sunday.strftime("%Y-%m-%d")
    ]


def get_upcoming_weekday(weekday_name: str) -> str:
    """Get date for the next occurrence of a weekday."""
    weekday_map = {
        "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
        "Friday": 4, "Saturday": 5, "Sunday": 6
    }
    
    target_day = weekday_map[weekday_name]
    today = datetime.now()
    days_ahead = (target_day - today.weekday()) % 7
    
    if days_ahead == 0:
        days_ahead = 7
    
    target_date = today + timedelta(days=days_ahead)
    return target_date.strftime("%Y-%m-%d")


def generate_task_config_random(
    event_type: Literal["sports", "concert", "theater"],
    city: str,
    timezone: str,
    event_name: str | None = None,
    seed: int | None = None,
    url: str = "https://www.stubhub.com",
) -> BaseTaskConfig:
    """Generate random task configuration for StubHub events.
    
    Args:
        event_type: Type of event (sports, concert, theater)
        city: City name for the event
        timezone: IANA timezone string (e.g., 'America/Los_Angeles', 'Asia/Kolkata')
        event_name: Optional specific event name. If None, uses generic category.
        seed: Random seed for reproducibility
        url: StubHub URL
    """
    if seed is not None:
        random.seed(seed)

    location = f"{city}"

    # Use provided event_name or generic category
    if not event_name:
        event_name = f"{event_type} event"

    # Generate random date (next 30 days)
    days_ahead = random.randint(1, 30)
    event_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    # Random price range
    max_price = random.choice([200.0, 300.0, 500.0, 1000.0])

    # Random ticket count
    min_tickets = random.randint(1, 4)

    # Create task description
    task = (
        f"Search for {event_name} tickets in {city} "
        f"for {event_date} with at least {min_tickets} tickets "
        f"under ${max_price:.0f}"
    )

    user_metadata = UserMetadata(
        location=location,
        timezone=timezone,
        timestamp=int(datetime.now().timestamp()),
    )

    eval_config = {
        "_target_": get_import_path(StubHubInfoGathering),
        "queries": [[{
            "event_names": [event_name.lower()],
            "dates": [event_date],
            "cities": [city.lower()],
            "min_tickets": min_tickets,
            "max_price": max_price,
        }]]
    }

    return BaseTaskConfig(url=url, task=task, user_metadata=user_metadata, eval_config=eval_config)


def generate_task_config_deterministic(
    mode: Literal["any", "all"],
    task: str,
    queries: list[list[MultiCandidateQuery]],
    location: str,
    timezone: str,
    timestamp: int | None = None,
    url: str = "https://www.stubhub.com",
) -> BaseTaskConfig:
    """Generate deterministic task configuration."""
    user_metadata = initialize_user_metadata(timezone, location, timestamp)
    
    eval_config = {
        "_target_": get_import_path(StubHubInfoGathering),
        "queries": queries
    }

    return BaseTaskConfig(url=url, task=task, user_metadata=user_metadata, eval_config=eval_config)



if __name__ == "__main__":
    import json
    from navi_bench.base import DatasetItem, instantiate

    dataset_row = {
        "task_id": "navi_bench/stubhub/test/0",
        "task_generation_config_json": json.dumps({
            "_target_": "navi_bench.stubhub.stubhub_info_gathering.generate_task_config_deterministic",
            "mode": "any",
            "url": "https://www.stubhub.com",
            "task": "Search for Lakers tickets in Los Angeles for December 20, 2025",
            "queries": [[{
                "event_names": ["lakers", "los angeles lakers"],
                "dates": ["2025-12-20"],
                "cities": ["los angeles", "inglewood"]
            }]],
            "location": "Los Angeles, CA, United States",
            "timezone": "America/Los_Angeles",
        }),
        "env": "real",
        "domain": "stubhub",
        "l1_category": "entertainment",
        "l2_category": "sports",
    }

    dataset_item = DatasetItem.model_validate(dataset_row)
    task_config = dataset_item.generate_task_config()
    evaluator = instantiate(task_config.eval_config)

    print("Loaded dataset item")
    print("-------------------")
    print(dataset_item)
    print()

    print("Generated task config")
    print("---------------------")
    print(task_config)
    print()

    print("Instantiated evaluator")
    print("----------------------")
    print(evaluator)
