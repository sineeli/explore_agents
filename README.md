# Product Hierarchy Agent — Azure AI Foundry

A dynamically configured AI agent for retail merchandising data.
**Nothing is hardcoded** — hierarchy levels, members, measures, and versions
are fetched from the realm API at startup and indexed into Azure vector stores.

The only constants: **3 dimensions** (ITEM, TIME, LOCATION).

## Architecture

```
                          STARTUP
                            │
                            ▼
              ┌──────────────────────────┐
              │  MetadataLoader          │
              │  Fetches from realm API: │
              │  • hierarchies per dim   │
              │  • members per dim       │
              │  • measures + versions   │
              └─────────┬────────────────┘
                        │
                        ▼
              ┌──────────────────────────┐
              │  build_index_documents() │
              │  Creates 4 JSON indexes: │
              │  • item_index.json       │
              │  • time_index.json       │
              │  • location_index.json   │
              │  • measure_index.json    │
              └─────────┬────────────────┘
                        │ upload
                        ▼
              ┌──────────────────────────┐
              │  Azure Vector Store      │
              │  (per-dimension indexes) │
              └─────────┬────────────────┘
                        │
                        ▼
              ┌──────────────────────────┐
              │  Azure OpenAI Assistant  │
              │  • Dynamic system prompt │
              │    (from fetched metadata)│
              │  • file_search tool      │
              │  • fetch_data tool       │
              │  • get_members tool      │
              └──────────────────────────┘

                        RUNTIME
                          │
   User: "show me sales retail for w tops for fy2025 version WP and LY"
                          │
                          ▼
   1. Model searches item_index → "w tops" = DEPARTMENT='W Tops'
   2. Model searches time_index → "fy2025" = FISCALYEAR='FY2025'
   3. Model searches measure_index → "sales retail" = NS_RTL, "WP" + "LY"
   4. Model calls fetch_data(
        measure_versions=["NS_RTLWP", "NS_RTLLY"],
        item_members=[{level: "DEPARTMENT", member: "W Tops"}],
        time_members=[{level: "FISCALYEAR", member: "FY2025"}]
      )
   5. Raw data returned → model computes, sorts, presents
```

## Key Design Principles

- **Environment-driven**: All metadata fetched at startup from realm API
- **Per-dimension vector indexes**: item_index, time_index, location_index, measure_index
- **Model does all math**: Tools only fetch raw data — sorting, variance, formatting by the model
- **Pydantic tool schemas**: Generic models, no hardcoded levels or names
- **Dynamic system prompt**: Built from fetched metadata so model knows this environment's structure

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Azure OpenAI + realm API credentials
```

## Usage

```bash
python main.py                  # Interactive mode
python main.py --query "..."    # Single query
python main.py --cleanup        # Delete Azure resources after session
```

## Example Queries

```
show me sales retail for w tops for fy2025 for version WP and version LY
show me gross margin percentage for w tops-tees crew for fy2025 for version BUPP/BULP % Variance BUPP
show me sales units for apples for fy2025 season1
get me data for gross margin profit for women tops for 2024 and break it down by channel
fetch data for version PRODFC for womens apparel for 2023 fiscal year and break it down by month
```

## Project Structure

```
explore_agents/
├── config.py              # Azure OpenAI + realm API configuration
├── metadata_loader.py     # Fetches metadata from realm API, builds vector store docs
├── agent.py               # Assistant lifecycle (dynamic prompt + indexes + tools)
├── main.py                # CLI entry point
├── tools/
│   ├── models.py          # Generic Pydantic models (no hardcoded levels/names)
│   ├── definitions.py     # Auto-generates JSON Schema from Pydantic models
│   └── handlers.py        # Pydantic validation → API call → raw data
├── data/                  # LOCAL FALLBACK ONLY — production uses realm API
│   ├── hierarchies.json   # Sample hierarchy definitions
│   ├── measures.json      # Sample measure/version definitions
│   └── members.json       # Sample member data
├── requirements.txt
└── .env.example
```

## How It Works Per Environment

When a new environment loads:

1. **MetadataLoader.load_all()** calls the realm API:
   - `GET /metadata/dimensions/ITEM/hierarchies` → item hierarchy levels
   - `GET /metadata/dimensions/ITEM/members` → item member rows
   - Same for TIME and LOCATION
   - `GET /metadata/measures` → measures, versions, derived versions

2. **build_index_documents()** creates 4 JSON files:
   - `item_index.json` — ITEM hierarchies + all levels + distinct members per level
   - `time_index.json` — TIME hierarchies + all levels + distinct members per level
   - `location_index.json` — LOCATION hierarchies + all levels + distinct members
   - `measure_index.json` — measures with aliases + versions + derived versions + combined key examples

3. **build_system_prompt_context()** creates a dynamic prompt section listing:
   - This environment's hierarchy levels per dimension
   - Available measures with aliases
   - Available versions and derived versions
   - Combined key examples

4. These are uploaded to an Azure vector store and used by the assistant for NL resolution.

## Connecting to a Real Realm API

In `metadata_loader.py`, uncomment the `requests.get(...)` calls in:
- `_fetch_hierarchies()`
- `_fetch_members()`
- `_fetch_measures()`

In `tools/handlers.py`, uncomment the `requests.post(...)` calls in:
- `_handle_fetch_data()`
- `_handle_get_members()`

Set `use_local_fallback=False` in the MetadataLoader constructor.
