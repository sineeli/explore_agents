"""
Pydantic models for tool input schemas.

These models are intentionally generic — no hardcoded hierarchy levels,
measure names, or member values. The model resolves those from the vector
store indexes at runtime.
"""

from pydantic import BaseModel, Field
from enum import Enum


# The only constant: the 3 dimension names
class DimensionEnum(str, Enum):
    ITEM = "ITEM"
    TIME = "TIME"
    LOCATION = "LOCATION"


class DimensionMember(BaseModel):
    """A member at a specific level within a dimension hierarchy."""
    level: str = Field(
        ...,
        description=(
            "The hierarchy level name as defined in this environment's metadata. "
            "Look up available levels from the dimension's vector store index."
        ),
    )
    member: str = Field(
        ...,
        description=(
            "The member value at that level. "
            "Resolve user's natural language to the actual member name "
            "using the dimension's vector store index."
        ),
    )


class BreakDownBy(BaseModel):
    """Specifies how to break down / group the results."""
    dimension: DimensionEnum = Field(
        ...,
        description="Which dimension to break down by (ITEM, TIME, or LOCATION)",
    )
    level: str = Field(
        ...,
        description=(
            "The level within that dimension to group by. "
            "Must be a valid level from the environment's hierarchy metadata."
        ),
    )


class FetchDataInput(BaseModel):
    """
    Fetch measure data from the data API.

    First resolve the user's natural language into correct measure names,
    version names, and dimension members using the vector store indexes.
    Then call this function with the resolved parameters.

    The raw data is returned for the model to do all math, sorting,
    variance calculations, and presentation.
    """

    measure_versions: list[str] = Field(
        ...,
        description=(
            "List of measure-version combined keys to fetch. "
            "Each key is {measure_name}{version_name} concatenated. "
            "Look up the correct measure name and version name from the "
            "measure_index in the vector store, then concatenate them. "
            "For derived versions (variances), use the derived version name "
            "as the version part."
        ),
    )

    item_members: list[DimensionMember] = Field(
        ...,
        description=(
            "Members from the ITEM dimension to filter on. "
            "Provide at least one member at any level of the item hierarchy. "
            "Resolve user's natural language to actual member names "
            "using the item_index in the vector store."
        ),
    )

    time_members: list[DimensionMember] = Field(
        ...,
        description=(
            "Members from the TIME dimension to filter on. "
            "Resolve user's natural language to actual member names "
            "using the time_index in the vector store."
        ),
    )

    location_members: list[DimensionMember] | None = Field(
        default=None,
        description=(
            "Optional. Members from the LOCATION dimension to filter on. "
            "Omit or leave empty for all locations. "
            "Resolve using the location_index in the vector store."
        ),
    )

    break_down_by: BreakDownBy | None = Field(
        default=None,
        description=(
            "Optional. Break down results by a dimension level. "
            "Use when user says 'break it down by ...' or 'group by ...'. "
            "The API returns data grouped by each member at that level."
        ),
    )


class GetMembersInput(BaseModel):
    """
    Look up available members at a specific hierarchy level within a dimension.

    Use this when you need to resolve a user's natural language to actual member
    names, or to verify a member exists before calling fetch_data.
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
            "Must be a valid level from the environment's hierarchy metadata."
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
