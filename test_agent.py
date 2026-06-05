"""Quick test script — runs the example query end-to-end."""
import os
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage
from arithmetic_agent.graph import build_graph
from arithmetic_agent.nodes import parse_response

load_dotenv()

graph = build_graph()

query = (
    "I bought two items priced at 349 and 829 and "
    "I get a 7% discount on the final price, "
    "what would be my final price to pay?"
)

initial_state = {
    "messages": [HumanMessage(content=query)],
    "context": {},
    "next_action": "",
    "action_input": {},
    "final_answer": "",
}

print("Query:", query)
print("=" * 60)

step = 0
final_answer = ""

for event in graph.stream(initial_state, stream_mode="updates"):
    for node_name, update in event.items():
        step += 1
        print(f"\nSTEP {step} | {node_name.upper()}")
        print("-" * 40)

        if node_name == "orchestrator":
            for m in update.get("messages", []):
                if isinstance(m, AIMessage):
                    try:
                        p = parse_response(m.content)
                        import json
                        print("  Decision:", json.dumps(p, indent=4))
                    except Exception as e:
                        print("  Parse error:", e)
                        print("  Raw:", m.content[:300])
        else:
            for m in update.get("messages", []):
                print("  Result:", m.content)
            ctx = update.get("context", {})
            if ctx:
                print("  Context:", ctx)

        fa = update.get("final_answer", "")
        if fa:
            final_answer = fa

print()
print("=" * 60)
print("FINAL ANSWER:", final_answer)
print("=" * 60)
