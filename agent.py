"""
Azure AI Foundry Agent — Dynamic Product Hierarchy & Measure Explorer

Nothing is hardcoded. On startup:
  1. MetadataLoader fetches hierarchies, members, measures from the realm API
  2. Builds 4 vector store indexes: item_index, time_index, location_index, measure_index
  3. Creates an assistant with dynamic system prompt + file_search + function calling
  4. The model resolves natural language via the indexes, calls fetch_data, does all math

The only constants are the 3 dimension names: ITEM, TIME, LOCATION.
"""

import io
import json
import time
from pathlib import Path
from openai import AzureOpenAI

from config import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT,
    AZURE_OPENAI_ENDPOINT,
    REALM_API_BASE_URL,
)
from metadata_loader import MetadataLoader, RealmMetadata, build_index_documents, build_system_prompt_context
from tools.definitions import TOOL_DEFINITIONS
from tools.handlers import dispatch_tool_call

SYSTEM_PROMPT_BASE = """\
You are a **Product Data Analyst Agent** for a retail merchandising planning platform.

You help users query product/location/time data by resolving their natural language
into the correct API parameters.

## Architecture

Data is organized across **3 dimensions**: ITEM, TIME, LOCATION.
Each dimension has hierarchies with ordered levels (varies per environment).
The hierarchy levels, members, measures, and versions for THIS environment
are described below and available in the vector store indexes.

## Your workflow

1. **Resolve metadata**: Search the vector store indexes to find:
   - The correct measure name (search measure_index)
   - The correct version name (search measure_index)
   - The correct item member + level (search item_index)
   - The correct time member + level (search time_index)
   - The correct location member + level (search location_index, if needed)

2. **Build the measure-version key**: Concatenate {measure_name}{version_name}.

3. **Call fetch_data**: With resolved measure_versions, item_members, time_members,
   and optionally location_members and break_down_by.

4. **Present raw data + do math**: The API returns raw numbers. YOU handle:
   - Sorting (top/bottom performers)
   - Variance calculation (fetch both versions, compute difference yourself)
   - Percentage calculations
   - Presentation in tables/bullets with formatted numbers

## Key rules

- When user says "break it down by X", use the break_down_by parameter
- When user asks for two versions (e.g. "WP and LY"), include both in measure_versions
- If unsure about a member name, use get_members to look it up
- Always resolve natural language to actual system names via vector store indexes
- If the query is ambiguous, ask for clarification

"""


class ProductHierarchyAgent:
    """
    Manages the Azure OpenAI Assistant lifecycle.

    Dynamically configured from environment metadata — no hardcoded values.
    """

    def __init__(self, client: AzureOpenAI | None = None):
        self.client = client or AzureOpenAI(
            api_version=AZURE_OPENAI_API_VERSION,
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
        )
        self.assistant = None
        self.vector_store = None
        self.realm: RealmMetadata | None = None

    def setup(self) -> "ProductHierarchyAgent":
        """
        Initialize the agent:
          1. Fetch metadata from realm API
          2. Build and upload vector store indexes
          3. Create the assistant with dynamic prompt
        """
        self._load_metadata()
        self._create_vector_store()
        self._create_assistant()
        return self

    # ------------------------------------------------------------------
    # Step 1: Fetch metadata
    # ------------------------------------------------------------------

    def _load_metadata(self):
        """Fetch all metadata from the realm API."""
        print("[setup] Fetching metadata from realm API...")
        loader = MetadataLoader(api_base_url=REALM_API_BASE_URL)
        self.realm = loader.load_all()

        dim_summary = []
        for dim_name, dim in self.realm.dimensions.items():
            h_count = len(dim.hierarchies)
            m_count = len(dim.members)
            dim_summary.append(f"{dim_name}({h_count} hierarchies, {m_count} members)")
        print(f"[setup] Loaded: {', '.join(dim_summary)}, "
              f"{len(self.realm.measures)} measures, "
              f"{len(self.realm.versions)} versions, "
              f"{len(self.realm.derived_versions)} derived versions")

    # ------------------------------------------------------------------
    # Step 2: Build vector store with per-dimension indexes
    # ------------------------------------------------------------------

    def _create_vector_store(self):
        """Build index documents from metadata and upload to vector store."""
        print("[setup] Creating vector store with per-dimension indexes...")
        self.vector_store = self.client.vector_stores.create(
            name="realm-metadata-indexes",
        )

        # Build index documents from the fetched metadata
        index_docs = build_index_documents(self.realm)

        # Upload each index as a named file
        file_streams = []
        for index_name, content_bytes in index_docs.items():
            stream = io.BytesIO(content_bytes)
            stream.name = f"{index_name}.json"
            file_streams.append(stream)

        file_batch = self.client.vector_stores.file_batches.upload_and_poll(
            vector_store_id=self.vector_store.id,
            files=file_streams,
        )
        print(f"[setup] Vector store ready — status: {file_batch.status}, "
              f"file_counts: {file_batch.file_counts}")
        print(f"[setup] Indexes: {', '.join(index_docs.keys())}")

    # ------------------------------------------------------------------
    # Step 3: Create assistant with dynamic prompt
    # ------------------------------------------------------------------

    def _create_assistant(self):
        """Create the assistant with dynamic system prompt + tools."""
        print("[setup] Creating assistant...")

        # Build dynamic system prompt from the fetched metadata
        env_context = build_system_prompt_context(self.realm)
        full_prompt = SYSTEM_PROMPT_BASE + "\n" + env_context

        all_tools = TOOL_DEFINITIONS + [{"type": "file_search"}]

        self.assistant = self.client.beta.assistants.create(
            name="Product Hierarchy Explorer",
            instructions=full_prompt,
            model=AZURE_OPENAI_DEPLOYMENT,
            tools=all_tools,
            tool_resources={
                "file_search": {
                    "vector_store_ids": [self.vector_store.id],
                }
            },
        )
        print(f"[setup] Assistant created — id: {self.assistant.id}")

    # ------------------------------------------------------------------
    # Conversation
    # ------------------------------------------------------------------

    def create_thread(self) -> str:
        """Create a new conversation thread."""
        thread = self.client.beta.threads.create()
        return thread.id

    def chat(self, thread_id: str, user_message: str) -> str:
        """Send a user message and return the assistant's response."""
        self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_message,
        )

        run = self.client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=self.assistant.id,
        )

        run = self._poll_run(thread_id, run.id)

        messages = self.client.beta.threads.messages.list(
            thread_id=thread_id,
            order="desc",
            limit=1,
        )
        for msg in messages.data:
            if msg.role == "assistant":
                return self._extract_text(msg)

        return "(No response from assistant)"

    def _poll_run(self, thread_id: str, run_id: str):
        """Poll the run, handling requires_action for function calls."""
        while True:
            run = self.client.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run_id,
            )

            if run.status == "completed":
                return run
            elif run.status == "requires_action":
                self._handle_tool_calls(thread_id, run_id, run)
            elif run.status in ("failed", "cancelled", "expired"):
                raise RuntimeError(f"Run ended with status: {run.status} — {run.last_error}")
            else:
                time.sleep(1)

    def _handle_tool_calls(self, thread_id: str, run_id: str, run):
        """Execute tool calls (Pydantic validated) and submit results."""
        tool_calls = run.required_action.submit_tool_outputs.tool_calls
        tool_outputs = []

        for tc in tool_calls:
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments)

            print(f"  [tool] {fn_name}({json.dumps(fn_args, separators=(',', ':'), ensure_ascii=False)[:200]})")
            result = dispatch_tool_call(fn_name, fn_args)

            tool_outputs.append({
                "tool_call_id": tc.id,
                "output": result,
            })

        self.client.beta.threads.runs.submit_tool_outputs(
            thread_id=thread_id,
            run_id=run_id,
            tool_outputs=tool_outputs,
        )

    @staticmethod
    def _extract_text(message) -> str:
        """Extract plain text from an assistant message."""
        parts = []
        for block in message.content:
            if block.type == "text":
                parts.append(block.text.value)
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self):
        """Delete the assistant and vector store."""
        if self.assistant:
            self.client.beta.assistants.delete(self.assistant.id)
            print(f"[cleanup] Deleted assistant {self.assistant.id}")
        if self.vector_store:
            self.client.vector_stores.delete(self.vector_store.id)
            print(f"[cleanup] Deleted vector store {self.vector_store.id}")
