"""
Tool definitions generated from Pydantic models.

Converts the Pydantic input models into the JSON Schema format required
by the Azure OpenAI Assistants API function calling interface.
"""

from tools.models import FetchDataInput, GetMembersInput


def _pydantic_to_tool_def(name: str, model_cls) -> dict:
    """Convert a Pydantic model class into an Assistants API tool definition."""
    schema = model_cls.model_json_schema()

    # Extract description from the model's docstring
    description = (model_cls.__doc__ or "").strip()

    # Build the parameters object from the JSON schema
    parameters = {
        "type": "object",
        "properties": schema.get("properties", {}),
        "required": schema.get("required", []),
    }

    # Include $defs if the schema uses nested models (e.g. DimensionMember, BreakDownBy)
    if "$defs" in schema:
        parameters["$defs"] = schema["$defs"]

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


TOOL_DEFINITIONS = [
    _pydantic_to_tool_def("fetch_data", FetchDataInput),
    _pydantic_to_tool_def("get_members", GetMembersInput),
]
