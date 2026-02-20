"""
Unit tests for StubHub verifier - no browser required.
Run with: pytest navi_bench/stubhub/test_stubhub_unit.py -v
"""

import json
import pytest
from datetime import datetime

# Test imports
from navi_bench.stubhub.stubhub_info_gathering import (
    StubHubInfoGathering,
    FinalResult,
    generate_task_config_random,
    generate_task_config_deterministic,
    get_next_weekend_dates,
    get_upcoming_weekday,
)


class TestStubHubVerifierLogic:
    """Test the verifier's matching logic without browser interaction."""
    
    @pytest.fixture
    def single_query_evaluator(self):
        """Create evaluator with single query."""
        return StubHubInfoGathering(
            queries=[[{
                "event_names": ["lakers", "los angeles lakers"],
                "dates": ["2025-12-20"],
                "cities": ["los angeles", "inglewood"],
                "max_price": 500.00
            }]]
        )
    
    @pytest.fixture
    def multi_query_evaluator(self):
        """Create evaluator with multiple queries."""
        return StubHubInfoGathering(
            queries=[
                [{
                    "event_names": ["lakers"],
                    "dates": ["2025-12-20"],
                    "cities": ["los angeles"]
                }],
                [{
                    "event_names": ["clippers"],
                    "dates": ["2025-12-21"],
                    "cities": ["los angeles"]
                }]
            ]
        )
    
    @pytest.mark.asyncio
    async def test_evaluator_initialization(self, single_query_evaluator):
        """Test evaluator initializes correctly."""
        assert len(single_query_evaluator.queries) == 1
    
    @pytest.mark.asyncio
    async def test_reset_clears_state(self, single_query_evaluator):
        """Test reset clears matched queries."""
        single_query_evaluator._is_query_covered = [True]
        await single_query_evaluator.reset()
        assert single_query_evaluator._is_query_covered == [False]
    
    @pytest.mark.asyncio
    async def test_compute_no_matches(self, single_query_evaluator):
        """Test compute returns 0 when no queries matched."""
        result = await single_query_evaluator.compute()
        assert result.score == 0.0
        assert result.n_covered == 0
        assert result.n_queries == 1
    
    @pytest.mark.asyncio
    async def test_compute_all_matched(self, single_query_evaluator):
        """Test compute returns 1.0 when all queries matched."""
        single_query_evaluator._is_query_covered = [True]
        result = await single_query_evaluator.compute()
        assert result.score == 1.0
        assert result.n_covered == 1
    
    @pytest.mark.asyncio
    async def test_compute_partial_matches(self, multi_query_evaluator):
        """Test compute returns partial score when some queries matched."""
        multi_query_evaluator._is_query_covered = [True, False]
        result = await multi_query_evaluator.compute()
        assert result.score == 0.5
        assert result.n_covered == 1
        assert result.n_queries == 2


class TestTaskGeneration:
    """Test task generation functions."""
    
    def test_random_task_generation(self):
        """Test random task generation creates valid config."""
        config = generate_task_config_random(
            event_type="sports",
            city="Los Angeles",
            timezone="America/Los_Angeles",
            event_name="Lakers"
        )
        
        assert config.url == "https://www.stubhub.com"
        assert config.task is not None
        assert len(config.task) > 0
        assert config.eval_config is not None
    
    def test_deterministic_task_generation(self):
        """Test deterministic task generation creates valid config."""
        config = generate_task_config_deterministic(
            mode="any",
            url="https://www.stubhub.com",
            task="Find Lakers tickets",
            queries=[[{
                "event_names": ["lakers"],
                "cities": ["los angeles"]
            }]],
            location="Los Angeles, CA, United States",
            timezone="America/Los_Angeles"
        )
        
        assert config.url == "https://www.stubhub.com"
        assert config.task == "Find Lakers tickets"
        assert config.eval_config is not None


class TestDateHelpers:
    """Test date helper functions."""
    
    def test_get_next_weekend_dates(self):
        """Test weekend date generation."""
        dates = get_next_weekend_dates()
        
        assert len(dates) == 2
        assert len(dates[0]) == 10  # YYYY-MM-DD format
        assert len(dates[1]) == 10
        assert dates[0] < dates[1]  # Saturday before Sunday
    
    def test_get_upcoming_weekday(self):
        """Test weekday date generation."""
        friday_date = get_upcoming_weekday("Friday")
        
        assert len(friday_date) == 10
        # Parse and verify it's a Friday
        date_obj = datetime.strptime(friday_date, "%Y-%m-%d")
        assert date_obj.weekday() == 4


class TestEvaluatorRepr:
    """Test evaluator representation."""
    
    def test_repr(self):
        """Test __repr__ returns useful info."""
        evaluator = StubHubInfoGathering(
            queries=[[{"event_names": ["test"]}]]
        )
        
        repr_str = repr(evaluator)
        assert "StubHubInfoGathering" in repr_str


class TestMatchingLogic:
    """Test query matching logic."""
    
    def test_check_multi_candidate_query_event_name_match(self):
        """Test event name matching."""
        query = {
            "event_names": ["lakers", "los angeles lakers"],
            "cities": ["los angeles"]
        }
        info_match = {
            "eventName": "lakers",
            "city": "los angeles",
            "date": "2025-12-20",
            "price": 100.0,
        }
        info_no_match = {
            "eventName": "clippers",
            "city": "los angeles",
            "date": "2025-12-20",
            "price": 100.0,
        }
        
        result_match = StubHubInfoGathering._check_multi_candidate_query(query, info_match, [])
        result_no_match = StubHubInfoGathering._check_multi_candidate_query(query, info_no_match, [])
        
        assert result_match == True
        assert result_no_match == False
    
    def test_check_multi_candidate_query_price_filter(self):
        """Test price filtering."""
        query = {
            "event_names": ["lakers"],
            "max_price": 200.0
        }
        info_under = {"eventName": "lakers", "price": 150.0}
        info_over = {"eventName": "lakers", "price": 250.0}
        
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_under, []) == True
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_over, []) == False


class TestUrlBasedVerification:
    """Test URL-based filter verification logic."""
    
    def test_url_section_matching(self):
        """Test URL section verification (agent clicked correct map section)."""
        query = {
            "event_names": ["lakers"],
            "url_sections": ["1132936", "1132937"]  # Expected section IDs
        }
        info_match = {"eventName": "lakers", "urlSections": ["1132936"]}
        info_no_match = {"eventName": "lakers", "urlSections": ["999999"]}
        info_empty = {"eventName": "lakers", "urlSections": []}
        
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_match, []) == True
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_no_match, []) == False
        # Empty URL sections should pass (filter not applied by agent)
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_empty, []) == True
    
    def test_url_quantity_matching(self):
        """Test URL quantity verification (agent set correct ticket count)."""
        query = {
            "event_names": ["lakers"],
            "url_quantity": 4
        }
        info_match = {"eventName": "lakers", "urlQuantity": 4}
        info_no_match = {"eventName": "lakers", "urlQuantity": 2}
        info_none = {"eventName": "lakers", "urlQuantity": None}
        
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_match, []) == True
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_no_match, []) == False
        # No URL quantity should pass
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_none, []) == True
    
    def test_url_ticket_class_matching(self):
        """Test URL ticket class/zone verification."""
        query = {
            "event_names": ["lakers"],
            "url_ticket_classes": ["1679", "1680"]
        }
        info_match = {"eventName": "lakers", "urlTicketClasses": ["1679"]}
        info_no_match = {"eventName": "lakers", "urlTicketClasses": ["9999"]}
        
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_match, []) == True
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_no_match, []) == False


class TestAuthAndPageType:
    """Test authentication and page type verification."""
    
    def test_require_login(self):
        """Test login requirement verification."""
        query = {
            "event_names": ["lakers"],
            "require_login": True
        }
        info_logged_in = {"eventName": "lakers", "loginStatus": "logged_in"}
        info_logged_out = {"eventName": "lakers", "loginStatus": "logged_out"}
        info_unknown = {"eventName": "lakers", "loginStatus": "unknown"}
        
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_logged_in, []) == True
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_logged_out, []) == False
        # Unknown login status should pass (no definitive logged_out)
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_unknown, []) == True
    
    def test_require_page_type(self):
        """Test page type requirement verification."""
        query = {
            "event_names": ["lakers"],
            "require_page_type": "event_listing"
        }
        info_match = {"eventName": "lakers", "pageType": "event_listing"}
        info_no_match = {"eventName": "lakers", "pageType": "search_results"}
        
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_match, []) == True
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_no_match, []) == False


class TestAvailabilityStatus:
    """Test availability status filtering."""
    
    def test_availability_status_filter(self):
        """Test availability status filtering."""
        query = {
            "event_names": ["lakers"],
            "availability_statuses": ["available", "limited"]
        }
        info_available = {"eventName": "lakers", "availabilityStatus": "available"}
        info_limited = {"eventName": "lakers", "availabilityStatus": "limited"}
        info_sold_out = {"eventName": "lakers", "availabilityStatus": "sold_out"}
        
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_available, []) == True
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_limited, []) == True
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_sold_out, []) == False
    
    def test_ticket_quantities_exact_match(self):
        """Test exact ticket quantity matching."""
        query = {
            "event_names": ["lakers"],
            "ticket_quantities": [2, 4]  # Accept exactly 2 or 4 tickets
        }
        info_match_2 = {"eventName": "lakers", "ticketCount": 2}
        info_match_4 = {"eventName": "lakers", "ticketCount": 4}
        info_no_match = {"eventName": "lakers", "ticketCount": 3}
        
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_match_2, []) == True
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_match_4, []) == True
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_no_match, []) == False
    
    def test_zone_matching(self):
        """Test zone name matching."""
        query = {
            "event_names": ["lakers"],
            "zones": ["lower level", "floor"]
        }
        info_match = {"eventName": "lakers", "zone": "lower level"}
        info_no_match = {"eventName": "lakers", "zone": "upper deck"}
        
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_match, []) == True
        assert StubHubInfoGathering._check_multi_candidate_query(query, info_no_match, []) == False


# Run with: pytest navi_bench/stubhub/test_stubhub_unit.py -v
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
