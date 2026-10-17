"""Milestone 2, step 2: does 'draw the outfit, then match the drawing' beat direct text-to-product retrieval?

Same 20 queries, same 3,128 products, same labels and metrics as milestone 1. Methods:
  direct-text          query text vs product photo, Marqo-FashionSigLIP (reused from runs/marqo-fashionsiglip.jsonl)
  gen-resnet50         v1 style: generated image -> ResNet50 features -> cosine vs ResNet50 features of product photos
  gen-fashionsiglip    generated image -> Marqo-FashionSigLIP image encoder -> cosine vs product photo embeddings
  text+gen-fashionsiglip  direct-text similarity + gen-fashionsiglip similarity (unweighted sum)
Usage: .venv/bin/python scripts/run_m2.py   (needs scripts/gen_images.py to have run)
"""
import datetime
import json
import pathlib
import sys
import time

import numpy as np
import torch
import torchvision
from PIL import Image

sys.path.insert(0, "src")
from genkart import embed  # noqa: E402
from genkart.metrics import bootstrap_ci, ndcg_at_k, recall_at_k, reciprocal_rank  # noqa: E402
from genkart.retrieval import cosine_scores, rank  # noqa: E402

products = [json.loads(l) for l in open("data/sample/products.jsonl")]
queries = {q["query_id"]: q for q in map(json.loads, open("data/sample/queries.jsonl"))}
gen = [json.loads(l) for l in open("runs/gen_sd15.jsonl")]
ids = [p["product_id"] for p in products]
paths = [p["image"] for p in products]
EMB = pathlib.Path("data/embeddings")
device = embed.pick_device()
setup = {"n_queries": len(gen), "n_products": len(ids), "date": datetime.datetime.now().isoformat(timespec="seconds"),
         "generator": gen[0]["model"], "generator_revision": gen[0]["model_revision"], "device": device, "torch": torch.__version__,
         "torchvision": torchvision.__version__, "resnet_weights": "torchvision ResNet50 IMAGENET1K_V1, 2048-d avgpool, brute-force cosine"}

# --- ResNet50 features (v1 used ResNet50 + Annoy; here brute-force cosine, which Annoy only approximates)
weights = torchvision.models.ResNet50_Weights.IMAGENET1K_V1
resnet = torchvision.models.resnet50(weights=weights)
resnet.fc = torch.nn.Identity()
resnet = resnet.to(device).eval()
tf = weights.transforms()


@torch.no_grad()
def resnet_encode(files, batch=64):
    out = []
    for i in range(0, len(files), batch):
        x = torch.stack([tf(Image.open(p).convert("RGB")) for p in files[i : i + batch]]).to(device)
        f = resnet(x)
        out.append((f / f.norm(dim=-1, keepdim=True)).float().cpu().numpy())
    return np.concatenate(out)


f = EMB / "resnet50_images.npz"
if f.exists() and list(np.load(f)["ids"]) == ids:
    prod_rn = np.load(f)["vecs"]
else:
    t = time.time()
    prod_rn = resnet_encode(paths)
    np.savez(f, ids=np.array(ids), vecs=prod_rn)
    setup["resnet_product_embed_seconds"] = round(time.time() - t, 1)
gen_files = [g["image"] for g in gen]
gen_rn = resnet_encode(gen_files)

# --- Marqo-FashionSigLIP: product photo embeddings are cached from milestone 1; encode text and generated images
model, preprocess, tokenizer, _ = embed.load("marqo-fashionsiglip")
z = np.load(EMB / "marqo-fashionsiglip_images.npz")
assert list(z["ids"]) == ids
prod_sg = z["vecs"]
gen_sg = embed.encode_images(model, preprocess, gen_files, device)
txt_sg = embed.encode_texts(model, tokenizer, [g["query"] for g in gen], device)

scores = {
    "gen-resnet50": lambda i: cosine_scores(gen_rn[i], prod_rn),
    "gen-fashionsiglip": lambda i: cosine_scores(gen_sg[i], prod_sg),
    "text+gen-fashionsiglip": lambda i: cosine_scores(txt_sg[i], prod_sg) + cosine_scores(gen_sg[i], prod_sg),
}
METRICS = ("ndcg10", "recall10", "recall50", "mrr")
results = {}
for name, fn in scores.items():
    rows = []
    for i, g in enumerate(gen):
        q = queries[g["query_id"]]
        gains = {p["product_id"]: p["score_linear"] for p in q["products"]}
        relevant = {pid for pid, s in gains.items() if s >= 80}
        top = rank(fn(i), ids, 50)
        rows.append({"query_id": q["query_id"], "query": q["query"], "n_listed": len(gains), "n_relevant": len(relevant),
                     "ndcg10": ndcg_at_k([gains.get(pid, 0) for pid in top], list(gains.values()), 10),
                     "recall10": recall_at_k(top, relevant, 10), "recall50": recall_at_k(top, relevant, 50),
                     "mrr": reciprocal_rank(top, relevant), "top10": top[:10]})
    results[name] = rows
    with open(f"runs/m2-{name}.jsonl", "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")

# direct text baseline: the same 20 queries taken from the milestone 1 log (no re-run, identical numbers)
m1 = {r["query_id"]: r for r in map(json.loads, open("runs/marqo-fashionsiglip.jsonl"))}
results["direct-text"] = [m1[g["query_id"]] for g in gen]
with open("runs/m2-direct-text.jsonl", "w") as fh:
    for r in results["direct-text"]:
        fh.write(json.dumps(r) + "\n")

summary = {"setup": setup, "metrics": {}, "paired_vs_direct_text": {}}
print(f"{'method':26}" + "".join(f"{m:>24}" for m in METRICS))
for name, rows in results.items():
    summary["metrics"][name] = {}
    line = f"{name:26}"
    for m in METRICS:
        v = [r[m] for r in rows]
        lo, hi = bootstrap_ci(v)
        summary["metrics"][name][m] = {"mean": round(float(np.mean(v)), 4), "ci95": [round(lo, 4), round(hi, 4)]}
        line += f"{np.mean(v):>10.3f} [{lo:.3f}, {hi:.3f}]".rjust(24)
    print(line)
print("\npaired difference vs direct-text (method minus direct-text), 95% bootstrap CI over the 20 queries:")
base = {r["query_id"]: r for r in results["direct-text"]}
for name, rows in results.items():
    if name == "direct-text":
        continue
    summary["paired_vs_direct_text"][name] = {}
    for m in ("ndcg10", "recall50", "mrr"):
        d = [r[m] - base[r["query_id"]][m] for r in rows]
        lo, hi = bootstrap_ci(d)
        wins, ties, losses = sum(x > 1e-9 for x in d), sum(abs(x) <= 1e-9 for x in d), sum(x < -1e-9 for x in d)
        summary["paired_vs_direct_text"][name][m] = {"mean": round(float(np.mean(d)), 4), "ci95": [round(lo, 4), round(hi, 4)],
                                                     "better": wins, "tied": ties, "worse": losses}
        verdict = "clear" if lo > 0 or hi < 0 else "not clear (interval includes 0)"
        print(f"  {name:24} {m:9} {np.mean(d):+.3f} [{lo:+.3f}, {hi:+.3f}]  better {wins} / tied {ties} / worse {losses}  {verdict}")
json.dump(summary, open("runs/m2.summary.json", "w"), indent=2)
