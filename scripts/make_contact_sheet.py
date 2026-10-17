"""Milestone 5, step 1: a photo contact sheet of what the search really returns for each plan piece, for human judging.

For every held-out prompt: one row for the raw prompt searched as typed, and one row per plan piece (prompt v2, after the safety
fixes). Each row shows the top 4 products from the saved index (Marqo-FashionSigLIP) with their photos and titles, plus good / okay /
bad buttons whose answers are kept in this browser and can be copied as text.
Output: data/preview/heldout_sheet.html (LOCAL ONLY: it shows seller photos from data/images, never publish or commit it).
Usage: .venv/bin/python scripts/make_contact_sheet.py
"""
import base64
import html
import io
import json
import pathlib
import sys

sys.path.insert(0, "src")
from PIL import Image  # noqa: E402

from genkart import embed  # noqa: E402
from genkart.index import VectorIndex  # noqa: E402

TOP = 4
plans = json.load(open("data/heldout_rows.v2-postfix.json"))
products = {int(p["product_id"]): p["title"] for p in map(json.loads, open("data/sample_scale/products.jsonl"))}
index = VectorIndex.load("data/index/scale-marqo-fashionsiglip")
model, _, tok, dev = embed.load("marqo-fashionsiglip")

texts, owners = [], []
for r in plans:
    texts.append(r["prompt"])
    owners.append((r["n"], "raw", r["prompt"]))
    for i, p in enumerate(r["plan"]["pieces"]):
        texts.append(p["search_text"])
        owners.append((r["n"], f"piece{i}", p["search_text"]))
vecs = embed.encode_texts(model, tok, texts, dev)
hits = {(n, key): [(pid, s) for pid, s in index.search(v, TOP)] for (n, key, _), v in zip(owners, vecs)}


_thumbs = {}


def thumb(pid):
    """Small embedded JPEG so the sheet is one self-contained file (the browser pane cannot follow image paths)."""
    if pid not in _thumbs:
        im = Image.open(f"data/images/{pid}.jpg").convert("RGB")
        im.thumbnail((240, 240))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=78)
        _thumbs[pid] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    return _thumbs[pid]


def card(pid, score):
    t = html.escape(products[pid])
    return (f'<figure><img loading="lazy" src="{thumb(pid)}" alt=""><figcaption>{t[:70]}'
            f'<span class="s">{score:.3f}</span></figcaption></figure>')


def row(n, key, label, query):
    cards = "".join(card(pid, s) for pid, s in hits[(n, key)])
    rid = f"{n}-{key}"
    return (f'<div class="row" id="r{rid}"><div class="lab"><b>{html.escape(label)}</b><span class="q">{html.escape(query)}</span>'
            f'<span class="rate" data-id="{rid}"><button data-v="good">good</button><button data-v="okay">okay</button>'
            f'<button data-v="bad">bad</button></span></div><div class="cards">{cards}</div></div>')


blocks = []
for r in plans:
    pl = r["plan"]
    meta = " · ".join(x for x in [f"gender {pl['gender']}", f"occasion {pl['occasion']}" if pl["occasion"] else "",
                                  f"season {pl['season']}" if pl["season"] else "",
                                  f"budget ₹{int(pl['budget_inr'])}" if pl["budget_inr"] else "",
                                  ("already has: " + ", ".join(pl["already_has"])) if pl["already_has"] else ""] if x)
    rows = row(r["n"], "raw", "Raw prompt searched as typed", r["prompt"])
    for i, p in enumerate(pl["pieces"]):
        rows += row(r["n"], f"piece{i}", f"Plan piece {i+1}: {p['kind']}", p["search_text"])
    blocks.append(f'<section><h2><span class="n">{r["n"]}</span> {html.escape(r["prompt"])}</h2><p class="meta">{html.escape(meta)}</p>{rows}</section>')

page = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Held-out contact sheet (local)</title><style>
:root{--bg:#f4f6f8;--surface:#fff;--fg:#14202b;--muted:#56646f;--line:#d5dde3;--accent:#095a72;--good:#14603a;--okay:#82470a;--bad:#9b1c1c}
@media (prefers-color-scheme:dark){:root{--bg:#0f171d;--surface:#17222a;--fg:#e6edf1;--muted:#9bacb7;--line:#2a3a45;--accent:#56b6d1;--good:#5ccb8f;--okay:#f0b35a;--bad:#ff8a8a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;padding:16px}
.wrap{max-width:1000px;margin:0 auto}h1{font-size:1.4rem;margin:0 0 4px}.note{color:var(--muted);margin:0 0 16px}
section{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px;margin-bottom:14px}
h2{font-size:1.05rem;margin:0 0 2px}.n{display:inline-block;min-width:1.8em;color:var(--accent)}.meta{color:var(--muted);margin:0 0 10px;font-size:.9rem}
.row{border-top:1px solid var(--line);padding:10px 0}.lab{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center;margin-bottom:8px}
.q{color:var(--muted);font-size:.9rem;flex:1 1 200px;min-width:0}.rate button{font:inherit;font-size:.85rem;border:1px solid var(--line);background:var(--bg);color:var(--fg);border-radius:6px;padding:3px 10px;margin-left:4px;cursor:pointer}
.rate button.on[data-v=good]{background:var(--good);color:#fff;border-color:var(--good)}.rate button.on[data-v=okay]{background:var(--okay);color:#fff;border-color:var(--okay)}.rate button.on[data-v=bad]{background:var(--bad);color:#fff;border-color:var(--bad)}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}figure{margin:0;min-width:0}img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:6px;background:var(--line);display:block}
figcaption{font-size:.78rem;color:var(--muted);margin-top:3px;overflow-wrap:anywhere}.s{display:block;font-variant-numeric:tabular-nums}
.bar{position:sticky;top:0;background:var(--bg);padding:8px 0;display:flex;gap:10px;align-items:center;flex-wrap:wrap;z-index:2}
#copy{font:inherit;border:1px solid var(--accent);background:var(--accent);color:#fff;border-radius:6px;padding:5px 12px;cursor:pointer}#status{color:var(--muted);font-size:.9rem}
@media(max-width:560px){.cards{grid-template-columns:repeat(2,1fr)}}
</style></head><body><div class="wrap"><h1>What the search returns, for your 30 held-out prompts</h1>
<p class="note">Rows with "Raw prompt" search the sentence exactly as you typed it. "Plan piece" rows search what the understanding step extracted. Rate each row: good = the 4 photos are what you meant, okay = partly, bad = not what you meant. The grey number is the match score.</p>
<div class="bar"><button id="copy">Copy my ratings</button><span id="status"></span></div>""" + "".join(blocks) + """</div><script>
(function(){var K='genkart-sheet-ratings-v1',R={};try{R=JSON.parse(localStorage.getItem(K)||'{}')}catch(e){}
function paint(){document.querySelectorAll('.rate').forEach(function(g){var v=R[g.dataset.id];g.querySelectorAll('button').forEach(function(b){b.classList.toggle('on',b.dataset.v===v)})});
document.getElementById('status').textContent=Object.keys(R).length+' rows rated of '+document.querySelectorAll('.rate').length}
document.querySelectorAll('.rate button').forEach(function(b){b.addEventListener('click',function(){var id=b.parentNode.dataset.id;if(R[id]===b.dataset.v){delete R[id]}else{R[id]=b.dataset.v}
try{localStorage.setItem(K,JSON.stringify(R))}catch(e){}paint()})});
document.getElementById('copy').addEventListener('click',function(){var t=Object.keys(R).sort(function(a,b){return a.localeCompare(b,undefined,{numeric:true})}).map(function(k){return k+': '+R[k]}).join('\\n');
var s=document.getElementById('status');function done(){s.textContent='copied '+Object.keys(R).length+' ratings; paste them in the chat'}
if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t).then(done,function(){s.textContent='copy blocked; ratings: '+t.replace(/\\n/g,' | ')})}else{s.textContent=t.replace(/\\n/g,' | ')}});
paint()})();
</script></body></html>"""
out = pathlib.Path("data/preview")
out.mkdir(parents=True, exist_ok=True)
(out / "heldout_sheet.html").write_text(page)
missing = [pid for hs in hits.values() for pid, _ in hs if not pathlib.Path(f"data/images/{pid}.jpg").exists()]
print(f"wrote data/preview/heldout_sheet.html: {len(plans)} prompts, {len(owners)} rows, {len(owners)*TOP} photos, missing photos: {len(missing)}")
