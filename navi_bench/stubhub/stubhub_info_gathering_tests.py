import pytest
from unittest.mock import AsyncMock, MagicMock
from stubhub_info_gathering import StubHubInfoGathering

# Mock the Playwright Page object
@pytest.fixture
def mock_page():
    page = AsyncMock()
    page.url = "https://www.stubhub.com/event/123"
    # Mock evaluate to return data based on our test scenario
    return page

@pytest.mark.asyncio
async def test_sold_out_edge_case(mock_page):
    """
    Test Edge Case: Agent finds the correct event, but it is sold out.
    The verifier should mark this as a success if 'require_available' is False (default).
    """
    verifier = StubHubInfoGathering(queries=[[{
        "event_names": ["taylor swift"],
        "require_available": False 
    }]])
    
    # Mock JS returning a sold-out event
    mock_data = [{
        "eventName": "taylor swift eras tour",
        "availabilityStatus": "sold_out",
        "pageType": "event_listing",
        "info": "sold_out"
    }]
    mock_page.evaluate.return_value = mock_data
    
    # Run update
    await verifier.update(page=mock_page)
    result = await verifier.compute()
    
    # Should pass because we found the event, even though it's sold out
    assert result.score == 1.0
    assert result.is_query_covered[0] is True

@pytest.mark.asyncio
async def test_multi_currency_edge_case(mock_page):
    """
    Test Edge Case: Event prices are in Euros (EUR) instead of USD.
    """
    verifier = StubHubInfoGathering(queries=[[{
        "max_price": 200.0,
        "currency": "EUR"
    }]])
    
    # Mock JS returning EUR price
    mock_data = [{
        "eventName": "uefa champions league",
        "price": 150.0, # 150 < 200
        "currency": "EUR",
        "pageType": "event_listing"
    }]
    mock_page.evaluate.return_value = mock_data
    
    await verifier.update(page=mock_page)
    result = await verifier.compute()
    
    assert result.score == 1.0

@pytest.mark.asyncio
async def test_relative_date_parsing(mock_page):
    """
    Test Edge Case: JS scraper detects 'Tomorrow' instead of exact date.
    Note: This tests the Python side's ability to accept the data, 
    assuming the JS (tested separately or via integration) normalized it.
    """
    verifier = StubHubInfoGathering(queries=[[{
        "date_range": "tomorrow"
    }]])
    
    mock_data = [{
        "eventName": "improv comedy",
        "dateRange": "tomorrow",
        "pageType": "event_listing"
    }]
    mock_page.evaluate.return_value = mock_data
    
    await verifier.update(page=mock_page)
    result = await verifier.compute()
    
    assert result.score == 1.0