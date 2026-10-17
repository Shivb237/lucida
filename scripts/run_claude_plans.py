"""Compare Claude with the local Qwen3 on the same job: turn a shopper request into a Plan (src/genkart/understand.py).
Same system prompt (v2), same schema, same code checks afterwards (ground + qualify). Claude is forced to answer through a tool whose
input schema is the Plan. Hard cap in code (src/genkart/claude_client.py). Usage:
  .venv/bin/python scripts/run_claude_plans.py --limit 3        (try 3 first)
  .venv/bin/python scripts/run_claude_plans.py                  (all 50 of test set 4)
Writes runs/claude-plans.jsonl (+ ledger runs/claude-spend.jsonl)."""
import argparse, json, sys
sys.path.insert(0, "src")
from genkart.claude_client import CapExceeded, CappedClaude
from genkart.understand import SYSTEMS, Plan, Piece, ground, qualify

ap = argparse.ArgumentParser()
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--cap", type=float, default=0.50)
ap.add_argument("--model", default="claude-sonnet-5-5")
ap.add_argument("--out", default="runs/claude-plans.jsonl")
a = ap.parse_args()

prompts = [json.loads(l) for l in open("data/test4_plans.jsonl")]
if a.limit:
    prompts = prompts[:a.limit]
done = {json.loads(l)["n"] for l in open(a.out)} if __import__("os").path.exists(a.out) else set()
cl = CappedClaude(a.model, a.cap, "runs/claude-spend.jsonl", "plan-comparison-test4")
tool = {"name": "answer", "description": "Return the product search plan.", "input_schema": Plan.model_json_schema()}
for r in prompts:
    if r["n"] in done:
        continue
    try:
        resp = cl.call(SYSTEMS["v2"] + "\nAnswer by calling the answer tool.", f"Request: {r['prompt']}", max_tokens=600, tools=[tool], tool_choice={"type": "auto"})
    except CapExceeded as e:
        print("STOP:", e); break
    block = next((b for b in resp.content if b.type == "tool_use"), None)
    try:
        plan = qualify(ground(Plan.model_validate(block.input), r["prompt"]), r["prompt"])
        if not plan.pieces:
            plan.pieces = [Piece(kind="other", search_text=plan.main_query or r["prompt"])]
        ok = True
    except Exception:
        plan, ok = None, False
    with open(a.out, "a") as f:
        f.write(json.dumps({"n": r["n"], "prompt": r["prompt"], "ok": ok, "plan": plan.model_dump() if plan else None,
                            "in_tokens": resp.usage.input_tokens, "out_tokens": resp.usage.output_tokens}, ensure_ascii=False) + "\n")
    print(r["n"], "ok" if ok else "BAD", "|", (plan.main_query if plan else "-")[:70], "| spent so far $%.4f" % cl.spent)
print(f"calls {cl.calls}, spent ${cl.spent:.4f} of cap ${a.cap:.2f}")
