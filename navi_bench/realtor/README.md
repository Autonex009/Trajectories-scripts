# Realtor.com URL Match Script

## Advanced URL Verification System for NaviBench

**NaviBench Framework**

---

## 1. Overview

The Realtor.com URL Match script is a production-grade URL verification metric for the NaviBench framework. It evaluates whether an AI agent has successfully navigated to the correct Realtor.com search page by comparing the agent's final URL against ground truth URLs.

### Purpose

This script handles Realtor.com's **path-segment based** URL structure where search filters are encoded as individual path segments (e.g., `/beds-3/price-500000-1000000/type-condo`).

### Design Philosophy

**"Parse → Normalize → Compare"**

1. **Parse**: Extract search type, location, and filters from URL path segments
2. **Normalize**: Apply aliases, abbreviations, and canonical forms
3. **Compare**: Use dictionary equality for order-independent matching

---

## 2. Core Capabilities

| Feature | Description | Status |
|---------|-------------|--------|
| Path-based Filters | Handles all `/filter-value` URL segments | ✅ |
| Search Type Equivalence | `sold-homes` ↔ `show-recently-sold`, `open-houses` ↔ `show-open-house` | ✅ |
| Rental Path Aliases | `rentals`, `houses-for-rent`, `apartments-for-rent` → `apartments` | ✅ |
| Location Parsing | City_ST, ZIP codes, Neighborhood_City_ST | ✅ |
| Property Type Aliases | 20+ aliases (house→single-family-home, ranch→farm, etc.) | ✅ |
| Price Abbreviations | `500k → 500000`, `1m → 1000000` | ✅ |
| Show Flag Handling | 8+ show flags with aliases | ✅ |
| Rental-Specific Filters | dog-friendly, cat-friendly, features-*, with_* | ✅ |
| Filter Order Independence | All permutations handled | ✅ |
| Case Insensitivity | Lowercase normalization | ✅ |
| Sort/Pagination Ignored | `sby-*`, `pg-*` stripped | ✅ |
| Extra Filters Allowed | Agent can have MORE filters than GT | ✅ |
| Multiple GT URLs | Supports multiple acceptable answers | ✅ |

---

## 3. Component Structure

| Component | Type | Purpose |
|-----------|------|---------|
| `InputDict` | TypedDict | Input specification containing URL string |
| `FinalResult` | Pydantic Model | Output model with score (0.0 or 1.0) |
| `RealtorUrlMatch` | BaseMetric | Main evaluation metric class |
| `generate_task_config` | Function | Factory for creating task configurations |

### Dependencies

| Library | Purpose |
|---------|---------|
| `re` | Regular expressions for URL parsing |
| `urllib.parse` | URL parsing: `urlparse`, `unquote` |
| `beartype` | Runtime type checking |
| `loguru` | Structured logging |
| `pydantic` | Data validation for FinalResult |
| `navi_bench.base` | BaseMetric, BaseTaskConfig, get_import_path |
| `navi_bench.dates` | initialize_user_metadata for task context |

---

## 4. Usage

### Basic Example

```python
from navi_bench.realtor.realtor_url_match import RealtorUrlMatch, generate_task_config

# Generate task configuration
task_config = generate_task_config(
    task="Find 3-bedroom homes in San Francisco under $1M",
    gt_url=[
        "https://www.realtor.com/realestateandhomes-search/San-Francisco_CA/beds-3/price-na-1000000"
    ],
    location="San Francisco, CA",
    timezone="America/Los_Angeles"
)

# Create evaluator
evaluator = RealtorUrlMatch(gt_url=task_config.eval_config["gt_url"])

# During agent execution
await evaluator.reset()
await evaluator.update(url=agent_current_url)

# Get final result
result = await evaluator.compute()
print(f"Score: {result.score}")  # 1.0 = match, 0.0 = no match
```

### Multiple GT URLs

```python
evaluator = RealtorUrlMatch(
    gt_url=[
        "https://www.realtor.com/sold-homes/SF_CA/beds-3",
        "https://www.realtor.com/realestateandhomes-search/SF_CA/beds-3/show-recently-sold"
    ]
)
```

---

## 5. Supported URL Patterns

### Search Types

| Type | Path | Status |
|------|------|--------|
| For Sale | `/realestateandhomes-search/` | ✅ |
| Rentals | `/apartments/` | ✅ |
| Sold (legacy) | `/sold-homes/` | ✅ (→ equivalence) |
| Open Houses (legacy) | `/open-houses/` | ✅ (→ equivalence) |

### Filters

| Category | Example Segments |
|----------|-----------------|
| Beds/Baths | `beds-3`, `beds-3-4`, `baths-2` |
| Price | `price-500000-1000000`, `price-na-500k` |
| Type | `type-single-family-home`, `type-condo` |
| Show Flags | `show-open-house`, `show-recently-sold` |
| Sqft | `sqft-2000-3000` |
| Lot | `lot-sqft-5000-10000` |
| Home Age | `age-0-10`, `year-built-2000-2024` |
| Structure | `stories-1`, `garage-2` |
| HOA | `hoa-na-500` |
| DOM | `dom-7`, `dom-30` |
| Radius | `radius-25` |
| Pet (rental) | `dog-friendly`, `cat-friendly` |
| Amenity (rental) | `features-cs` (pool), `features-gy` (gym) |
| Laundry (rental) | `with_inunitlaundry` |

---

## 6. Running Tests

### Command

```bash
cd /path/to/project
python -m navi_bench.realtor.realtor_url_match
```

### Expected Output

```
================================================================================
REALTOR.COM URL VERIFIER - COMPREHENSIVE EDGE CASE TEST SUITE
================================================================================

90+ tests across 21 categories...

================================================================================
FINAL RESULTS
================================================================================
Total Tests: 90+
Passed: ALL
Success Rate: 100.0%
================================================================================
```

---

## 7. Documentation Files

| Document | Description |
|----------|-------------|
| [README.md](./README.md) | This file — overview and usage |
| [COVERAGE.md](./COVERAGE.md) | All 61+ filters with URL formats and verification status |
| [HOW_IT_WORKS.md](./HOW_IT_WORKS.md) | Technical algorithm deep dive |

---

## 8. Summary & Statistics

| Metric | Value |
|--------|-------|
| Total Lines of Code | 1400+ |
| Property Type Aliases | 20+ |
| Show Flag Types | 8+ |
| Filter Categories | 15+ |
| Inline Test Cases | 90+ |
| Test Pass Rate | 100% |
| Browser Verification Sessions | 2 |

---

**Last Updated**: 2026-02-17
**Implementation Version**: 2.0 (Chrome-Verified)
