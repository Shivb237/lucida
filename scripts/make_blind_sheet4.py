"""Blind sheet for test set 4 (50 Indian-occasion prompts; a fair test, nothing tuned on it).

Options per prompt (shuffled, unlabelled, no query text):
  A  raw sentence, Marqo only (the earlier baseline)
  B  raw sentence, all four catalogues (fallback routing)
  C  understood plan (prompt v2 + gender in every piece + knowledge graph), all four catalogues, one row per piece
Identical options are shown once; the key maps every shown option to the methods it stands for. Local only (seller photos).
Usage: .venv/bin/python scripts/make_blind_sheet4.py
"""
import base64
import html
import io
import json
import pathlib
import random
import sys

import pandas as pd
from PIL import Image

sys.path.insert(0, "src")
from genkart import embed  # noqa: E402
from genkart.catalogue import image_path as img_path  # noqa: E402
from genkart.catalogue import Catalogue  # noqa: E402
from genkart.graph import build_graph, expand_plan  # noqa: E402
from genkart.understand import make_chain, understand  # noqa: E402

prompts = [l.strip() for l in open("data/human_prompts_test4.txt") if l.strip() and not l.startswith("#")]
assert len(prompts) == 50
cat = Catalogue.load()
graph = build_graph(pd.read_csv("data/kaggle/styles.csv", on_bad_lines="skip"))



chain = make_chain()
model, _, tok, dev = embed.load("marqo-fashionsiglip")
plans, texts = [], set(prompts)
for n, text in enumerate(prompts, 1):
    plan, secs = understand(text, chain, version="v2")
    plan = expand_plan(graph, plan, text)
    plans.append({"n": n, "prompt": text, "plan": plan.model_dump(), "seconds": round(secs, 2)})
    texts.update(p.search_text for p in plan.pieces[:4])
with open("data/test4_plans.jsonl", "w") as f:
    for r in plans:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
order = sorted(texts)
vec = dict(zip(order, embed.encode_texts(model, tok, order, dev)))
K = 4
_th = {}


def thumb(pid):
    if pid not in _th:
        im = Image.open(img_path(pid)).convert("RGB")
        im.thumbnail((170, 220))
        b = io.BytesIO()
        im.save(b, "JPEG", quality=72)
        _th[pid] = "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()
    return _th[pid]


rng = random.Random(0)
key, blocks, stats = {}, [], {"A=B": 0, "B=C": 0, "sources_B": {}, "sources_C": {}}
for r in plans:
    n, text, plan = r["n"], r["prompt"], r["plan"]
    gender = plan["gender"] if plan["gender"] != "unknown" else None
    A = [[h.product_id for h in cat.general.search(vec[text], K, None)]]
    hb = cat.search(vec[text], K, None)
    B = [[h.product_id for h in hb]]
    rowsC = [cat.search(vec[p["search_text"]], K, gender) for p in plan["pieces"][:4]]
    C = [[h.product_id for h in row] for row in rowsC]
    for h in hb:
        stats["sources_B"][h.source] = stats["sources_B"].get(h.source, 0) + 1
    for row in rowsC:
        for h in row:
            stats["sources_C"][h.source] = stats["sources_C"].get(h.source, 0) + 1
    options = {"A": A, "B": B, "C": C}
    merged = []   # list of (methods, rows)
    for name, rows in options.items():
        for m in merged:
            if m[1] == rows:
                m[0].append(name)
                break
        else:
            merged.append(([name], rows))
    stats["A=B"] += int(options["A"] == options["B"])
    stats["B=C"] += int(options["B"] == options["C"])
    rng.shuffle(merged)
    body = ""
    for k, (methods, rows) in enumerate(merged, 1):
        key[f"p{n}-o{k}"] = methods
        cards = "".join('<div class="cards">' + "".join(f'<figure><img src="{thumb(pid)}" alt=""></figure>' for pid in row) + "</div>" for row in rows)
        body += (f'<div class="opt"><div class="lab"><b>Option {k}</b><span class="rate" data-id="p{n}-o{k}"><button data-v="good">good</button>'
                 f'<button data-v="okay">okay</button><button data-v="bad">bad</button></span></div>{cards}</div>')
    blocks.append(f'<section><h2><span class="n">{n}</span> {html.escape(text)}</h2>{body}</section>')
json.dump(key, open("data/preview/blind_key4.json", "w"), indent=1)
page = open("data/preview/blind_sheet.html").read()
head = page[:page.index("<section>")]
tail = page[page.rindex("</section>") + len("</section>"):]
head = head.replace("Blind test: which result answers the request?", "Blind test 2: Indian occasions").replace("genkart-blind-v1", "genkart-blind-v2")
tail = tail.replace("genkart-blind-v1", "genkart-blind-v2")
pathlib.Path("data/preview/blind_sheet4.html").write_text(head + "".join(blocks) + tail)
print(f"prompts 50 | options shown {len(key)} | A==B on {stats['A=B']} prompts | B==C on {stats['B=C']} prompts")
print("sources of option B photos:", stats["sources_B"], "| option C:", stats["sources_C"])
