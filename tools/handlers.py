"""
Tool handler implementations with Pydantic validation.

Two tools only — data fetching. The model handles all math/sorting/variance.

In production:
  - fetch_data calls your real data API (POST /api/v1/data/query)
  - get_members calls your real hierarchy API (POST /api/v1/hierarchy/members)

For local testing, mock implementations return simulated data based on the
JSON metadata files so the full agent flow works end-to-end.
"""

import hashlib
import json
from pathlib import Path

from tools.models import FetchDataInput, GetMembersInput

DATA_DIR = Path(__file__).parent.parent / "data"


def _load_json(filename: str) -> dict:
    with open(DATA_DIR / filename) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Tool: fetch_data
# ---------------------------------------------------------------------------

def _handle_fetch_data(params: FetchDataInput) -> str:
    """
    Fetch measure data from the API.

    Returns raw data to the model — no math, no sorting.
    The model interprets and presents the data to the user.
    """

    # ------------------------------------------------------------------
    # PRODUCTION: Uncomment this block to call your real data API
    #
    # import requests
    # from config import DATA_API_BASE_URL
    #
    # payload = {
    #     "measureVersions": params.measure_versions,
    #     "dimensions": {
    #         "item": [m.model_dump() for m in params.item_members],
    #         "time": [m.model_dump() for m in params.time_members],
    #     },
    # }
    # if params.location_members:
    #     payload["dimensions"]["location"] = [m.model_dump() for m in params.location_members]
    # if params.break_down_by:
    #     payload["breakDownBy"] = params.break_down_by.model_dump()
    #
    # resp = requests.post(f"{DATA_API_BASE_URL}/data/query", json=payload)
    # resp.raise_for_status()
    # return resp.text
    # ------------------------------------------------------------------

    # MOCK: Generate simulated data for testing
    item_members = [m.model_dump() for m in params.item_members]
    time_members = [m.model_dump() for m in params.time_members]
    location_members = [m.model_dump() for m in params.location_members] if params.location_members else None
    break_down_by = params.break_down_by.model_dump() if params.break_down_by else None

    if break_down_by:
        return _mock_breakdown_data(params.measure_versions, item_members, time_members,
                                     location_members, break_down_by)
    else:
        return _mock_aggregate_data(params.measure_versions, item_members, time_members,
                                     location_members)


def _mock_aggregate_data(
    measure_versions: list[str],
    item_members: list[dict],
    time_members: list[dict],
    location_members: list[dict] | None,
) -> str:
    """Return a single aggregated row with values for each measure-version."""
    item_ctx = ", ".join(f"{m['level']}={m['member']}" for m in item_members)
    time_ctx = ", ".join(f"{m['level']}={m['member']}" for m in time_members)

    result = {
        "context": {
            "item": item_ctx,
            "time": time_ctx,
            "location": (
                ", ".join(f"{m['level']}={m['member']}" for m in location_members)
                if location_members else "TOTALLOCATION"
            ),
        },
        "data": {},
    }

    for mv in measure_versions:
        seed = f"{mv}:{item_ctx}:{time_ctx}"
        h = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)
        if "PCT" in mv or "VP" in mv:
            result["data"][mv] = round((h % 10000) / 100.0 - 20, 2)
        elif "UNITS" in mv:
            result["data"][mv] = h % 500000 + 10000
        else:
            result["data"][mv] = round((h % 10000000) / 100.0 + 50000, 2)

    return json.dumps(result, indent=2)


def _mock_breakdown_data(
    measure_versions: list[str],
    item_members: list[dict],
    time_members: list[dict],
    location_members: list[dict] | None,
    break_down_by: dict,
) -> str:
    """Return data broken down by a dimension level."""
    members_data = _load_json("members.json")

    dim = break_down_by["dimension"]
    level = break_down_by["level"]

    if dim == "ITEM":
        source = members_data["itemMembers"]
    elif dim == "TIME":
        source = members_data["timeMembers"]
    elif dim == "LOCATION":
        source = members_data["locationMembers"]
    else:
        source = []

    breakdown_members = sorted(set(
        row[level] for row in source if level in row and row[level]
    ))

    if not breakdown_members:
        breakdown_members = [f"{level}_1", f"{level}_2", f"{level}_3"]

    item_ctx = ", ".join(f"{m['level']}={m['member']}" for m in item_members)
    time_ctx = ", ".join(f"{m['level']}={m['member']}" for m in time_members)

    rows = []
    for bm in breakdown_members:
        row = {"breakdownMember": bm, "breakdownLevel": level}
        for mv in measure_versions:
            seed = f"{mv}:{item_ctx}:{time_ctx}:{bm}"
            h = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)
            if "PCT" in mv or "VP" in mv:
                row[mv] = round((h % 10000) / 100.0 - 20, 2)
            elif "UNITS" in mv:
                row[mv] = h % 500000 + 10000
            else:
                row[mv] = round((h % 10000000) / 100.0 + 50000, 2)
        rows.append(row)

    result = {
        "context": {
            "item": item_ctx,
            "time": time_ctx,
            "location": (
                ", ".join(f"{m['level']}={m['member']}" for m in location_members)
                if location_members else "TOTALLOCATION"
            ),
        },
        "breakDownBy": {"dimension": dim, "level": level},
        "rowCount": len(rows),
        "data": rows,
    }

    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Tool: get_members
# ---------------------------------------------------------------------------

def _handle_get_members(params: GetMembersInput) -> str:
    """
    Look up members at a hierarchy level within a dimension.
    Optionally filter by a parent member.
    """

    # ------------------------------------------------------------------
    # PRODUCTION: Uncomment this block to call your real hierarchy API
    #
    # import requests
    # from config import DATA_API_BASE_URL
    #
    # payload = {
    #     "dimension": params.dimension.value,
    #     "level": params.level,
    # }
    # if params.parent_level and params.parent_member:
    #     payload["filters"] = [{"level": params.parent_level, "members": [params.parent_member]}]
    #
    # resp = requests.post(f"{DATA_API_BASE_URL}/hierarchy/members", json=payload)
    # resp.raise_for_status()
    # return resp.text
    # ------------------------------------------------------------------

    # MOCK: Use local JSON data
    members_data = _load_json("members.json")
    dimension = params.dimension.value

    if dimension == "ITEM":
        source = members_data["itemMembers"]
    elif dimension == "TIME":
        source = members_data["timeMembers"]
    elif dimension == "LOCATION":
        source = members_data["locationMembers"]
    else:
        return json.dumps({"error": f"Unknown dimension: {dimension}. Use ITEM, TIME, or LOCATION."})

    filtered = source
    if params.parent_level and params.parent_member:
        filtered = [row for row in source if row.get(params.parent_level) == params.parent_member]

    seen = set()
    result_members = []
    for row in filtered:
        val = row.get(params.level)
        if val and val.strip() and val not in seen:
            seen.add(val)
            result_members.append(val)

    return json.dumps({
        "dimension": dimension,
        "level": params.level,
        "parentFilter": (
            {"level": params.parent_level, "member": params.parent_member}
            if params.parent_level else None
        ),
        "count": len(result_members),
        "members": sorted(result_members),
    }, indent=2)


# ---------------------------------------------------------------------------
# Dispatcher: validates with Pydantic then routes to handler
# ---------------------------------------------------------------------------

def dispatch_tool_call(function_name: str, arguments: dict) -> str:
    """Validate arguments with Pydantic model, then execute the handler."""
    if function_name == "fetch_data":
        params = FetchDataInput.model_validate(arguments)
        return _handle_fetch_data(params)
    elif function_name == "get_members":
        params = GetMembersInput.model_validate(arguments)
        return _handle_get_members(params)
    else:
        return json.dumps({"error": f"Unknown function: {function_name}"})
