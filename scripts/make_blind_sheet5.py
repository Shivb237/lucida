"""Blind sheet for test set 5 (50 fresh prompts, written 2026-10-14, nothing tuned on them). Options per prompt, shuffled and unlabelled:
  B raw sentence, all four catalogues   C local Qwen3 plan (prompt v2 + gender + graph)   D Claude Sonnet 5.5 plan (same instructions, same checks, same graph)
Identical options are shown once. Key -> data/preview/blind_key5.json (do NOT open before the ratings are in). Paid: only the 50 Claude plan calls, capped.
Usage: .venv/bin/python scripts/make_blind_sheet5.py"""
import base64, html, io, json, pathlib, random, sys
import pandas as pd
from PIL import Image
sys.path.insert(0, "src")
from genkart import embed, guard
from genkart.catalogue import image_path as img_path  # noqa: E402
from genkart.catalogue import Catalogue
from genkart.claude_client import CapExceeded, CappedClaude
from genkart.graph import build_graph, expand_plan
from genkart.understand import SYSTEMS, Piece, Plan, ground, make_chain, qualify, understand

prompts = [l.strip() for l in open("data/human_prompts_test5.txt") if l.strip() and not l.startswith("#")]
assert len(prompts) == 50
# 1. safety guard on every prompt (real use of src/genkart/guard.py)
reviewer = guard.make_reviewer()
verdicts = [guard.check(t, reviewer) for t in prompts]
refused = [(i + 1, t, v.category) for i, (t, v) in enumerate(zip(prompts, verdicts)) if not v.allowed]
print("guard refused:", refused)

cat = Catalogue.load(); graph = build_graph(pd.read_csv("data/kaggle/styles.csv", on_bad_lines="skip"))

# 2. plans: local Qwen3 and Claude
chain = make_chain()
claude = CappedClaude("claude-sonnet-5-5", 0.50, "runs/claude-spend.jsonl", "plan-comparison-test5")
tool = {"name": "answer", "description": "Return the product search plan.", "input_schema": Plan.model_json_schema()}
plans = []
for n, text in enumerate(prompts, 1):
    q, secs = understand(text, chain, version="v2"); q = expand_plan(graph, q, text)
    c_ok = True
    try:
        resp = claude.call(SYSTEMS["v2"] + "\nAnswer by calling the answer tool.", f"Request: {text}", max_tokens=600, tools=[tool], tool_choice={"type": "auto"})
        blk = next(b for b in resp.content if b.type == "tool_use")
        c = qualify(ground(Plan.model_validate(blk.input), text), text)
        if not c.pieces: c.pieces = [Piece(kind="other", search_text=c.main_query or text)]
        c = expand_plan(graph, c, text)
    except CapExceeded as e:
        raise SystemExit(f"STOP: {e}") from e
    except Exception:
        c_ok = False; c = Plan(main_query=text, gender="unknown", pieces=[Piece(kind="other", search_text=text)])
    plans.append({"n": n, "prompt": text, "qwen": q.model_dump(), "claude": c.model_dump(), "claude_ok": c_ok, "qwen_seconds": round(secs, 2)})
    print(n, "qwen/claude plans done", flush=True)
with open("data/test5_plans.jsonl", "w") as f:
    for r in plans: f.write(json.dumps(r, ensure_ascii=False) + "\n")

# 3. options
model, _, tok, dev = embed.load("marqo-fashionsiglip")
texts = set(prompts)
for r in plans: texts.update(p["search_text"] for k in ("qwen", "claude") for p in r[k]["pieces"][:4])
order = sorted(texts); vec = dict(zip(order, embed.encode_texts(model, tok, order, dev)))
_th = {}
def thumb(pid):
    if pid not in _th:
        im = Image.open(img_path(pid)).convert("RGB"); im.thumbnail((170, 220))
        b = io.BytesIO(); im.save(b, "JPEG", quality=72); _th[pid] = "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()
    return _th[pid]
def rows_of(plan, K=4):
    g = plan["gender"] if plan["gender"] != "unknown" else None
    return [[h.product_id for h in cat.search(vec[p["search_text"]], K, g)] for p in plan["pieces"][:4]]

rng = random.Random(5); key, blocks, same = {}, [], {"B=C": 0, "B=D": 0, "C=D": 0}
for r in plans:
    n = r["n"]
    opts = {"B": [[h.product_id for h in cat.search(vec[r["prompt"]], 4, None)]], "C": rows_of(r["qwen"]), "D": rows_of(r["claude"])}
    same["B=C"] += opts["B"] == opts["C"]; same["B=D"] += opts["B"] == opts["D"]; same["C=D"] += opts["C"] == opts["D"]
    merged = []
    for name, rows in opts.items():
        for m in merged:
            if m[1] == rows: m[0].append(name); break
        else: merged.append(([name], rows))
    rng.shuffle(merged); body = ""
    for k, (methods, rows) in enumerate(merged, 1):
        key[f"p{n}-o{k}"] = methods
        cards = "".join('<div class="cards">' + "".join(f'<figure><img src="{thumb(pid)}" alt=""></figure>' for pid in row) + "</div>" for row in rows)
        body += (f'<div class="opt"><div class="lab"><b>Option {k}</b><span class="rate" data-id="p{n}-o{k}"><button data-v="good">good</button>'
                 f'<button data-v="okay">okay</button><button data-v="bad">bad</button></span></div>{cards}</div>')
    blocks.append(f'<section><h2><span class="n">{n}</span> {html.escape(r["prompt"])}</h2>{body}</section>')
json.dump(key, open("data/preview/blind_key5.json", "w"), indent=1)
page = open("data/preview/blind_sheet.html").read()
head = page[:page.index("<section>")]; tail = page[page.rindex("</section>") + len("</section>"):]
head = head.replace("Blind test: which result answers the request?", "Blind test 3: 50 fresh prompts").replace("genkart-blind-v1", "genkart-blind-v3")
tail = tail.replace("genkart-blind-v1", "genkart-blind-v3")
pathlib.Path("data/preview/blind_sheet5.html").write_text(head + "".join(blocks) + tail)
json.dump({"prompts": 50, "options_shown": len(key), "identical_option_pairs": same, "guard_refused": [[a, c] for a, _, c in refused], "claude_plans_failed": sum(not r["claude_ok"] for r in plans),
           "claude_cost_usd_this_purpose": round(claude.spent, 4), "photos": len(_th)}, open("runs/test5-build.summary.json", "w"), indent=2)
print(f"options shown {len(key)} | identical pairs {same} | claude cost ${claude.spent:.4f} | photos {len(_th)}")
