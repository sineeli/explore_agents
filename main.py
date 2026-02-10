#!/usr/bin/env python3
"""
Product Hierarchy Agent — Interactive CLI

Usage:
    python main.py                  # Interactive chat mode
    python main.py --query "..."    # Single query mode
    python main.py --cleanup        # Delete assistant + vector store after session
"""

import argparse

from agent import ProductHierarchyAgent


EXAMPLE_QUERIES = [
    "show me sales retail for w tops for fy2025 for version WP and version LY",
    "show me sales retail for w tops-tees for fy2025 for version WP",
    "show me sales retail for w tops-tees for fy2025 for version LLY",
    "show me gross margin percentage for w tops-tees crew for fy2025 for version BUPP/BULP % Variance BUPP",
    "show me sales units for apples for fy2025 season1",
    "get me data for gross margin profit for women tops for 2024 and break it down by channel",
    "fetch data for version PRODFC for womens apparel for 2023 fiscal year and break it down by month",
]


def run_interactive(agent: ProductHierarchyAgent, thread_id: str):
    """Run an interactive chat loop."""
    print("\n" + "=" * 60)
    print("  Product Hierarchy Agent — Interactive Mode")
    print("=" * 60)
    print("\nExample queries you can try:")
    for i, q in enumerate(EXAMPLE_QUERIES, 1):
        print(f"  {i}. {q}")
    print("\nType 'quit' or 'exit' to end the session.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        print("\nAssistant: ", end="", flush=True)
        response = agent.chat(thread_id, user_input)
        print(response)
        print()


def run_single_query(agent: ProductHierarchyAgent, thread_id: str, query: str):
    """Run a single query and print the result."""
    print(f"\nQuery: {query}\n")
    response = agent.chat(thread_id, query)
    print(f"Response:\n{response}")


def main():
    parser = argparse.ArgumentParser(description="Product Hierarchy Agent CLI")
    parser.add_argument("--query", "-q", type=str, help="Single query to run (non-interactive)")
    parser.add_argument("--cleanup", action="store_true", help="Delete assistant and vector store after session")
    args = parser.parse_args()

    print("Initializing agent...")
    agent = ProductHierarchyAgent()
    agent.setup()

    thread_id = agent.create_thread()
    print(f"Thread created: {thread_id}")

    try:
        if args.query:
            run_single_query(agent, thread_id, args.query)
        else:
            run_interactive(agent, thread_id)
    finally:
        if args.cleanup:
            agent.cleanup()
        else:
            print(f"\nAssistant ID: {agent.assistant.id}")
            print(f"Vector Store ID: {agent.vector_store.id}")
            print("(Run with --cleanup to delete these resources)")


if __name__ == "__main__":
    main()
