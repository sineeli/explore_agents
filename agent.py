"""
Azure AI Foundry Agent — Product Hierarchy & Measure Explorer

Uses the Azure OpenAI Assistants API with:
  1. Function Calling — for live data queries (hierarchy, members, measures, variance)
  2. File Search — for vector-store-backed metadata lookup (hierarchy docs, measure catalog)

The agent interprets natural language questions about product data, determines which
tools to call, and returns structured answers.
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
You are a **Product Data Analyst Agent** for a retail merchandising platform.

You help users explore product hierarchies, query sales/inventory measures, and
compute variances across time periods.

## Your capabilities

1. **Hierarchy Navigation** — You understand that product data is organized in
   hierarchical dimensions (Item Hierarchy, Buyer Hierarchy, Vendor Hierarchy).
   Each hierarchy has ordered levels from finest grain to aggregate totals.
   Use `get_hierarchy_levels` to discover the structure.

2. **Member Lookup** — Use `get_members` to find which members exist at a given
   level, optionally filtered by a parent level. For example, "which classes are
   under department DPT21?"

3. **Measure Queries** — Use `query_measure_data` to fetch KPI values (Net Sales,
   Gross Margin, Sell Through, Inventory, etc.) grouped by any hierarchy level
   and filtered by parent levels. Sort by top/bottom performers.

4. **Variance Analysis** — Use `compute_variance` to compare measure values across
   two time versions (e.g., This Week vs Last Year) and find the largest movers.

5. **Measure Discovery** — Use `list_measures` to find what measures and versions
   are available when the user mentions a metric you're not sure about.

## How to respond

- Always start by understanding the hierarchy structure if you're unsure.
- When the user says "top performing", default to Net Sales $ (NS_RTL), This Week (TW).
- When the user asks for "variance" or "change", use compute_variance.
- Present results in clear tables or bullet points.
- Reference the hierarchy level and member names from the data, not made-up names.
- If the user's question is ambiguous, ask for clarification about which measure,
  time version, or hierarchy level they mean.
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
        """Upload hierarchy and measure JSON files into a vector store for file search."""
        print("[setup] Creating vector store...")
        self.vector_store = self.client.vector_stores.create(
            name="product-metadata-store",
        )

        # Upload each metadata file
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
        """Create the assistant with function calling + file search tools."""
        print("[setup] Creating assistant...")

        # Combine function tools with file_search tool
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
    # Conversation: create thread, send messages, handle tool calls
    # ------------------------------------------------------------------

    def create_thread(self) -> str:
        """Create a new conversation thread. Returns the thread ID."""
        thread = self.client.beta.threads.create()
        return thread.id

    def chat(self, thread_id: str, user_message: str) -> str:
        """
        Send a user message and get the assistant's response.

        Handles the full loop:
          1. Add user message to thread
          2. Create a run
          3. Poll until complete (handling tool calls along the way)
          4. Return the final text response
        """
        # 1. Add user message
        self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_message,
        )

        # 2. Create run
        run = self.client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=self.assistant.id,
        )

        # 3. Poll and handle tool calls
        run = self._poll_run(thread_id, run.id)

        # 4. Extract assistant's final response
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
        """Poll the run until it completes, handling requires_action for tool calls."""
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
                # queued, in_progress — wait and retry
                time.sleep(1)

    def _handle_tool_calls(self, thread_id: str, run_id: str, run):
        """Execute requested tool calls and submit results back."""
        tool_calls = run.required_action.submit_tool_outputs.tool_calls
        tool_outputs = []

        for tc in tool_calls:
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments)

            print(f"  [tool] Calling {fn_name}({json.dumps(fn_args, separators=(',', ':'))})")
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
        """Delete the assistant and vector store (optional, for dev/testing)."""
        if self.assistant:
            self.client.beta.assistants.delete(self.assistant.id)
            print(f"[cleanup] Deleted assistant {self.assistant.id}")
        if self.vector_store:
            self.client.vector_stores.delete(self.vector_store.id)
            print(f"[cleanup] Deleted vector store {self.vector_store.id}")
