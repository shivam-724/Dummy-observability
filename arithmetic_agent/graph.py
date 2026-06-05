from langgraph.graph import StateGraph, END

from arithmetic_agent.state import AgentState
from arithmetic_agent.nodes import (
    orchestrator_node,
    add_node,
    subtract_node,
    multiply_node,
    divide_node,
    route_from_orchestrator,
)


def build_graph() -> StateGraph:
    """
    Construct and compile the arithmetic orchestrator graph.

    Graph topology:
        START
          └─► orchestrator_node
                ├─(add)──────► add_node ──────┐
                ├─(subtract)─► subtract_node ──┤
                ├─(multiply)─► multiply_node ──┼──► orchestrator_node (loop)
                ├─(divide)───► divide_node ────┘
                └─(end)──────► END
    """
    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("add", add_node)
    graph.add_node("subtract", subtract_node)
    graph.add_node("multiply", multiply_node)
    graph.add_node("divide", divide_node)

    # Entry point
    graph.set_entry_point("orchestrator")

    # Conditional edges from orchestrator → arithmetic nodes or END
    graph.add_conditional_edges(
        "orchestrator",
        route_from_orchestrator,
        {
            "add": "add",
            "subtract": "subtract",
            "multiply": "multiply",
            "divide": "divide",
            "end": END,
        },
    )

    # All arithmetic nodes loop back to the orchestrator
    for node in ("add", "subtract", "multiply", "divide"):
        graph.add_edge(node, "orchestrator")

    return graph.compile()
