# Product Hierarchy Agent — Azure AI Foundry

An AI agent that explores hierarchical retail product data across 3 dimensions
(ITEM, TIME, LOCATION), queries measures/KPIs, and performs math/sorting/variance
using Azure OpenAI Assistants API with **file search** (vector stores) and
**Pydantic-based function calling**.

## Architecture

```
User: "show me sales retail for w tops for fy2025 for version WP and LY"
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│  Azure OpenAI Assistant (gpt-5.2)                        │
│                                                          │
│  1. file_search (vector store)                           │
│     ├── hierarchies.json  (3 dimensions, all levels)     │
│     ├── measures.json     (measures, versions, aliases)  │
│     └── members.json      (item/time/location members)   │
│                                                          │
│  2. Resolves NL → system names via vector store:         │
│     "sales retail" → NS_RTL                              │
│     "w tops" → DEPARTMENT='W Tops'                       │
│     "fy2025" → FISCALYEAR='FY2025'                       │
│     "WP and LY" → measure_versions: [NS_RTLWP, NS_RTLLY]│
│                                                          │
│  3. Calls fetch_data (Pydantic-validated)                │
│  4. Gets raw data back → model does math/sorting/display │
└───────────┬──────────────────────────────────────────────┘
            │ function calls
            ▼
┌──────────────────────────────────────────────────────────┐
│  Tool Handlers (tools/handlers.py)                       │
│  Pydantic validation → API call → raw data               │
│                                                          │
│  Production:                                             │
│    POST /api/v1/data/query        (fetch_data)           │
│    POST /api/v1/hierarchy/members (get_members)          │
└──────────────────────────────────────────────────────────┘
```

## Key Design Principles

- **Model does all the math**: Sorting, variance, percentages — the tools just fetch raw data
- **Vector store for metadata**: Hierarchies, measures, members uploaded to Azure vector store
  so the model can resolve natural language ("sales retail") to system names (NS_RTL)
- **Pydantic tool schemas**: Tool inputs defined as Pydantic models, auto-converted to JSON Schema
- **3 dimensions**: ITEM (product), TIME (fiscal calendar), LOCATION (store/channel)

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Azure OpenAI credentials
```

## Usage

```bash
# Interactive mode
python main.py

# Single query
python main.py --query "show me sales retail for w tops for fy2025 for version WP and LY"

# Cleanup resources after session
python main.py --cleanup
```

## Example Queries

```
show me sales retail for w tops for fy2025 for version WP and version LY
show me sales retail for w tops-tees for fy2025 for version WP
show me sales retail for w tops-tees for fy2025 for version LLY
show me gross margin percentage for w tops-tees crew for fy2025 for version BUPP/BULP % Variance BUPP
show me sales units for apples for fy2025 season1
get me data for gross margin profit for women tops for 2024 and break it down by channel
fetch data for version PRODFC for womens apparel for 2023 fiscal year and break it down by month
```

## Data Model

### 3 Dimensions

| Dimension | Hierarchy Levels |
|-----------|-----------------|
| **ITEM** | ITEM → STYLECOLOR → STYLE → SUBCLASS → CLASS → DEPARTMENT → SUBDEPARTMENT → DIVISION → TOTALPRODUCT |
| **TIME** | WEEK → MONTH → QUARTER → SEASON → HALFYEAR → FISCALYEAR → TOTALTIME |
| **LOCATION** | STORE → DISTRICT → REGION → CHANNEL → TOTALLOCATION |

### Measures

| Measure | System Name | Aliases |
|---------|-------------|---------|
| Net Sales $ | NS_RTL | sales retail, net sales, retail sales |
| Net Sales Units | NS_UNITS | sales units, units sold |
| Gross Margin $ | GM_RTL | gross margin, margin $, gross margin profit |
| Gross Margin % | GM_PCT | gross margin percentage, margin % |
| Sell Through % | SELL_THRU_PCT | sell through, sell-through |
| Inventory Units | INV_UNITS | inventory, stock units |
| Inventory $ | INV_RTL | inventory dollars |
| Receipt Units | RCPT_UNITS | receipts, receipt units |
| Receipt $ | RCPT_RTL | receipt dollars |
| Average Unit Retail | AUR | average unit retail, avg price |

### Versions

| Version | System Name | Description |
|---------|-------------|-------------|
| Working Plan | WP | Current working plan |
| Last Year | LY | Same period last year |
| Last Last Year | LLY | Two years ago |
| Actuals | ACT | Actual reported |
| BUPP | BUPP | Bottom-Up Plan Proposed |
| BULP | BULP | Bottom-Up Last Plan |
| Product Forecast | PRODFC | Product forecast |
| Original Plan | OP | Original plan |
| Current Plan | CP | Current plan |

### Derived Versions (Variances)

| Derived | Key | Formula |
|---------|-----|---------|
| BUPP/BULP % Var | BUPP_BULP_VP | ((BUPP-BULP)/BULP)*100 |
| WP/LY % Var | WP_LY_VP | ((WP-LY)/LY)*100 |
| WP/LY $ Var | WP_LY_VD | WP-LY |

### API Payload Structure

The `fetch_data` tool sends this to your backend:

```json
{
  "measureVersions": ["NS_RTLWP", "NS_RTLLY"],
  "dimensions": {
    "item": [{"level": "DEPARTMENT", "member": "W Tops"}],
    "time": [{"level": "FISCALYEAR", "member": "FY2025"}]
  },
  "breakDownBy": {"dimension": "LOCATION", "level": "CHANNEL"}
}
```

## Project Structure

```
explore_agents/
├── config.py                  # Azure OpenAI configuration
├── agent.py                   # Assistant lifecycle (vector store + tools + thread)
├── main.py                    # CLI entry point
├── tools/
│   ├── models.py              # Pydantic models for tool input schemas
│   ├── definitions.py         # Auto-generates JSON Schema from Pydantic models
│   └── handlers.py            # Tool handlers (Pydantic validation + API call)
├── data/
│   ├── hierarchies.json       # 3 dimensions with all hierarchy levels
│   ├── measures.json          # Measures, versions, aliases, derived versions
│   └── members.json           # Sample members for each dimension
├── requirements.txt
└── .env.example
```
