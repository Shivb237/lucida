"""Milestone 5: a BLIND photo sheet for test set 3 (the user's fresh prompts).

For each prompt up to three options are built, then shown in random order with no labels and no query text:
  raw         the prompt searched as typed (one row)
  plan        prompt v2 plan (understand.py, with the safety fixes): one row per piece
  plan+graph  the same plan after expand_plan (knowledge graph); omitted when the graph changed nothing
Every row shows 4 distinct products (duplicate clusters merged, tau 0.97; two no-garment images skipped).
The answer key goes to data/preview/blind_key.json and is not to be opened until the ratings are in.
Local only: the sheet embeds seller photos. Usage: .venv/bin/python scripts/make_blind_sheet.py
"""
import base64
import html
import io
import json
import pathlib
import random
import sys

import numpy as np
import pandas as pd
from PIL import Image

sys.path.insert(0, "src")
from genkart import embed  # noqa: E402
from genkart.dedup import Clusters  # noqa: E402
from genkart.graph import build_graph, expand_plan  # noqa: E402
from genkart.index import VectorIndex  # noqa: E402
from genkart.understand import make_chain, understand  # noqa: E402

ROWS_PER_OPTION_MAX = 4
SHOW = 4
prompts = [l.strip() for l in open("data/human_prompts_test3.txt") if l.strip() and not l.startswith("#")]
products = {int(p["product_id"]): p["title"] for p in map(json.loads, open("data/sample_scale/products.jsonl"))}
idx = VectorIndex.load("data/index/scale-marqo-fashionsiglip")
cm = json.load(open("data/clean/dup_clusters.json"))["cluster_of"]
clusters = Clusters(idx.ids, np.array([cm[str(pid)] for pid in idx.ids]))
skip = set(json.load(open("data/clean/manual_flags.json"))["no_garment_visible"])
graph = build_graph(pd.read_csv("data/kaggle/styles.csv", on_bad_lines="skip"))

chain = make_chain()
entries = []   # (prompt_no, option_name, [row query texts])
plans_log = []
for n, text in enumerate(prompts, 1):
    plan, secs = understand(text, chain, version="v2")
    before = [p.search_text for p in plan.pieces][:ROWS_PER_OPTION_MAX]
    plan_g = expand_plan(graph, plan.model_copy(deep=True), text)
    after = [p.search_text for p in plan_g.pieces][:ROWS_PER_OPTION_MAX]
    plans_log.append({"n": n, "prompt": text, "plan": plan.model_dump(), "plan_graph": plan_g.model_dump(), "seconds": round(secs, 2)})
    entries.append((n, "raw", [text]))
    entries.append((n, "plan", before))
    if after != before:
        entries.append((n, "plan_graph", after))
with open("data/test3_plans.jsonl", "w") as f:
    for r in plans_log:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

model, _, tok, dev = embed.load("marqo-fashionsiglip")
all_texts = sorted({t for _, _, rows in entries for t in rows})
vec = dict(zip(all_texts, embed.encode_texts(model, tok, all_texts, dev)))
_th = {}


def thumb(pid):
    if pid not in _th:
        im = Image.open(f"data/images/{pid}.jpg").convert("RGB")
        im.thumbnail((160, 160))
        b = io.BytesIO()
        im.save(b, "JPEG", quality=70)
        _th[pid] = "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()
    return _th[pid]


def top_distinct(text):
    ranked = [pid for pid, _ in idx.search(vec[text], 30) if pid not in skip]
    return clusters.collapse(ranked, SHOW)


rng = random.Random(0)
key, blocks = {}, []
for n, text in enumerate(prompts, 1):
    opts = [e for e in entries if e[0] == n]
    rng.shuffle(opts)
    body = ""
    for k, (_, name, rows) in enumerate(opts, 1):
        key[f"p{n}-o{k}"] = name
        cards = "".join(
            '<div class="cards">' + "".join(f'<figure><img src="{thumb(pid)}" alt=""></figure>' for pid in top_distinct(t)) + "</div>" for t in rows)
        body += (f'<div class="opt"><div class="lab"><b>Option {k}</b><span class="rate" data-id="p{n}-o{k}">'
                 f'<button data-v="good">good</button><button data-v="okay">okay</button><button data-v="bad">bad</button></span></div>{cards}</div>')
    blocks.append(f'<section><h2><span class="n">{n}</span> {html.escape(text)}</h2>{body}</section>')
pathlib.Path("data/preview").mkdir(parents=True, exist_ok=True)
json.dump(key, open("data/preview/blind_key.json", "w"), indent=1)

page = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Blind sheet (local)</title><style>
:root{--bg:#f4f6f8;--surface:#fff;--fg:#14202b;--muted:#56646f;--line:#d5dde3;--accent:#095a72;--good:#14603a;--okay:#82470a;--bad:#9b1c1c}
@media (prefers-color-scheme:dark){:root{--bg:#0f171d;--surface:#17222a;--fg:#e6edf1;--muted:#9bacb7;--line:#2a3a45;--accent:#56b6d1;--good:#5ccb8f;--okay:#f0b35a;--bad:#ff8a8a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;padding:16px}.wrap{max-width:900px;margin:0 auto}
h1{font-size:1.35rem;margin:0 0 4px}.note{color:var(--muted);margin:0 0 12px}section{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px;margin-bottom:14px}
h2{font-size:1.05rem;margin:0 0 8px}.n{display:inline-block;min-width:1.8em;color:var(--accent)}.opt{border-top:1px solid var(--line);padding:10px 0}
.lab{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}.rate button{font:inherit;font-size:.85rem;border:1px solid var(--line);background:var(--bg);color:var(--fg);border-radius:6px;padding:3px 10px;margin-left:4px;cursor:pointer}
.rate button.on[data-v=good]{background:var(--good);color:#fff;border-color:var(--good)}.rate button.on[data-v=okay]{background:var(--okay);color:#fff;border-color:var(--okay)}.rate button.on[data-v=bad]{background:var(--bad);color:#fff;border-color:var(--bad)}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:6px}figure{margin:0;min-width:0}img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:6px;background:var(--line);display:block}
.bar{position:sticky;top:0;background:var(--bg);padding:8px 0;display:flex;gap:10px;align-items:center;flex-wrap:wrap;z-index:2}
#copy{font:inherit;border:1px solid var(--accent);background:var(--accent);color:#fff;border-radius:6px;padding:5px 12px;cursor:pointer}#status{color:var(--muted);font-size:.9rem}
@media(max-width:560px){.cards{grid-template-columns:repeat(2,1fr)}}
</style></head><body><div class="wrap"><h1>Blind test: which result answers the request?</h1>
<p class="note">For each request, rate every option as a whole. good = this set of photos answers what you asked, okay = partly, bad = not really. Options are in random order and unlabelled. A row is one search; an option with several rows is a set of pieces.</p>
<div class="bar"><button id="copy">Copy my ratings</button><span id="status"></span></div>""" + "".join(blocks) + """</div><script>
(function(){var K='genkart-blind-v1',R={};try{R=JSON.parse(localStorage.getItem(K)||'{}')}catch(e){}
function paint(){document.querySelectorAll('.rate').forEach(function(g){var v=R[g.dataset.id];g.querySelectorAll('button').forEach(function(b){b.classList.toggle('on',b.dataset.v===v)})});
document.getElementById('status').textContent=Object.keys(R).length+' options rated of '+document.querySelectorAll('.rate').length}
document.querySelectorAll('.rate button').forEach(function(b){b.addEventListener('click',function(){var id=b.parentNode.dataset.id;if(R[id]===b.dataset.v){delete R[id]}else{R[id]=b.dataset.v}
try{localStorage.setItem(K,JSON.stringify(R))}catch(e){}paint()})});
document.getElementById('copy').addEventListener('click',function(){var t=Object.keys(R).sort(function(a,b){return a.localeCompare(b,undefined,{numeric:true})}).map(function(k){return k+': '+R[k]}).join('\\n');
var s=document.getElementById('status');function done(){s.textContent='copied '+Object.keys(R).length+' ratings; paste them in the chat'}
if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t).then(done,function(){s.textContent='copy blocked: '+t.replace(/\\n/g,' | ')})}else{s.textContent=t.replace(/\\n/g,' | ')}});
paint()})();
</script></body></html>"""
(pathlib.Path("data/preview") / "blind_sheet.html").write_text(page)
n_g = sum(1 for e in entries if e[1] == "plan_graph")
print(f"prompts {len(prompts)} | options {len(key)} | prompts where the graph changed the plan: {n_g} | photos {len(_th)}")
print("sheet: data/preview/blind_sheet.html | key: data/preview/blind_key.json (do not open until rated)")
