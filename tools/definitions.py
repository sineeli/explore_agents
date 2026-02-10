"""
Tool (function) definitions for the Azure OpenAI Assistants agent.

Each tool maps to a capability the agent can invoke:
  - get_hierarchy_levels: understand what levels exist in a hierarchy
  - get_members: fetch members at a given level, optionally filtered by parent
  - query_measure_data: fetch measure/metric data for members
  - list_measures: list all available measures and their versions
  - compute_variance: compute variance between two measure versions
"""

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_hierarchy_levels",
            "description": (
                "Returns the ordered list of levels for a given hierarchy "
                "(e.g. ITEMHIERARCHY, BUYERHIERARCHY, VENDORHIERARCHY). "
                "Use this to understand the dimension structure before querying data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hierarchy_name": {
                        "type": "string",
                        "description": (
                            "Name of the hierarchy. "
                            "One of: ITEMHIERARCHY, BUYERHIERARCHY, VENDORHIERARCHY, "
                            "SUBCLASSATTRIBUTEHIERARCHY"
                        ),
                    }
                },
                "required": ["hierarchy_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_members",
            "description": (
                "Fetch members (nodes) at a specific hierarchy level. "
                "Optionally filter by a parent member at a higher level. "
                "For example: get all CLASS members under DEPARTMENT='DPT21'. "
                "Returns a list of member identifiers at the requested level."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hierarchy_name": {
                        "type": "string",
                        "description": "Name of the hierarchy (e.g. ITEMHIERARCHY)",
                    },
                    "level": {
                        "type": "string",
                        "description": (
                            "The level to retrieve members from "
                            "(e.g. ITEM, STYLECOLOR, STYLE, SUBCLASS, CLASS, DEPARTMENT, DIVISION, TOTALPRODUCT)"
                        ),
                    },
                    "parent_level": {
                        "type": "string",
                        "description": "Optional. The parent level to filter by (must be a higher-order level than 'level').",
                    },
                    "parent_member": {
                        "type": "string",
                        "description": "Optional. The specific parent member value to filter by (e.g. 'DPT21').",
                    },
                },
                "required": ["hierarchy_name", "level"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_measure_data",
            "description": (
                "Query measure/metric data for specific members. "
                "Provide the measure name (e.g. NS_RTL for Net Sales $), "
                "the version (e.g. TW for This Week, LY for Last Year), "
                "the dimension level to group by, and optional filters. "
                "Returns a ranked list of members with their measure values. "
                "Use this to answer questions like 'top performing classes by net sales'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "measure_name": {
                        "type": "string",
                        "description": (
                            "The measure to query. Examples: NS_RTL (Net Sales $), "
                            "NS_UNITS (Net Sales Units), GM_RTL (Gross Margin $), "
                            "GM_PCT (Gross Margin %), SELL_THRU_PCT (Sell Through %), "
                            "INV_UNITS (Inventory Units)"
                        ),
                    },
                    "version": {
                        "type": "string",
                        "description": (
                            "The time version of the measure. "
                            "Options: TW (This Week), LW (Last Week), LY (Last Year), "
                            "TDC (To Date Current), TDC2 (To Date Current 2), LTRP (Last TRP)"
                        ),
                    },
                    "group_by_level": {
                        "type": "string",
                        "description": "The hierarchy level to group/aggregate results by (e.g. CLASS, DEPARTMENT, SUBCLASS).",
                    },
                    "filter_level": {
                        "type": "string",
                        "description": "Optional. A higher-level dimension to filter on (e.g. DEPARTMENT).",
                    },
                    "filter_member": {
                        "type": "string",
                        "description": "Optional. The member value to filter on at filter_level (e.g. 'DPT21').",
                    },
                    "sort_order": {
                        "type": "string",
                        "enum": ["desc", "asc"],
                        "description": "Sort order for results. 'desc' for top performers, 'asc' for bottom. Default: desc.",
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Optional. Return only top N results. Default returns all.",
                    },
                },
                "required": ["measure_name", "version", "group_by_level"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_measures",
            "description": (
                "List all available measures, their versions, and derived measures. "
                "Use this to understand what metrics are available before querying data. "
                "Returns measure names, display names, descriptions, and available versions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "search_term": {
                        "type": "string",
                        "description": "Optional keyword to filter measures (e.g. 'sales', 'margin', 'inventory').",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_variance",
            "description": (
                "Compute variance (difference or percentage change) between two versions "
                "of the same measure for given members. For example, compute the variance "
                "of Net Sales $ between This Week and Last Year for all classes under a department. "
                "Use this when the user asks for 'variance', 'change', 'comparison', or 'vs'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "measure_name": {
                        "type": "string",
                        "description": "The base measure (e.g. NS_RTL, GM_RTL).",
                    },
                    "version_a": {
                        "type": "string",
                        "description": "First version to compare (e.g. TW, TDC2).",
                    },
                    "version_b": {
                        "type": "string",
                        "description": "Second version to compare (e.g. LY, LTRP).",
                    },
                    "variance_type": {
                        "type": "string",
                        "enum": ["absolute", "percentage"],
                        "description": "Type of variance: 'absolute' (A-B) or 'percentage' ((A-B)/B * 100). Default: percentage.",
                    },
                    "group_by_level": {
                        "type": "string",
                        "description": "Hierarchy level to group results by.",
                    },
                    "filter_level": {
                        "type": "string",
                        "description": "Optional. Higher-level filter dimension.",
                    },
                    "filter_member": {
                        "type": "string",
                        "description": "Optional. Member value at filter_level.",
                    },
                    "sort_order": {
                        "type": "string",
                        "enum": ["desc", "asc"],
                        "description": "Sort by variance value. Default: desc (largest variance first).",
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Optional. Return only top N results.",
                    },
                },
                "required": ["measure_name", "version_a", "version_b", "group_by_level"],
            },
        },
    },
]
