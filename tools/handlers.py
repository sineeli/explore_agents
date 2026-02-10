"""
Tool handler implementations.

Each function corresponds to a tool the agent can call.
In production, these would call your real data API endpoints.
Here we provide both:
  1. A mock/local implementation using the JSON data files (for testing)
  2. The HTTP API call pattern (commented, ready for your real backend)
"""

import json
import os
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _load_json(filename: str) -> dict:
    with open(DATA_DIR / filename) as f:
        return json.load(f)


def _load_hierarchies() -> dict:
    return _load_json("hierarchies.json")


def _load_measures() -> dict:
    return _load_json("measures.json")


def _load_members() -> list[dict]:
    return _load_json("members.json")["members"]


# ---------------------------------------------------------------------------
# Tool: get_hierarchy_levels
# ---------------------------------------------------------------------------

def get_hierarchy_levels(hierarchy_name: str) -> str:
    """Return ordered levels for a hierarchy."""
    data = _load_hierarchies()
    for h in data["hierarchies"]:
        if h["name"].upper() == hierarchy_name.upper():
            levels = sorted(h["levels"], key=lambda l: l["order"])
            result = {
                "hierarchy": h["name"],
                "displayName": h["displayName"],
                "description": h["description"],
                "levels": [
                    {
                        "level": lv["level"],
                        "order": lv["order"],
                        "displayName": lv.get("displayName", lv["level"]),
                        "description": lv.get("description", ""),
                    }
                    for lv in levels
                ],
            }
            return json.dumps(result, indent=2)

    return json.dumps({"error": f"Hierarchy '{hierarchy_name}' not found. Available: ITEMHIERARCHY, BUYERHIERARCHY, VENDORHIERARCHY, SUBCLASSATTRIBUTEHIERARCHY"})


# ---------------------------------------------------------------------------
# Tool: get_members
# ---------------------------------------------------------------------------

def get_members(
    hierarchy_name: str,
    level: str,
    parent_level: str | None = None,
    parent_member: str | None = None,
) -> str:
    """Fetch distinct members at a hierarchy level, optionally filtered by parent."""
    members = _load_members()
    level_key = level.upper()

    # Filter by parent if provided
    filtered = members
    if parent_level and parent_member:
        pk = parent_level.upper()
        filtered = [m for m in members if m.get(pk) == parent_member]

    # Extract distinct values at the requested level
    seen = set()
    result_members = []
    for m in filtered:
        val = m.get(level_key)
        if val and val.strip() and val not in seen:
            seen.add(val)
            result_members.append(val)

    # ------------------------------------------------------------------
    # Production API call pattern (uncomment when connecting to real API):
    #
    # import requests
    # from config import DATA_API_BASE_URL
    #
    # resp = requests.post(
    #     f"{DATA_API_BASE_URL}/hierarchy/members",
    #     json={
    #         "hierarchyName": hierarchy_name,
    #         "level": level,
    #         "filters": (
    #             [{"level": parent_level, "members": [parent_member]}]
    #             if parent_level and parent_member else []
    #         ),
    #     },
    # )
    # resp.raise_for_status()
    # return resp.text
    # ------------------------------------------------------------------

    return json.dumps({
        "hierarchy": hierarchy_name,
        "level": level_key,
        "parent_filter": {"level": parent_level, "member": parent_member} if parent_level else None,
        "count": len(result_members),
        "members": sorted(result_members),
    }, indent=2)


# ---------------------------------------------------------------------------
# Tool: query_measure_data
# ---------------------------------------------------------------------------

def query_measure_data(
    measure_name: str,
    version: str,
    group_by_level: str,
    filter_level: str | None = None,
    filter_member: str | None = None,
    sort_order: str = "desc",
    top_n: int | None = None,
) -> str:
    """
    Query measure data grouped by a hierarchy level.

    In production this calls your data API. Here we return simulated data
    based on the member structure so the agent flow works end-to-end.
    """
    import hashlib

    members = _load_members()
    level_key = group_by_level.upper()

    # Apply filter
    filtered = members
    if filter_level and filter_member:
        fk = filter_level.upper()
        filtered = [m for m in members if m.get(fk) == filter_member]

    # Aggregate distinct members at group_by_level with simulated values
    seen = {}
    for m in filtered:
        val = m.get(level_key)
        if val and val.strip():
            if val not in seen:
                # Generate a deterministic pseudo-random value from the member+measure
                seed = f"{val}:{measure_name}:{version}"
                h = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)
                seen[val] = round((h % 100000) / 100.0 + 1000, 2)

    # Sort
    items = sorted(seen.items(), key=lambda x: x[1], reverse=(sort_order == "desc"))
    if top_n:
        items = items[:top_n]

    # ------------------------------------------------------------------
    # Production API call pattern:
    #
    # import requests
    # from config import DATA_API_BASE_URL
    #
    # payload = {
    #     "measures": [{"name": measure_name, "version": version}],
    #     "groupBy": {"hierarchy": "ITEMHIERARCHY", "level": group_by_level},
    #     "filters": (
    #         [{"level": filter_level, "members": [filter_member]}]
    #         if filter_level and filter_member else []
    #     ),
    #     "sort": {"field": measure_name, "order": sort_order},
    #     "limit": top_n,
    # }
    # resp = requests.post(f"{DATA_API_BASE_URL}/data/query", json=payload)
    # resp.raise_for_status()
    # return resp.text
    # ------------------------------------------------------------------

    return json.dumps({
        "measure": measure_name,
        "version": version,
        "groupBy": level_key,
        "filter": {"level": filter_level, "member": filter_member} if filter_level else None,
        "sortOrder": sort_order,
        "resultCount": len(items),
        "data": [{"member": k, "value": v} for k, v in items],
    }, indent=2)


# ---------------------------------------------------------------------------
# Tool: list_measures
# ---------------------------------------------------------------------------

def list_measures(search_term: str | None = None) -> str:
    """List available measures, optionally filtered by keyword."""
    data = _load_measures()
    results = []

    for m in data["measures"]:
        # Keyword filter
        if search_term:
            st = search_term.lower()
            searchable = f"{m['name']} {m['displayName']} {m['description']}".lower()
            if st not in searchable:
                continue

        entry = {
            "name": m["name"],
            "displayName": m["displayName"],
            "description": m["description"],
            "versions": [v["name"] for v in m["versions"]],
        }
        if m.get("derivedMeasures"):
            entry["derivedMeasures"] = [
                {"name": dm["name"], "displayName": dm["displayName"], "description": dm["description"]}
                for dm in m["derivedMeasures"]
            ]
        results.append(entry)

    return json.dumps({"measures": results, "count": len(results)}, indent=2)


# ---------------------------------------------------------------------------
# Tool: compute_variance
# ---------------------------------------------------------------------------

def compute_variance(
    measure_name: str,
    version_a: str,
    version_b: str,
    group_by_level: str,
    variance_type: str = "percentage",
    filter_level: str | None = None,
    filter_member: str | None = None,
    sort_order: str = "desc",
    top_n: int | None = None,
) -> str:
    """
    Compute variance between two versions of a measure.

    Fetches data for both versions and computes the difference.
    """
    # Get data for both versions
    data_a = json.loads(query_measure_data(
        measure_name, version_a, group_by_level, filter_level, filter_member,
    ))
    data_b = json.loads(query_measure_data(
        measure_name, version_b, group_by_level, filter_level, filter_member,
    ))

    # Index version B by member
    b_map = {d["member"]: d["value"] for d in data_b["data"]}

    # Compute variance
    results = []
    for d in data_a["data"]:
        member = d["member"]
        val_a = d["value"]
        val_b = b_map.get(member)
        if val_b is None:
            continue

        if variance_type == "percentage":
            var_val = round(((val_a - val_b) / val_b) * 100, 2) if val_b != 0 else None
        else:
            var_val = round(val_a - val_b, 2)

        if var_val is not None:
            results.append({
                "member": member,
                f"{version_a}_value": val_a,
                f"{version_b}_value": val_b,
                "variance": var_val,
                "variance_type": variance_type,
            })

    # Sort
    results.sort(key=lambda x: x["variance"], reverse=(sort_order == "desc"))
    if top_n:
        results = results[:top_n]

    # ------------------------------------------------------------------
    # Production API call pattern:
    #
    # import requests
    # from config import DATA_API_BASE_URL
    #
    # payload = {
    #     "measures": [
    #         {"name": measure_name, "version": version_a},
    #         {"name": measure_name, "version": version_b},
    #     ],
    #     "computeVariance": {
    #         "type": variance_type,
    #         "baseVersion": version_b,
    #         "compareVersion": version_a,
    #     },
    #     "groupBy": {"hierarchy": "ITEMHIERARCHY", "level": group_by_level},
    #     "filters": (
    #         [{"level": filter_level, "members": [filter_member]}]
    #         if filter_level and filter_member else []
    #     ),
    #     "sort": {"field": "variance", "order": sort_order},
    #     "limit": top_n,
    # }
    # resp = requests.post(f"{DATA_API_BASE_URL}/data/variance", json=payload)
    # resp.raise_for_status()
    # return resp.text
    # ------------------------------------------------------------------

    return json.dumps({
        "measure": measure_name,
        "versionA": version_a,
        "versionB": version_b,
        "varianceType": variance_type,
        "groupBy": group_by_level,
        "filter": {"level": filter_level, "member": filter_member} if filter_level else None,
        "resultCount": len(results),
        "data": results,
    }, indent=2)


# ---------------------------------------------------------------------------
# Dispatcher: route tool calls to handlers
# ---------------------------------------------------------------------------

TOOL_HANDLERS = {
    "get_hierarchy_levels": get_hierarchy_levels,
    "get_members": get_members,
    "query_measure_data": query_measure_data,
    "list_measures": list_measures,
    "compute_variance": compute_variance,
}


def dispatch_tool_call(function_name: str, arguments: dict) -> str:
    """Route a tool call to its handler and return the result as a string."""
    handler = TOOL_HANDLERS.get(function_name)
    if handler is None:
        return json.dumps({"error": f"Unknown function: {function_name}"})
    return handler(**arguments)
