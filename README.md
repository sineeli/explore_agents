# Product Hierarchy Agent — Azure AI Foundry

An AI agent that explores hierarchical retail product data, queries measures/KPIs,
and computes variances using Azure OpenAI Assistants API with **function calling**
and **file search** (vector stores).

## Architecture

```
User Query (natural language)
        │
        ▼
┌─────────────────────────────────────────┐
│  Azure OpenAI Assistant                 │
│  (gpt-5.2 deployment)                  │
│                                         │
│  Tools:                                 │
│  ├── file_search (vector store)         │
│  │   └── hierarchies.json              │
│  │   └── measures.json                 │
│  │   └── members.json                  │
│  │                                      │
│  ├── get_hierarchy_levels()             │
│  ├── get_members()                      │
│  ├── query_measure_data()              │
│  ├── list_measures()                    │
│  └── compute_variance()                │
└────────────┬────────────────────────────┘
             │ function calls
             ▼
┌─────────────────────────────────────────┐
│  Tool Handlers (tools/handlers.py)      │
│  ├── Local mock (JSON files)            │
│  └── Production: HTTP API calls         │
│      POST /api/v1/hierarchy/members     │
│      POST /api/v1/data/query            │
│      POST /api/v1/data/variance         │
└─────────────────────────────────────────┘
```

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
python main.py --query "Show me top performing classes under department DPT21"

# Cleanup resources after session
python main.py --cleanup
```

## Example Queries

- "Show me the hierarchy levels for Item Hierarchy"
- "What classes exist under department DPT21?"
- "Top 5 performing subclasses by Net Sales this week"
- "Compute variance of Gross Margin between This Week and Last Year for all classes"
- "Which vendors supply items in subclass SCLS21243?"
- "List all available measures related to sales"

## Two Implementation Options

| File | SDK | Notes |
|------|-----|-------|
| `agent.py` | `openai` (AzureOpenAI) | Classic Assistants API — widely deployed |
| `agent_foundry.py` | `azure-ai-projects` | Newer Foundry Agent Service — reference code |

## Data Model

### Hierarchies
Product data is organized in hierarchical dimensions. The **Item Hierarchy** is primary:

```
ITEM → STYLECOLOR → STYLE → SUBCLASS → CLASS → DEPARTMENT → SUBDEPARTMENT → DIVISION → TOTALPRODUCT
```

Additional hierarchies: Buyer, Vendor, Subclass Attribute.

### Measures
KPIs with time versions:

| Measure | Versions |
|---------|----------|
| Net Sales $ (NS_RTL) | TW, LW, LY, TDC, TDC2, LTRP |
| Net Sales Units (NS_UNITS) | TW, LW, LY, TDC |
| Gross Margin $ (GM_RTL) | TW, LW, LY, TDC |
| Gross Margin % (GM_PCT) | TW, LY |
| Sell Through % (SELL_THRU_PCT) | TW, LY |
| Inventory Units (INV_UNITS) | TW, LW |

### API Payload Structure

When connecting to a real backend, the query pattern is:

```json
{
  "measures": [{"name": "NS_RTL", "version": "TW"}],
  "groupBy": {"hierarchy": "ITEMHIERARCHY", "level": "CLASS"},
  "filters": [{"level": "DEPARTMENT", "members": ["DPT21"]}],
  "sort": {"field": "NS_RTL", "order": "desc"},
  "limit": 10
}
```
