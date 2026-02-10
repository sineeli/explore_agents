"""
Azure AI Foundry Agent — Product Hierarchy & Measure Explorer

Uses the Azure OpenAI Assistants API with:
  1. File Search (Vector Store) — metadata about hierarchies, measures, members
     uploaded so the model can resolve natural language to actual names
  2. Function Calling (Pydantic-based) — fetch_data and get_members tools to
     call the data API. Raw data returned to the model for all math/sorting.

Flow:
  User question → Model searches vector store for metadata →
  Model resolves to actual measure/version/member names →
  Model calls fetch_data with resolved params →
  Raw data returned to model → Model does math/sorting/presentation
"""

import json
import time
from pathlib import Path
from openai import AzureOpenAI

from config import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT,
    AZURE_OPENAI_ENDPOINT,
)
from tools.definitions import TOOL_DEFINITIONS
from tools.handlers import dispatch_tool_call

DATA_DIR = Path(__file__).parent / "data"

SYSTEM_PROMPT = """\
You are a **Product Data Analyst Agent** for a retail merchandising planning platform.

You help users query product/location/time data by resolving their natural language
into the correct API parameters.

## Architecture

Data is organized across **3 dimensions**:
- **ITEM**: Product hierarchy (ITEM → STYLECOLOR → STYLE → SUBCLASS → CLASS → DEPARTMENT → SUBDEPARTMENT → DIVISION → TOTALPRODUCT)
- **TIME**: Fiscal time hierarchy (WEEK → MONTH → QUARTER → SEASON → HALFYEAR → FISCALYEAR → TOTALTIME)
- **LOCATION**: Store/channel hierarchy (STORE → DISTRICT → REGION → CHANNEL → TOTALLOCATION)

**Measures** are KPIs like Net Sales $, Gross Margin %, Inventory Units, etc.
**Versions** are time/plan perspectives like WP (Working Plan), LY (Last Year), LLY (Last Last Year), BUPP, BULP, PRODFC, ACT, OP, CP.
**Derived versions** are computed variances like BUPP_BULP_VP (BUPP/BULP % Variance).

## Your workflow

1. **Resolve metadata**: Use the file_search tool (vector store) to look up the correct:
   - Measure name (e.g. user says "sales retail" → NS_RTL, "gross margin percentage" → GM_PCT)
   - Version name (e.g. user says "working plan" → WP, "last year" → LY)
   - Member names (e.g. user says "w tops" → DEPARTMENT='W Tops', "fy2025" → FISCALYEAR='FY2025')
   - Derived versions (e.g. "BUPP/BULP % Variance" → BUPP_BULP_VP)

2. **Build the measure-version key**: Concatenate measure name + version name.
   Examples: NS_RTLWP, NS_RTLLY, GM_PCTBUPP_BULP_VP, NS_RTLPRODFC, NS_UNITSWP

3. **Call fetch_data**: With the resolved measure_versions, item_members, time_members,
   and optionally location_members and break_down_by.

4. **Present raw data + do math**: The API returns raw numbers. YOU do all:
   - Sorting (top/bottom performers)
   - Variance calculation (if user wants A vs B, fetch both and compute difference)
   - Percentage calculations
   - Presentation in tables/bullets

## Key rules

- When user says "break it down by channel/month/class", use the break_down_by parameter
- When user asks for two versions (e.g. "WP and LY"), include both in measure_versions
- If unsure about a member name, use get_members to look it up first
- Always resolve natural language to actual system names via the vector store metadata
- Present numbers formatted with commas and appropriate decimal places
- If the query is ambiguous, ask for clarification
"""


class ProductHierarchyAgent:
    """Manages the Azure OpenAI Assistant lifecycle."""

    def __init__(self, client: AzureOpenAI | None = None):
        self.client = client or AzureOpenAI(
            api_version=AZURE_OPENAI_API_VERSION,
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
        )
        self.assistant = None
        self.vector_store = None

    # ------------------------------------------------------------------
    # Setup: create vector store + assistant
    # ------------------------------------------------------------------

    def setup(self) -> "ProductHierarchyAgent":
        """Create the vector store, upload metadata files, and create the assistant."""
        self._create_vector_store()
        self._create_assistant()
        return self

    def _create_vector_store(self):
        """Upload hierarchy, measure, and member metadata into a vector store."""
        print("[setup] Creating vector store...")
        self.vector_store = self.client.vector_stores.create(
            name="product-metadata-store",
        )

        file_paths = [
            DATA_DIR / "hierarchies.json",
            DATA_DIR / "measures.json",
            DATA_DIR / "members.json",
        ]

        file_streams = [open(fp, "rb") for fp in file_paths]
        try:
            file_batch = self.client.vector_stores.file_batches.upload_and_poll(
                vector_store_id=self.vector_store.id,
                files=file_streams,
            )
            print(f"[setup] Vector store ready — status: {file_batch.status}, "
                  f"file_counts: {file_batch.file_counts}")
        finally:
            for f in file_streams:
                f.close()

    def _create_assistant(self):
        """Create the assistant with file_search + Pydantic-based function tools."""
        print("[setup] Creating assistant...")

        all_tools = TOOL_DEFINITIONS + [{"type": "file_search"}]

        self.assistant = self.client.beta.assistants.create(
            name="Product Hierarchy Explorer",
            instructions=SYSTEM_PROMPT,
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
        """
        Send a user message and get the assistant's response.

        Handles the full loop: add message → create run → poll →
        handle tool calls → return final text.
        """
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
        """Execute tool calls (validated via Pydantic) and submit results."""
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
