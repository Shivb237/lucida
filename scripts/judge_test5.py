"""LLM judge for blind-sheet options (test set 5; derived from judge_options.py). Claude sees the shopper's request and ONE picture per option (a row of 4 photos per search;
several rows = pieces of an outfit), never the method name, and answers good / okay / bad with the same wording the human raters had.
  --validate  rate the 141 options the user already rated, compare with the human ratings (agreement, kappa, confusion)
  --claude    build option D = Claude's plan (same graph expansion as C) and rate A, B, C, D with the judge (only after --validate looked usable)
Hard cap in code (claude_client). Writes runs/judge-validate.* or runs/judge-claude.*. Usage: .venv/bin/python scripts/judge_options.py --validate --cap 0.5"""
import argparse, base64, io, json, os, sys
from PIL import Image
sys.path.insert(0, "src")
from genkart import embed
from genkart.catalogue import image_path as img_path  # noqa: E402
from genkart.catalogue import Catalogue
from genkart.claude_client import CapExceeded, CappedClaude

ap = argparse.ArgumentParser()
ap.add_argument("--cap", type=float, default=0.5); ap.add_argument("--model", default="claude-sonnet-5-5"); ap.add_argument("--limit", type=int, default=0)
a = ap.parse_args()

prompts = [l.strip() for l in open("data/human_prompts_test5.txt") if l.strip() and not l.startswith("#")]
plans5 = {json.loads(l)["n"]: json.loads(l) for l in open("data/test5_plans.jsonl")}
key = json.load(open("data/preview/blind_key5.json")); human = json.load(open("data/human_ratings_test5.json"))
cat = Catalogue.load()

model, _, tok, dev = embed.load("marqo-fashionsiglip")
_vec = {}
def V(t):
    if t not in _vec: _vec[t] = embed.encode_texts(model, tok, [t], dev)[0]
    return _vec[t]
def rows_for(n, method):
    if method == "B": return [[h.product_id for h in cat.search(V(prompts[n - 1]), 4, None)]]
    plan = plans5[n]["qwen" if method == "C" else "claude"]
    g = plan["gender"] if plan["gender"] != "unknown" else None
    return [[h.product_id for h in cat.search(V(p["search_text"]), 4, g)] for p in plan["pieces"][:4]]

def collage(rows):
    W, H = 170, 220
    im = Image.new("RGB", (4 * W, len(rows) * H), "white")
    for r, row in enumerate(rows):
        for c, pid in enumerate(row):
            t = Image.open(img_path(pid)).convert("RGB"); t.thumbnail((W, H)); im.paste(t, (c * W, r * H))
    b = io.BytesIO(); im.save(b, "JPEG", quality=72); return base64.b64encode(b.getvalue()).decode()

SYSTEM = ("You rate how well a set of product photos answers a shopper's clothing request. Each picture is one option: every row of 4 photos is one search, "
          "and several rows are the pieces of an outfit. good = this set of photos answers what was asked; okay = partly; bad = not really. "
          "Judge the garments, colours and occasion in the photos against the request. Reply with ONLY one word and nothing else: good, okay or bad. Do not explain.")
judge = CappedClaude(a.model, a.cap, "runs/claude-spend.jsonl", "judge-test5")
def rate(n, rows):
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": collage(rows)}}, {"type": "text", "text": f"Request: {prompts[n-1]}"}]
    tool = {"name": "rate", "description": "Record the rating.", "input_schema": {"type": "object", "properties": {"rating": {"type": "string", "enum": ["good", "okay", "bad"]}}, "required": ["rating"]}}
    resp = judge.call(SYSTEM + " Record your answer by calling the rate tool.", content, max_tokens=400, est_input_tokens=2500, tools=[tool], tool_choice={"type": "auto"}, thinking={"type": "between_tools"})
    blk = next((b for b in resp.content if b.type == "tool_use"), None)
    if blk and blk.input.get("rating") in ("good", "okay", "bad"):
        return blk.input["rating"]
    return "unparsed:" + json.dumps({"stop": resp.stop_reason, "blocks": [(b.type, str(getattr(b, "text", None) or getattr(b, "input", None) or getattr(b, "thinking", ""))[:300]) for b in resp.content]})

out = "runs/judge-test5.jsonl"
done = {json.loads(l)["id"] for l in open(out)} if os.path.exists(out) else set()
items = [(k, int(k.split("-")[0][1:]), v[0], rows_for(int(k.split("-")[0][1:]), v[0])) for k, v in key.items()]
if a.limit: items = items[:a.limit]
for k, n, m, rows in items:
    if k in done: continue
    try: j = rate(n, rows)
    except CapExceeded as e: print("STOP:", e); break
    with open(out, "a") as f: f.write(json.dumps({"id": k, "n": n, "method": m, "judge": j, "human": human.get(k), "rows": rows}) + "\n")
print(f"calls {judge.calls}, spent this purpose ${judge.spent:.4f} (cap ${a.cap})")
