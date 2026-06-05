from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages


def merge_dicts(left: dict, right: dict) -> dict:
    """Custom reducer: merges two dicts, right values take precedence."""
    return {**left, **right}


class AgentState(TypedDict):
    """
    Shared state passed between all nodes in the LangGraph.

    Attributes:
        messages:     Full conversation history (auto-merged by add_messages).
        context:      Named intermediate results, e.g. {"total_price": 1178.0}.
        next_action:  Routing signal set by the orchestrator:
                      "add" | "subtract" | "multiply" | "divide" | "end".
        action_input: Parameters for the current arithmetic operation.
        final_answer: Human-readable final answer, set when next_action == "end".
    """
    messages: Annotated[list, add_messages]
    context: Annotated[dict, merge_dicts]
    next_action: str
    action_input: dict
    final_answer: str
