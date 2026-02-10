"""
Knowledge Source Example — Azure AI Search Agentic Retrieval
=============================================================

This file explains step-by-step how to create knowledge sources
for our 3-dimension product data (ITEM, TIME, LOCATION + measures).

The flow:
  1. Create SEARCH INDEXES (the actual searchable storage)
  2. Create KNOWLEDGE SOURCES (wrappers that point to indexes)
  3. Create a KNOWLEDGE BASE (orchestrator that ties sources + LLM together)
  4. RETRIEVE (query the knowledge base — LLM plans subqueries for you)

For our data, we create 4 search indexes and 4 knowledge sources:
  - item_index / item_ks       → product hierarchy members
  - time_index / time_ks       → fiscal time hierarchy members
  - location_index / location_ks → store/channel hierarchy members
  - measure_index / measure_ks  → measures, versions, derived versions

Prerequisites:
  pip install azure-search-documents>=11.7.0b2 azure-identity python-dotenv
  (requires the PREVIEW SDK — install with: pip install azure-search-documents --pre)
"""

import os
import json
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    # Index creation
    SearchIndex,
    SearchField,
    # Vector search (optional — knowledge base doesn't require it)
    VectorSearch,
    VectorSearchProfile,
    HnswAlgorithmConfiguration,
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    # Semantic search (REQUIRED for knowledge sources)
    SemanticSearch,
    SemanticConfiguration,
    SemanticPrioritizedFields,
    SemanticField,
    # Knowledge source
    SearchIndexKnowledgeSource,
    SearchIndexKnowledgeSourceParameters,
    SearchIndexFieldReference,
    # Knowledge base
    KnowledgeBase,
    KnowledgeBaseAzureOpenAIModel,
    KnowledgeSourceReference,
    KnowledgeRetrievalOutputMode,
)
from azure.search.documents import SearchIndexingBufferedSender

load_dotenv(override=True)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SEARCH_ENDPOINT = os.environ["SEARCH_ENDPOINT"]            # https://<your-search>.search.windows.net
AOAI_ENDPOINT = os.environ["AOAI_ENDPOINT"]                # https://<your-openai>.openai.azure.com
AOAI_GPT_DEPLOYMENT = os.getenv("AOAI_GPT_DEPLOYMENT", "gpt-5.2")
AOAI_GPT_MODEL = os.getenv("AOAI_GPT_MODEL", "gpt-5.2")
AOAI_EMBEDDING_DEPLOYMENT = os.getenv("AOAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large")
AOAI_EMBEDDING_MODEL = os.getenv("AOAI_EMBEDDING_MODEL", "text-embedding-3-large")

credential = DefaultAzureCredential()
index_client = SearchIndexClient(endpoint=SEARCH_ENDPOINT, credential=credential)


# ===================================================================
# STEP 1: CREATE SEARCH INDEXES
# ===================================================================
# Each index stores documents for one aspect of our metadata.
# The key decision: what fields do we need, and which are searchable?
#
# IMPORTANT: Semantic search must be enabled — knowledge sources require it.
# ===================================================================


def create_item_index():
    """
    Item dimension index.

    Think about what the model needs to search for:
    - User says "w tops" → needs to find DEPARTMENT='W Tops'
    - User says "apples" → needs to find CLASS='Apples'

    So we need searchable fields for each hierarchy level's member name,
    plus a "content" field that combines everything for semantic search.
    """
    index = SearchIndex(
        name="item-index",
        fields=[
            # Key field (required)
            SearchField(name="id", type="Edm.String", key=True, filterable=True),

            # The level this member belongs to (e.g. "CLASS", "DEPARTMENT")
            SearchField(name="level", type="Edm.String", filterable=True, sortable=True),

            # The actual member name (e.g. "W Tops", "Apples")
            SearchField(name="member", type="Edm.String", filterable=True, sortable=True),

            # Parent level and member (for hierarchy navigation)
            SearchField(name="parent_level", type="Edm.String", filterable=True),
            SearchField(name="parent_member", type="Edm.String", filterable=True),

            # The hierarchy this belongs to (e.g. "ITEMHIERARCHY")
            SearchField(name="hierarchy_name", type="Edm.String", filterable=True),

            # Combined text for semantic search — this is what gets searched
            # Contains: member name, level, parent, hierarchy path
            # e.g. "W Tops is a DEPARTMENT in the Item Hierarchy under Womens Tops division"
            SearchField(name="content", type="Edm.String", filterable=False, sortable=False),
        ],
        # Semantic search config — REQUIRED for knowledge sources
        semantic_search=SemanticSearch(
            default_configuration_name="item-semantic-config",
            configurations=[
                SemanticConfiguration(
                    name="item-semantic-config",
                    prioritized_fields=SemanticPrioritizedFields(
                        # Tell the semantic ranker which field has the main content
                        content_fields=[SemanticField(field_name="content")],
                    ),
                ),
            ],
        ),
    )

    index_client.create_or_update_index(index)
    print(f"Created index: {index.name}")
    return index.name


def create_time_index():
    """
    Time dimension index.

    User says "fy2025" → needs to find FISCALYEAR='FY2025'
    User says "season1" → needs to find SEASON='Season1'
    """
    index = SearchIndex(
        name="time-index",
        fields=[
            SearchField(name="id", type="Edm.String", key=True, filterable=True),
            SearchField(name="level", type="Edm.String", filterable=True, sortable=True),
            SearchField(name="member", type="Edm.String", filterable=True, sortable=True),
            SearchField(name="parent_level", type="Edm.String", filterable=True),
            SearchField(name="parent_member", type="Edm.String", filterable=True),
            SearchField(name="hierarchy_name", type="Edm.String", filterable=True),
            SearchField(name="content", type="Edm.String", filterable=False, sortable=False),
        ],
        semantic_search=SemanticSearch(
            default_configuration_name="time-semantic-config",
            configurations=[
                SemanticConfiguration(
                    name="time-semantic-config",
                    prioritized_fields=SemanticPrioritizedFields(
                        content_fields=[SemanticField(field_name="content")],
                    ),
                ),
            ],
        ),
    )

    index_client.create_or_update_index(index)
    print(f"Created index: {index.name}")
    return index.name


def create_location_index():
    """
    Location dimension index.

    User says "stores channel" → needs to find CHANNEL='Stores'
    User says "northeast" → needs to find REGION='Northeast'
    """
    index = SearchIndex(
        name="location-index",
        fields=[
            SearchField(name="id", type="Edm.String", key=True, filterable=True),
            SearchField(name="level", type="Edm.String", filterable=True, sortable=True),
            SearchField(name="member", type="Edm.String", filterable=True, sortable=True),
            SearchField(name="parent_level", type="Edm.String", filterable=True),
            SearchField(name="parent_member", type="Edm.String", filterable=True),
            SearchField(name="hierarchy_name", type="Edm.String", filterable=True),
            SearchField(name="content", type="Edm.String", filterable=False, sortable=False),
        ],
        semantic_search=SemanticSearch(
            default_configuration_name="location-semantic-config",
            configurations=[
                SemanticConfiguration(
                    name="location-semantic-config",
                    prioritized_fields=SemanticPrioritizedFields(
                        content_fields=[SemanticField(field_name="content")],
                    ),
                ),
            ],
        ),
    )

    index_client.create_or_update_index(index)
    print(f"Created index: {index.name}")
    return index.name


def create_measure_index():
    """
    Measure + version index.

    User says "sales retail" → needs to find measure NS_RTL
    User says "BUPP/BULP % Variance" → needs to find derived version BUPP_BULP_VP
    User says "working plan" → needs to find version WP

    Documents in this index are of 3 types:
      - measure: {name: "NS_RTL", displayName: "Net Sales $", aliases: [...]}
      - version: {name: "WP", displayName: "Working Plan"}
      - derived_version: {name: "BUPP_BULP_VP", formula: "((BUPP-BULP)/BULP)*100"}
    """
    index = SearchIndex(
        name="measure-index",
        fields=[
            SearchField(name="id", type="Edm.String", key=True, filterable=True),

            # What kind of document: "measure", "version", or "derived_version"
            SearchField(name="doc_type", type="Edm.String", filterable=True),

            # System name (e.g. "NS_RTL", "WP", "BUPP_BULP_VP")
            SearchField(name="name", type="Edm.String", filterable=True, sortable=True),

            # Display name (e.g. "Net Sales $", "Working Plan")
            SearchField(name="display_name", type="Edm.String", filterable=True),

            # Combined searchable text with aliases and descriptions
            SearchField(name="content", type="Edm.String", filterable=False, sortable=False),
        ],
        semantic_search=SemanticSearch(
            default_configuration_name="measure-semantic-config",
            configurations=[
                SemanticConfiguration(
                    name="measure-semantic-config",
                    prioritized_fields=SemanticPrioritizedFields(
                        content_fields=[SemanticField(field_name="content")],
                    ),
                ),
            ],
        ),
    )

    index_client.create_or_update_index(index)
    print(f"Created index: {index.name}")
    return index.name


# ===================================================================
# STEP 2: INDEX DOCUMENTS
# ===================================================================
# Convert our metadata into search documents and upload them.
# This is the key part — HOW you structure the documents determines
# how well the knowledge base can resolve natural language.
# ===================================================================


def build_dimension_documents(dimension_name: str, hierarchies: list, members: list) -> list[dict]:
    """
    Convert dimension metadata into search documents.

    Each document = one member at one level.
    The 'content' field is a rich text description for semantic search.

    Example document:
    {
        "id": "ITEM-CLASS-W Tops-Tees",
        "level": "CLASS",
        "member": "W Tops-Tees",
        "parent_level": "DEPARTMENT",
        "parent_member": "W Tops",
        "hierarchy_name": "ITEMHIERARCHY",
        "content": "W Tops-Tees is a CLASS in the Item Hierarchy.
                    It belongs under DEPARTMENT: W Tops.
                    Full path: W Tops-Tees (CLASS) → W Tops (DEPARTMENT) → ..."
    }
    """
    docs = []
    seen = set()

    # Get the primary hierarchy and its level order
    primary_hierarchy = hierarchies[0] if hierarchies else {}
    hierarchy_name = primary_hierarchy.get("name", "")
    levels = sorted(primary_hierarchy.get("levels", []), key=lambda x: x.get("order", 0))
    level_order = {lv["level"]: lv.get("order", 0) for lv in levels}

    for row in members:
        for level_info in levels:
            level_name = level_info["level"]
            member_value = row.get(level_name)
            if not member_value or not str(member_value).strip():
                continue

            doc_id = f"{dimension_name}-{level_name}-{member_value}"
            if doc_id in seen:
                continue
            seen.add(doc_id)

            # Find parent (next level up in hierarchy)
            parent_level = None
            parent_member = None
            current_order = level_order.get(level_name, 0)
            for plv in levels:
                if plv.get("order", 0) == current_order + 1:
                    parent_level = plv["level"]
                    parent_member = row.get(parent_level)
                    break

            # Build a rich content string for semantic search
            content_parts = [
                f"{member_value} is a member at the {level_name} level",
                f"in the {primary_hierarchy.get('displayName', hierarchy_name)}.",
            ]
            if parent_level and parent_member:
                content_parts.append(f"It belongs under {parent_level}: {parent_member}.")

            # Add the full hierarchy path from this member upward
            path_parts = []
            for plv in sorted(levels, key=lambda x: x.get("order", 0)):
                val = row.get(plv["level"])
                if val and str(val).strip():
                    path_parts.append(f"{val} ({plv['level']})")
            if path_parts:
                content_parts.append(f"Full hierarchy path: {' → '.join(path_parts)}.")

            docs.append({
                "id": doc_id.replace(" ", "_").replace("/", "_"),
                "level": level_name,
                "member": str(member_value),
                "parent_level": parent_level or "",
                "parent_member": str(parent_member) if parent_member else "",
                "hierarchy_name": hierarchy_name,
                "content": " ".join(content_parts),
            })

    return docs


def build_measure_documents(measures: list, versions: list, derived_versions: list) -> list[dict]:
    """
    Convert measure metadata into search documents.

    Three types of documents:
      1. measure: one per measure (NS_RTL, GM_PCT, etc.)
      2. version: one per version (WP, LY, BUPP, etc.)
      3. derived_version: one per derived version (BUPP_BULP_VP, etc.)

    The 'content' field includes aliases so "sales retail" finds NS_RTL.
    """
    docs = []

    for m in measures:
        aliases = m.get("aliases", [])
        alias_str = ", ".join(aliases) if aliases else ""
        content = (
            f"{m['name']} ({m.get('displayName', '')}) is a measure. "
            f"Description: {m.get('description', '')}. "
            f"Also known as: {alias_str}. "
            f"To use this measure, combine it with a version name. "
            f"For example: {m['name']}WP means {m.get('displayName', '')} Working Plan."
        )
        docs.append({
            "id": f"measure-{m['name']}",
            "doc_type": "measure",
            "name": m["name"],
            "display_name": m.get("displayName", m["name"]),
            "content": content,
        })

    for v in versions:
        content = (
            f"{v['name']} ({v.get('displayName', '')}) is a version. "
            f"Description: {v.get('description', '')}. "
            f"When combined with a measure, append this version name to the measure name. "
            f"For example: NS_RTL{v['name']} means Net Sales $ {v.get('displayName', '')}."
        )
        docs.append({
            "id": f"version-{v['name']}",
            "doc_type": "version",
            "name": v["name"],
            "display_name": v.get("displayName", v["name"]),
            "content": content,
        })

    for dv in derived_versions:
        content = (
            f"{dv['name']} ({dv.get('displayName', '')}) is a derived version (variance). "
            f"Description: {dv.get('description', '')}. "
            f"Compares {dv.get('baseVersion', '')} vs {dv.get('compareVersion', '')}. "
            f"Type: {dv.get('type', '')}. "
            f"When combined with a measure, append this derived version name to the measure name. "
            f"For example: GM_PCT{dv['name']} means Gross Margin % {dv.get('displayName', '')}."
        )
        docs.append({
            "id": f"derived-{dv['name']}",
            "doc_type": "derived_version",
            "name": dv["name"],
            "display_name": dv.get("displayName", dv["name"]),
            "content": content,
        })

    return docs


def upload_documents(index_name: str, documents: list[dict]):
    """Upload documents to a search index."""
    with SearchIndexingBufferedSender(
        endpoint=SEARCH_ENDPOINT,
        index_name=index_name,
        credential=credential,
    ) as sender:
        sender.upload_documents(documents=documents)
    print(f"Uploaded {len(documents)} documents to '{index_name}'")


# ===================================================================
# STEP 3: CREATE KNOWLEDGE SOURCES
# ===================================================================
# A knowledge source wraps a search index and tells the knowledge base
# what fields to use for search and what fields to return.
#
# Key concepts:
#   - source_data_fields: fields returned in the retrieval response
#     (this is what the agent gets back as grounding data)
#   - The semantic config on the index determines search behavior
# ===================================================================


def create_knowledge_source(ks_name: str, index_name: str, description: str, source_fields: list[str]):
    """
    Create a knowledge source pointing to a search index.

    source_fields: which fields to include in the retrieval response
    (the grounding data the agent receives).
    """
    ks = SearchIndexKnowledgeSource(
        name=ks_name,
        description=description,
        search_index_parameters=SearchIndexKnowledgeSourceParameters(
            search_index_name=index_name,
            # These fields are returned in the retrieval response
            # The agent uses them to extract the resolved names
            source_data_fields=[
                SearchIndexFieldReference(name=field) for field in source_fields
            ],
        ),
    )

    index_client.create_or_update_knowledge_source(knowledge_source=ks)
    print(f"Created knowledge source: {ks_name} → {index_name}")
    return ks_name


# ===================================================================
# STEP 4: CREATE KNOWLEDGE BASE
# ===================================================================
# The knowledge base ties everything together:
#   - References all 4 knowledge sources
#   - Connects to an LLM for query planning
#   - Configures output mode (raw grounding or answer synthesis)
# ===================================================================


def create_knowledge_base(
    kb_name: str,
    ks_names: list[str],
):
    """
    Create a knowledge base that orchestrates retrieval across all sources.

    When the agent asks "what is sales retail?", the LLM query planner will:
    1. Recognize this is about a measure
    2. Generate a subquery against the measure_ks
    3. Return the semantic-ranked results (NS_RTL with its aliases)
    """
    aoai_params = AzureOpenAIVectorizerParameters(
        resource_url=AOAI_ENDPOINT,
        deployment_name=AOAI_GPT_DEPLOYMENT,
        model_name=AOAI_GPT_MODEL,
    )

    kb = KnowledgeBase(
        name=kb_name,
        # LLM for query planning — decomposes complex queries into subqueries
        models=[KnowledgeBaseAzureOpenAIModel(azure_open_ai_parameters=aoai_params)],
        # All 4 knowledge sources
        knowledge_sources=[KnowledgeSourceReference(name=n) for n in ks_names],
        # Raw grounding data (no answer synthesis — our agent model does that)
        # Use ANSWER_SYNTHESIS if you want the knowledge base to generate answers
        output_mode=KnowledgeRetrievalOutputMode.GROUNDING_DATA,
    )

    index_client.create_or_update_knowledge_base(kb)
    print(f"Created knowledge base: {kb_name} with sources: {ks_names}")
    return kb_name


# ===================================================================
# STEP 5: RETRIEVE (query the knowledge base)
# ===================================================================
# This is what the agent calls at runtime instead of a vector store.
# The knowledge base handles query planning, multi-source search,
# semantic reranking — all automatically.
# ===================================================================


def retrieve_example(kb_name: str, ks_names: list[str]):
    """
    Example: how the agent would query the knowledge base.

    The retrieve call sends the user's message (+ chat history).
    The LLM query planner breaks it into subqueries across sources.
    Returns grounding data the agent can use.
    """
    from azure.search.documents.knowledgebases import KnowledgeBaseRetrievalClient
    from azure.search.documents.knowledgebases.models import (
        KnowledgeBaseRetrievalRequest,
        KnowledgeBaseMessage,
        KnowledgeBaseMessageTextContent,
        SearchIndexKnowledgeSourceParams,
    )

    retrieval_client = KnowledgeBaseRetrievalClient(
        endpoint=SEARCH_ENDPOINT,
        knowledge_base_name=kb_name,
        credential=credential,
    )

    # Simulate a user query
    user_query = "show me sales retail for w tops for fy2025 for version WP and LY"

    request = KnowledgeBaseRetrievalRequest(
        messages=[
            KnowledgeBaseMessage(
                role="user",
                content=[KnowledgeBaseMessageTextContent(text=user_query)],
            ),
        ],
        # Tell it which sources to query and what to return
        knowledge_source_params=[
            SearchIndexKnowledgeSourceParams(
                knowledge_source_name=ks_name,
                include_references=True,
                include_reference_source_data=True,
                always_query_source=True,
            )
            for ks_name in ks_names
        ],
        # Include the query plan activity for debugging
        include_activity=True,
    )

    result = retrieval_client.retrieve(retrieval_request=request)

    # The response contains:
    # 1. result.response — grounding data (ranked chunks from all sources)
    # 2. result.references — source documents with full fields
    # 3. result.activity — the query plan (what subqueries were generated)

    print("\n=== GROUNDING DATA ===")
    for resp in result.response:
        for content in resp.content:
            print(content.text)

    print("\n=== QUERY PLAN (ACTIVITY) ===")
    if result.activity:
        for a in result.activity:
            print(json.dumps(a.as_dict(), indent=2))

    print("\n=== REFERENCES ===")
    if result.references:
        for ref in result.references[:5]:  # Show first 5
            print(json.dumps(ref.as_dict(), indent=2))

    return result


# ===================================================================
# MAIN: Run the full setup
# ===================================================================

def main():
    """
    Full setup flow — run once per environment.

    In production, the MetadataLoader fetches this data from the realm API.
    Here we use the local sample data to demonstrate.
    """
    from metadata_loader import MetadataLoader

    # --- Load metadata (from realm API or local fallback) ---
    loader = MetadataLoader(api_base_url="http://localhost:8000/api/v1")
    realm = loader.load_all()

    # --- Step 1: Create search indexes ---
    item_idx = create_item_index()
    time_idx = create_time_index()
    location_idx = create_location_index()
    measure_idx = create_measure_index()

    # --- Step 2: Build and upload documents ---
    # Item dimension
    item_dim = realm.dimensions["ITEM"]
    item_docs = build_dimension_documents("ITEM", item_dim.hierarchies, item_dim.members)
    upload_documents(item_idx, item_docs)

    # Time dimension
    time_dim = realm.dimensions["TIME"]
    time_docs = build_dimension_documents("TIME", time_dim.hierarchies, time_dim.members)
    upload_documents(time_idx, time_docs)

    # Location dimension
    loc_dim = realm.dimensions["LOCATION"]
    loc_docs = build_dimension_documents("LOCATION", loc_dim.hierarchies, loc_dim.members)
    upload_documents(location_idx, loc_docs)

    # Measures
    measure_docs = build_measure_documents(realm.measures, realm.versions, realm.derived_versions)
    upload_documents(measure_idx, measure_docs)

    # --- Step 3: Create knowledge sources ---
    item_ks = create_knowledge_source(
        ks_name="item-ks",
        index_name=item_idx,
        description="Product item hierarchy members — resolves product names like 'w tops', 'apples' to hierarchy level and member",
        source_fields=["level", "member", "parent_level", "parent_member", "hierarchy_name"],
    )
    time_ks = create_knowledge_source(
        ks_name="time-ks",
        index_name=time_idx,
        description="Fiscal time hierarchy members — resolves time references like 'fy2025', 'season1' to hierarchy level and member",
        source_fields=["level", "member", "parent_level", "parent_member", "hierarchy_name"],
    )
    location_ks = create_knowledge_source(
        ks_name="location-ks",
        index_name=location_idx,
        description="Store/channel location hierarchy members — resolves location references like 'stores', 'northeast' to hierarchy level and member",
        source_fields=["level", "member", "parent_level", "parent_member", "hierarchy_name"],
    )
    measure_ks = create_knowledge_source(
        ks_name="measure-ks",
        index_name=measure_idx,
        description="Measures, versions, and derived versions — resolves names like 'sales retail' to NS_RTL, 'working plan' to WP, 'BUPP/BULP variance' to BUPP_BULP_VP",
        source_fields=["doc_type", "name", "display_name"],
    )

    # --- Step 4: Create knowledge base ---
    all_ks = [item_ks, time_ks, location_ks, measure_ks]
    kb_name = create_knowledge_base(
        kb_name="product-data-kb",
        ks_names=all_ks,
    )

    # --- Step 5: Test a retrieval ---
    print("\n" + "=" * 60)
    print("Testing retrieval...")
    print("=" * 60)
    retrieve_example(kb_name, all_ks)


if __name__ == "__main__":
    main()
