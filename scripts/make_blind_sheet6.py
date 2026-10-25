"""Blind sheet for test set 6: do the tiny Kaggle small photos (60 x 80 px) help or hurt what a shopper sees?

For each of 60 fresh prompts the raw sentence is searched twice: with all four catalogues (what the site does now) and with Kaggle small switched off.
Prompts where both give the same four photos are not shown (nothing to rate; counted as ties in the summary). The rest are shown as two unlabelled,
shuffled options; photos appear at the same size for every source, so a tiny photo looks as blurry as it does on the site. Local only (seller photos).
Key (do NOT open before the ratings are pasted): data/preview/blind_key6.json.  Usage: .venv/bin/python scripts/make_blind_sheet6.py
"""
import base64
import html
import io
import json
import pathlib
import random
import sys

from PIL import Image

sys.path.insert(0, "src")
from genkart import embed  # noqa: E402
from genkart.catalogue import Catalogue  # noqa: E402
from genkart.catalogue import image_path as img_path  # noqa: E402

prompts = [l.strip() for l in open("data/human_prompts_test6.txt") if l.strip() and not l.startswith("#")]
assert len(prompts) == 60
cat = Catalogue.load()
no_tiny = Catalogue(cat.general, [s for s in cat.specialists if s.name != "kaggle"], shared_clusters=cat.shared_clusters)
model, _, tok, dev = embed.load("marqo-fashionsiglip")
vec = dict(zip(prompts, embed.encode_texts(model, tok, prompts, dev)))
K = 4
_th = {}


def thumb(pid):
    if pid not in _th:
        im = Image.open(img_path(pid)).convert("RGB")
        if max(im.size) > 480:
            im.thumbnail((480, 480))             # same cap as the site's photos; a 60 x 80 photo is NOT enlarged here, the page does that
        b = io.BytesIO()
        im.save(b, "JPEG", quality=80)
        _th[pid] = "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()
    return _th[pid]


rng = random.Random(6)
key, blocks, same, shown_tiny = {}, [], 0, 0
for n, text in enumerate(prompts, 1):
    ha = cat.search(vec[text], K, None)
    hb = no_tiny.search(vec[text], K, None)
    a, b = [h.product_id for h in ha], [h.product_id for h in hb]
    if a == b:
        same += 1
        continue
    shown_tiny += sum(h.source == "kaggle" for h in ha)
    opts = [("A_all", a), ("B_no_tiny", b)]
    rng.shuffle(opts)
    body = ""
    for k, (name, ids) in enumerate(opts, 1):
        key[f"p{n}-o{k}"] = [name]
        cards = '<div class="cards">' + "".join(f'<figure><img src="{thumb(pid)}" alt=""></figure>' for pid in ids) + "</div>"
        body += (f'<div class="opt"><div class="lab"><b>Option {k}</b><span class="rate" data-id="p{n}-o{k}"><button data-v="good">good</button>'
                 f'<button data-v="okay">okay</button><button data-v="bad">bad</button></span></div>{cards}</div>')
    blocks.append(f'<section><h2><span class="n">{n}</span> {html.escape(text)}</h2>{body}</section>')
json.dump(key, open("data/preview/blind_key6.json", "w"), indent=1)
page = open("data/preview/blind_sheet.html").read()
head = page[:page.index("<section>")]
tail = page[page.rindex("</section>") + len("</section>"):]
head = head.replace("Blind test: which result answers the request?", "Blind test 3: tiny photos").replace("genkart-blind-v1", "genkart-blind-v3")
tail = tail.replace("genkart-blind-v1", "genkart-blind-v3")
pathlib.Path("data/preview/blind_sheet6.html").write_text(head + "".join(blocks) + tail)
print(f"prompts 60 | identical (not shown) {same} | prompts shown {len(blocks)} | options {len(key)} | tiny photos among option A results: {shown_tiny}")
