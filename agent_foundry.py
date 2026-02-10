"""
Azure AI Foundry Agent Service — Alternative implementation.

This uses the newer `azure-ai-projects` SDK (Foundry Agent Service)
instead of the classic `openai` Assistants API. Both approaches work;
this one integrates more natively with Azure AI Foundry projects.

Prerequisites:
    pip install azure-ai-projects azure-identity

Setup:
    export AZURE_AI_PROJECT_CONNECTION_STRING="<your-connection-string>"
    # Connection string from Azure AI Foundry project settings

This is provided as a reference — the primary agent.py uses the classic
Assistants API which is more widely deployed.
"""

import json
import time
from pathlib import Path

# Uncomment when using this implementation:
# from azure.ai.projects import AIProjectClient
# from azure.ai.projects.models import (
#     FunctionTool,
#     FilePurpose,
#     FileSearchTool,
#     VectorStoreDataSource,
#     VectorStoreDataSourceAssetType,
# )
# from azure.identity import DefaultAzureCredential

from tools.definitions import TOOL_DEFINITIONS
from tools.handlers import dispatch_tool_call

DATA_DIR = Path(__file__).parent / "data"

SYSTEM_PROMPT = """\
You are a **Product Data Analyst Agent** for a retail merchandising platform.

You help users explore product hierarchies, query sales/inventory measures, and
compute variances across time periods.

Use your tools to:
1. Discover hierarchy structures (get_hierarchy_levels)
2. Look up members at hierarchy levels (get_members)
3. Query measure data with grouping and filtering (query_measure_data)
4. List available measures (list_measures)
5. Compute variances between time versions (compute_variance)

When users ask about "top performing" items, default to Net Sales $ (NS_RTL).
When users ask for variance/change, use compute_variance.
Present results in clear tables.
"""


def create_foundry_agent():
    """
    Create an agent using Azure AI Foundry Agent Service.

    This is the newer approach recommended by Microsoft for new projects.
    It uses the azure-ai-projects SDK with DefaultAzureCredential.
    """
    # 1. Initialize the project client
    # project_client = AIProjectClient.from_connection_string(
    #     credential=DefaultAzureCredential(),
    #     conn_str=os.environ["AZURE_AI_PROJECT_CONNECTION_STRING"],
    # )

    # 2. Upload metadata files for file search
    # uploaded_files = []
    # for filename in ["hierarchies.json", "measures.json", "members.json"]:
    #     filepath = DATA_DIR / filename
    #     uploaded = project_client.agents.upload_file_and_poll(
    #         file_path=str(filepath),
    #         purpose=FilePurpose.AGENTS,
    #     )
    #     uploaded_files.append(uploaded)
    #     print(f"Uploaded {filename} -> {uploaded.id}")

    # 3. Create vector store from uploaded files
    # vector_store = project_client.agents.create_vector_store_and_poll(
    #     file_ids=[f.id for f in uploaded_files],
    #     name="product-metadata-store",
    # )
    # print(f"Vector store created: {vector_store.id}")

    # 4. Build function tools from definitions
    # The Foundry SDK can parse function schemas from docstrings or dicts.
    # Here we convert our existing TOOL_DEFINITIONS into FunctionTool objects:
    #
    # function_tools = []
    # for td in TOOL_DEFINITIONS:
    #     fn = td["function"]
    #     function_tools.append(FunctionTool(
    #         name=fn["name"],
    #         description=fn["description"],
    #         parameters=fn["parameters"],
    #     ))

    # 5. Create the agent with both file search and function tools
    # file_search_tool = FileSearchTool(
    #     vector_store_ids=[vector_store.id],
    # )
    #
    # agent = project_client.agents.create_agent(
    #     model="gpt-5.2",
    #     name="Product Hierarchy Explorer",
    #     instructions=SYSTEM_PROMPT,
    #     tools=file_search_tool.definitions + [t for ft in function_tools for t in ft.definitions],
    #     tool_resources=file_search_tool.resources,
    # )
    # print(f"Agent created: {agent.id}")

    # 6. Create a thread and run conversation
    # thread = project_client.agents.create_thread()
    #
    # def chat(user_message: str) -> str:
    #     project_client.agents.create_message(
    #         thread_id=thread.id,
    #         role="user",
    #         content=user_message,
    #     )
    #     run = project_client.agents.create_and_process_run(
    #         thread_id=thread.id,
    #         agent_id=agent.id,
    #     )
    #
    #     # Handle requires_action for function calls
    #     while run.status == "requires_action":
    #         tool_calls = run.required_action.submit_tool_outputs.tool_calls
    #         tool_outputs = []
    #         for tc in tool_calls:
    #             args = json.loads(tc.function.arguments)
    #             result = dispatch_tool_call(tc.function.name, args)
    #             tool_outputs.append({"tool_call_id": tc.id, "output": result})
    #
    #         run = project_client.agents.submit_tool_outputs_to_run(
    #             thread_id=thread.id,
    #             run_id=run.id,
    #             tool_outputs=tool_outputs,
    #         )
    #
    #     messages = project_client.agents.list_messages(thread_id=thread.id)
    #     return messages.get_last_text_message_by_role("assistant")
    #
    # return chat

    print("Foundry Agent Service implementation (commented reference code).")
    print("Uncomment and install azure-ai-projects to use this approach.")


if __name__ == "__main__":
    create_foundry_agent()
