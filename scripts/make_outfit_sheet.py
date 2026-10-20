"""Blind sheet for outfit coherence: does choosing pieces jointly (colour harmony) beat taking each piece's best match on its own?

Prompts: multi-piece plans from the user's test sets 3 and 4 (plans regenerated with the current code), 30 drawn at random (seed 0).
Per prompt up to three outfit boards, shuffled and unlabelled, one photo per piece:
  baseline  best match for each piece, independently (no product used twice)
  coherent  best joint score of relevance and colour harmony (src/genkart/outfit.py; weights fixed in advance)
  clash     worst-harmony combination from the top 6 of each piece: a sanity check that harmony is visible to a person
Identical boards are shown once. Objective numbers (harmony, relevance loss) go to the key file. Local only (seller photos).
Usage: .venv/bin/python scripts/make_outfit_sheet.py
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
from genkart.catalogue import Catalogue, image_path  # noqa: E402
from genkart.colour import dominant_colour  # noqa: E402
from genkart.graph import build_graph, expand_plan  # noqa: E402
from genkart.outfit import build_outfits  # noqa: E402
from genkart.understand import make_chain, understand  # noqa: E402

rd = lambda f: [l.strip() for l in open(f) if l.strip() and not l.startswith("#")]  # noqa: E731
pool = sorted(set(rd("data/human_prompts_test3.txt") + rd("data/human_prompts_test4.txt")))
cat = Catalogue.load()
graph = build_graph(pd.read_csv("data/kaggle/styles.csv", on_bad_lines="skip"))
chain = make_chain()
model, _, tok, dev = embed.load("marqo-fashionsiglip")

multi = []
for text in pool:
    plan, _ = understand(text, chain, version="v2")
    plan = expand_plan(graph, plan, text)
    if len(plan.pieces) >= 2:
        multi.append((text, plan))
print(f"{len(pool)} prompts in test sets 3 and 4; {len(multi)} give a multi-piece plan")
chosen = random.Random(0).sample(multi, min(30, len(multi)))
_col = {}


def colours_of_factory(kind_of):
    def f(h):
        key = (h.product_id, kind_of[h.product_id])
        if key not in _col:
            _col[key] = dominant_colour(image_path(h.product_id), kind_of[h.product_id])
        return _col[key]
    return f


_th = {}


def thumb(pid):
    if pid not in _th:
        im = Image.open(image_path(pid)).convert("RGB")
        im.thumbnail((200, 260))
        b = io.BytesIO()
        im.save(b, "JPEG", quality=74)
        _th[pid] = "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()
    return _th[pid]


rng = random.Random(1)
key, blocks, summary = {}, [], {"n_prompts": 0, "coherent_equals_baseline": 0, "harmony": {"baseline": [], "coherent": [], "clash": []},
                                "relevance_loss": {"baseline": [], "coherent": [], "clash": []}}
texts = sorted({p.search_text for _, pl in chosen for p in pl.pieces[:3]})
vec = dict(zip(texts, embed.encode_texts(model, tok, texts, dev)))
for n, (text, plan) in enumerate(chosen, 1):
    gender = plan.gender if plan.gender != "unknown" else None
    pieces = plan.pieces[:3]
    cands, kind_of = [], {}
    for p in pieces:
        hits = cat.search(vec[p.search_text], 10, gender)
        cands.append(hits)
        for h in hits:
            kind_of[h.product_id] = p.kind
    outs = build_outfits(cands, colours_of_factory(kind_of))
    if not outs:
        continue
    summary["n_prompts"] += 1
    summary["coherent_equals_baseline"] += int([h.product_id for h in outs["coherent"].hits] == [h.product_id for h in outs["baseline"].hits])
    shown = []
    for name in ("baseline", "coherent", "clash"):
        ids = [h.product_id for h in outs[name].hits]
        summary["harmony"][name].append(outs[name].harmony)
        summary["relevance_loss"][name].append(outs[name].relevance_loss)
        for s in shown:
            if s["ids"] == ids:
                s["methods"].append(name)
                break
        else:
            shown.append({"ids": ids, "methods": [name], "harmony": outs[name].harmony, "loss": outs[name].relevance_loss,
                          "colours": [c.name if c else None for c in outs[name].colours]})
    rng.shuffle(shown)
    body = ""
    for k, s in enumerate(shown, 1):
        key[f"p{n}-o{k}"] = {"methods": s["methods"], "harmony": round(s["harmony"], 3), "relevance_loss": round(s["loss"], 2), "colours": s["colours"], "ids": s["ids"]}
        board = '<div class="board">' + "".join(f'<figure><img src="{thumb(pid)}" alt=""></figure>' for pid in s["ids"]) + "</div>"
        body += (f'<div class="opt"><div class="lab"><b>Outfit {k}</b><span class="rate" data-id="p{n}-o{k}"><button data-v="good">good</button>'
                 f'<button data-v="okay">okay</button><button data-v="bad">bad</button></span></div>{board}</div>')
    blocks.append(f'<section><h2><span class="n">{n}</span> {html.escape(text)}</h2>{body}</section>')
json.dump(key, open("data/preview/outfit_key.json", "w"), indent=1)
page = open("data/preview/blind_sheet4.html").read()
head = page[:page.index("<section>")]
tail = page[page.rindex("</section>") + len("</section>"):]
head = (head.replace("Blind test 2: Indian occasions", "Blind test 3: complete outfits")
       .replace("</style>", ".board{display:flex;gap:6px;flex-wrap:wrap}.board figure{flex:1 1 0;min-width:90px;max-width:220px}</style>")
       .replace("For each request, rate every option as a whole.", "Each outfit is one photo per piece. Rate the whole outfit: do the pieces go well together and fit the request?"))
# Own localStorage key so these ratings do not mix with make_blind_sheet5.py's genkart-blind-v3 (the key is in tail, the script after the last section).
assert "genkart-blind-v2" in tail, "blind_sheet4.html no longer has the key this script replaces"
tail = tail.replace("genkart-blind-v2", "genkart-blind-outfit-v1")
pathlib.Path("data/preview/outfit_sheet.html").write_text(head + "".join(blocks) + tail)
S = summary
print(f"prompts used {S['n_prompts']} | coherent outfit differs from baseline on {S['n_prompts']-S['coherent_equals_baseline']} of them")
for m in ("baseline", "coherent", "clash"):
    print(f"  {m:9} mean harmony {np.mean(S['harmony'][m]):.3f} | mean relevance loss {np.mean(S['relevance_loss'][m]):.2f} (units of one sd of a best-match score)")
print("boards shown:", len(key))
json.dump({k: (v if not isinstance(v, dict) else {a: round(float(np.mean(b)), 4) for a, b in v.items()}) for k, v in S.items()}, open("runs/outfit-objective.summary.json", "w"), indent=2)
