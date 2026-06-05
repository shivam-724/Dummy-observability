"""
main.py — CLI entry point for the LangGraph Arithmetic Orchestrator.

Usage:
    python main.py

The program accepts natural-language arithmetic word problems and solves
them step by step using a Groq-powered LLM orchestrator + LangGraph.
"""

import os
import json
import logging
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage

from arithmetic_agent.graph import build_graph
from arithmetic_agent.nodes import parse_response

# ── OpenTelemetry ─────────────────────────────────────────────────────────────
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry._logs import set_logger_provider
from opentelemetry.instrumentation.logging import LoggingInstrumentor


def setup_otel_logging() -> None:
    """
    Programmatically configure OTel logging pipeline.
    Runs with plain `python main.py` — no CLI wrapper needed.

    Pipeline:
        Python logger.info() calls
            → LoggingInstrumentor bridges them into OTel
            → BatchLogRecordProcessor batches records and flushes every 5s
            → OTLPLogExporter ships them to the Collector on port 4317
    """
    resource = Resource.create({"service.name": "arithmetic-orchestrator"})

    exporter = OTLPLogExporter(
        endpoint="http://localhost:4317",
        insecure=True,
    )

    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(BatchLogRecordProcessor(exporter))

    set_logger_provider(provider)

    LoggingInstrumentor().instrument(set_logging_format=True)

    logging.getLogger(__name__).info(
        "OTel logging pipeline initialised",
        extra={"exporter": "otlp-grpc", "endpoint": "localhost:4317"},
    )


# ── Colour / style helpers ────────────────────────────────────────────────────
RESET = "\033[0m"
BOLD  = "\033[1m"
CYAN  = "\033[96m"
GREEN = "\033[92m"
YELLOW= "\033[93m"
MAGENTA="\033[95m"
RED   = "\033[91m"
DIM   = "\033[2m"

NODE_STYLE = {
    "orchestrator": (CYAN,   "[ORCHESTRATOR]"),
    "add":          (GREEN,  "[+] ADD"),
    "subtract":     (GREEN,  "[-] SUBTRACT"),
    "multiply":     (GREEN,  "[x] MULTIPLY"),
    "divide":       (GREEN,  "[/] DIVIDE"),
}

DIVIDER     = "-" * 58
THICK_DIV   = "=" * 58


def print_header():
    print(f"\n{BOLD}{THICK_DIV}{RESET}")
    print(f"{BOLD}  [*] Arithmetic Orchestrator  |  Groq x LangGraph{RESET}")
    print(f"{BOLD}{THICK_DIV}{RESET}")
    print(f"{DIM}  Model : qwen/qwen3-32b{RESET}")
    print(f"{DIM}  Type 'quit' or 'exit' to stop.{RESET}\n")


def print_step(step_num: int, node_name: str, state_update: dict):
    """Pretty-print a single graph step."""
    colour, label = NODE_STYLE.get(node_name, (YELLOW, f"⚙  {node_name.upper()}"))
    print(f"\n{colour}{BOLD}{DIVIDER}{RESET}")
    print(f"{colour}{BOLD}  STEP {step_num} │ {label}{RESET}")
    print(f"{colour}{BOLD}{DIVIDER}{RESET}")

    if node_name == "orchestrator":
        # Show the LLM's JSON decision
        messages = state_update.get("messages", [])
        for msg in messages:
            if isinstance(msg, AIMessage):
                try:
                    parsed = parse_response(msg.content)
                    action = parsed.get("action", "?")
                    if action == "end":
                        print(f"  {BOLD}Decision :{RESET} Final answer ready")
                        print(f"  {BOLD}Answer   :{RESET} {parsed.get('answer', '')}")
                    else:
                        a = parsed.get("a", "?")
                        b = parsed.get("b", "?")
                        save = parsed.get("save_as", "?")
                        explanation = parsed.get("explanation", "")
                        print(f"  {BOLD}Decision    :{RESET} {action.upper()}({a}, {b})  →  save as '{save}'")
                        if explanation:
                            print(f"  {BOLD}Explanation :{RESET} {explanation}")
                except Exception:
                    print(f"  Raw: {msg.content[:200]}")

        # Show updated context if available
        if state_update.get("context"):
            print(f"  {DIM}Context  : {json.dumps(state_update['context'])}{RESET}")

    else:
        # Arithmetic node — show tool result message
        messages = state_update.get("messages", [])
        for msg in messages:
            print(f"  {BOLD}Result :{RESET} {msg.content}")

        ctx = state_update.get("context", {})
        if ctx:
            key, val = next(iter(ctx.items()))
            print(f"  {BOLD}Saved  :{RESET} {key} = {val}")


def run_query(graph, query: str):
    print(f"\n{BOLD}{THICK_DIV}{RESET}")
    print(f"{BOLD}  Query: {query}{RESET}")
    print(f"{BOLD}{THICK_DIV}{RESET}")
    print(f"{YELLOW}  >> Starting orchestration...{RESET}\n")

    initial_state = {
        "messages": [HumanMessage(content=query)],
        "context": {},
        "next_action": "",
        "action_input": {},
        "final_answer": "",
    }

    step_num = 0
    final_answer = ""

    for event in graph.stream(initial_state, stream_mode="updates"):
        for node_name, state_update in event.items():
            step_num += 1
            print_step(step_num, node_name, state_update)
            if state_update.get("final_answer"):
                final_answer = state_update["final_answer"]

    # Final answer banner
    print(f"\n{BOLD}{THICK_DIV}{RESET}")
    print(f"{BOLD}{GREEN}  [OK] FINAL ANSWER{RESET}")
    print(f"{BOLD}{THICK_DIV}{RESET}")
    print(f"  {final_answer}")
    print(f"{BOLD}{THICK_DIV}{RESET}\n")


def main():
    load_dotenv()

    # Set up OTel logging pipeline before anything else.
    # After this, all logger.info() calls in nodes.py are shipped to OpenObserve.
    setup_otel_logging()

    # Validate env vars
    if not os.environ.get("GROQ_API_KEY"):
        print(f"{RED}Error: GROQ_API_KEY not found in .env{RESET}")
        return

    graph = build_graph()
    print_header()

    while True:
        try:
            print(f"{BOLD}Your question:{RESET}")
            query = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        try:
            run_query(graph, query)
        except Exception as exc:
            print(f"\n{RED}Error during execution: {exc}{RESET}\n")


if __name__ == "__main__":
    main()
