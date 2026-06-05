import json
import re
import os
import logging

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from arithmetic_agent.state import AgentState
from arithmetic_agent.tools import add, subtract, multiply, divide
from arithmetic_agent.prompts import SYSTEM_PROMPT

# ── Logger setup ─────────────────────────────────────────────────────────────
# __name__ gives this logger the name "arithmetic_agent.nodes".
# When OTel auto-instrumentation is active, these calls are forwarded
# through the OTel pipeline → Collector → OpenObserve automatically.
logger = logging.getLogger(__name__)

# ── LLM setup ────────────────────────────────────────────────────────────────
_llm = None


def get_llm() -> ChatGroq:
    global _llm
    if _llm is None:
        _llm = ChatGroq(
            model="qwen/qwen3-32b",
            api_key=os.environ["GROQ_API_KEY"],
            temperature=0,
        )
    return _llm


# ── Response parser ───────────────────────────────────────────────────────────

def parse_response(content: str) -> dict:
    """
    Parse the LLM response into a dict.
    Handles:
      - <think>...</think> blocks (qwen3 reasoning tokens)
      - Markdown code fences
      - Multiple JSON blocks (picks the last valid one with an 'action' key)
    """
    # Strip thinking tokens emitted by qwen3
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    content = content.strip()

    # Strip markdown code fences if present — try parsing directly
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Walk through content collecting all top-level {...} objects
    # so we can pick the last one that contains "action"
    last_valid = None
    i = 0
    while i < len(content):
        if content[i] == "{":
            depth = 0
            for j in range(i, len(content)):
                if content[j] == "{":
                    depth += 1
                elif content[j] == "}":
                    depth -= 1
                    if depth == 0:
                        snippet = content[i: j + 1]
                        try:
                            candidate = json.loads(snippet)
                            if isinstance(candidate, dict) and "action" in candidate:
                                last_valid = candidate
                        except json.JSONDecodeError:
                            pass
                        i = j  # advance past this block
                        break
        i += 1

    if last_valid is not None:
        return last_valid

    raise ValueError(f"No valid JSON with 'action' key found in response:\n{content[:500]}")


# ── Resolve operand (number or context key) ───────────────────────────────────

def resolve(val, context: dict) -> float:
    """Return a float — either the literal value or a context lookup."""
    if isinstance(val, str):
        if val not in context:
            raise KeyError(f"Context key '{val}' not found. Available: {list(context.keys())}")
        return float(context[val])
    return float(val)


# ── Orchestrator node ─────────────────────────────────────────────────────────

def orchestrator_node(state: AgentState) -> dict:
    """
    Calls the Groq LLM with the current problem state.
    Parses the JSON response and sets next_action + action_input.
    """
    # Build a self-contained prompt for the LLM
    original_query = ""
    history_lines = []
    for msg in state["messages"]:
        if isinstance(msg, HumanMessage) and not original_query:
            original_query = msg.content
        elif isinstance(msg, AIMessage):
            history_lines.append(f"  Orchestrator: {msg.content}")
        else:
            history_lines.append(f"  Tool result: {msg.content}")

    context = state.get("context", {})
    context_str = json.dumps(context) if context else "{}"
    history_str = "\n".join(history_lines) if history_lines else "  (none)"

    user_prompt = (
        f"Problem: {original_query}\n\n"
        f"Steps done so far:\n{history_str}\n\n"
        f"Saved context: {context_str}\n\n"
        "What is the next step?"
    )

    logger.info("Orchestrator invoked", extra={"context_keys": list(context.keys())})

    response = get_llm().invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])

    try:
        parsed = parse_response(response.content)
    except ValueError as exc:
        logger.error("Failed to parse LLM response", extra={"error": str(exc)})
        raise

    next_action = parsed.get("action", "end")

    if next_action == "end":
        final_answer = parsed.get("answer", "")
        logger.info(
            "Orchestrator decision: END",
            extra={"action": "end", "final_answer": final_answer},
        )
        return {
            "messages": [AIMessage(content=response.content)],
            "next_action": "end",
            "final_answer": final_answer,
        }

    logger.info(
        f"Orchestrator decision: {next_action}",
        extra={
            "action": next_action,
            "action_input": parsed,
        },
    )
    return {
        "messages": [AIMessage(content=response.content)],
        "next_action": next_action,
        "action_input": parsed,
    }


# ── Generic arithmetic executor ───────────────────────────────────────────────

_TOOL_MAP = {
    "add": add,
    "subtract": subtract,
    "multiply": multiply,
    "divide": divide,
}
_SYMBOLS = {"add": "+", "subtract": "−", "multiply": "×", "divide": "÷"}


def _execute_arithmetic(state: AgentState, op: str) -> dict:
    """Run the arithmetic tool and update context."""
    ai = state["action_input"]
    context = state.get("context", {})

    a = resolve(ai["a"], context)
    b = resolve(ai["b"], context)

    try:
        result = _TOOL_MAP[op](a, b)
    except (ValueError, ZeroDivisionError) as exc:
        logger.error(
            f"Arithmetic error in {op}",
            extra={"operation": op, "a": a, "b": b, "error": str(exc)},
        )
        raise

    save_as = ai.get("save_as", f"{op}_result")

    logger.info(
        f"Tool executed: {op}({a}, {b}) = {result}",
        extra={
            "operation": op,
            "operand_a": a,
            "operand_b": b,
            "result": result,
            "saved_as": save_as,
        },
    )

    tool_msg = (
        f"{op}({a}, {b}) = {result}  ->  saved as '{save_as}'"
    )

    return {
        "messages": [HumanMessage(content=tool_msg)],
        "context": {save_as: result},
    }


# ── Four arithmetic nodes ─────────────────────────────────────────────────────

def add_node(state: AgentState) -> dict:
    """Execute addition and update context."""
    return _execute_arithmetic(state, "add")


def subtract_node(state: AgentState) -> dict:
    """Execute subtraction and update context."""
    return _execute_arithmetic(state, "subtract")


def multiply_node(state: AgentState) -> dict:
    """Execute multiplication and update context."""
    return _execute_arithmetic(state, "multiply")


def divide_node(state: AgentState) -> dict:
    """Execute division and update context."""
    return _execute_arithmetic(state, "divide")


# ── Conditional router ────────────────────────────────────────────────────────

def route_from_orchestrator(state: AgentState) -> str:
    """Return the next node name based on orchestrator's decision."""
    return state.get("next_action", "end")
