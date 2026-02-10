"""
Pydantic models for tool input schemas.

These models define the structure of arguments for each tool.
They are converted to JSON Schema for the Azure OpenAI Assistants API
function definitions, and used for runtime validation in handlers.
"""

from pydantic import BaseModel, Field
from enum import Enum


# ---------------------------------------------------------------------------
# Shared enums and sub-models
# ---------------------------------------------------------------------------

class DimensionEnum(str, Enum):
    ITEM = "ITEM"
    TIME = "TIME"
    LOCATION = "LOCATION"


class DimensionMember(BaseModel):
    """A member at a specific level within a dimension hierarchy."""
    level: str = Field(
        ...,
        description=(
            "The hierarchy level. "
            "ITEM: ITEM, STYLECOLOR, STYLE, SUBCLASS, CLASS, DEPARTMENT, SUBDEPARTMENT, DIVISION, TOTALPRODUCT. "
            "TIME: WEEK, MONTH, QUARTER, SEASON, HALFYEAR, FISCALYEAR, TOTALTIME. "
            "LOCATION: STORE, DISTRICT, REGION, CHANNEL, TOTALLOCATION."
        ),
    )
    member: str = Field(
        ...,
        description="The member value at that level (e.g. 'W Tops', 'FY2025', 'Stores')",
    )


class BreakDownBy(BaseModel):
    """Specifies how to break down / group the results."""
    dimension: DimensionEnum = Field(
        ...,
        description="Which dimension to break down by (ITEM, TIME, or LOCATION)",
    )
    level: str = Field(
        ...,
        description="The level within that dimension to group by (e.g. CHANNEL, MONTH, CLASS)",
    )


# ---------------------------------------------------------------------------
# Tool: fetch_data
# ---------------------------------------------------------------------------

class FetchDataInput(BaseModel):
    """
    Fetch measure data from the data API.

    The model should first resolve the user's natural language into the correct
    measure names, version names, and dimension members using the metadata in
    the vector store. Then call this function with the resolved parameters.

    The raw data is returned to the model for any math, sorting, variance,
    or presentation the user requested.
    """

    measure_versions: list[str] = Field(
        ...,
        description=(
            "List of measure-version combined keys to fetch. "
            "Each key is {measure_name}{version_name} concatenated. "
            "Examples: "
            "'NS_RTLWP' (Net Sales $ Working Plan), "
            "'NS_RTLLY' (Net Sales $ Last Year), "
            "'NS_RTLLLY' (Net Sales $ Last Last Year), "
            "'GM_PCTBUPP' (Gross Margin % BUPP), "
            "'GM_PCTBUPP_BULP_VP' (Gross Margin % BUPP/BULP % Variance), "
            "'NS_RTLPRODFC' (Net Sales $ Product Forecast), "
            "'NS_UNITSBUPP' (Net Sales Units BUPP). "
            "Look up the correct measure and version from the vector store metadata, "
            "then concatenate them."
        ),
    )

    item_members: list[DimensionMember] = Field(
        ...,
        description=(
            "Members from the ITEM dimension to filter on. "
            "Provide at least one member at any level. "
            "Resolve user's natural language (e.g. 'w tops', 'womens apparel', 'apples') "
            "to actual member names using the vector store metadata. "
            "Examples: "
            "level=DEPARTMENT member='W Tops', "
            "level=CLASS member='W Tops-Tees', "
            "level=SUBCLASS member='W Tops-Tees Crew', "
            "level=DIVISION member='Womens Apparel', "
            "level=CLASS member='Apples'."
        ),
    )

    time_members: list[DimensionMember] = Field(
        ...,
        description=(
            "Members from the TIME dimension to filter on. "
            "Resolve user's natural language (e.g. 'fy2025', '2024 fiscal year', 'season1') "
            "to actual member names. "
            "Examples: "
            "level=FISCALYEAR member='FY2025', "
            "level=SEASON member='Season1', "
            "level=QUARTER member='Q1-2025', "
            "level=MONTH member='Feb-2025'."
        ),
    )

    location_members: list[DimensionMember] | None = Field(
        default=None,
        description=(
            "Optional. Members from the LOCATION dimension to filter on. "
            "Omit for all locations. "
            "Examples: level=CHANNEL member='Stores', level=REGION member='Northeast'."
        ),
    )

    break_down_by: BreakDownBy | None = Field(
        default=None,
        description=(
            "Optional. Break down results by a dimension level. "
            "Use when user says 'break it down by channel', 'break it down by month', etc. "
            "The API returns data grouped by each member at that level."
        ),
    )


# ---------------------------------------------------------------------------
# Tool: get_members
# ---------------------------------------------------------------------------

class GetMembersInput(BaseModel):
    """
    Look up available members at a specific hierarchy level within a dimension.

    Use this when you need to resolve a user's natural language to actual member
    names, or when you need to verify that a member exists before calling fetch_data.
    Optionally filter by a parent member at a higher level.
    """

    dimension: DimensionEnum = Field(
        ...,
        description="Which dimension to look up members in (ITEM, TIME, or LOCATION)",
    )

    level: str = Field(
        ...,
        description=(
            "The hierarchy level to get members from. "
            "ITEM: ITEM, STYLECOLOR, STYLE, SUBCLASS, CLASS, DEPARTMENT, SUBDEPARTMENT, DIVISION, TOTALPRODUCT. "
            "TIME: WEEK, MONTH, QUARTER, SEASON, HALFYEAR, FISCALYEAR, TOTALTIME. "
            "LOCATION: STORE, DISTRICT, REGION, CHANNEL, TOTALLOCATION."
        ),
    )

    parent_level: str | None = Field(
        default=None,
        description="Optional. A higher level to filter by.",
    )

    parent_member: str | None = Field(
        default=None,
        description="Optional. The member at parent_level to filter under.",
    )
