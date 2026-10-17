"""Milestone 2, step 1: draw one image per query with local Stable Diffusion 1.5 (free, on the Apple GPU).

Picks 20 of the 64 pilot queries with a fixed seed, builds a fixed prompt (no LLM rewrite: v1's GPT-3.5 step is a paid call
and is not part of this test), generates one image per query with a per-query seed, and logs every image to runs/gen_sd15.jsonl.
Usage: .venv/bin/python scripts/gen_images.py [--n 20] [--steps 20]
"""
import argparse
import datetime
import json
import pathlib
import random
import time

import torch
from diffusers import StableDiffusionPipeline, DPMSolverMultistepScheduler
from huggingface_hub import HfApi

REPO = "stable-diffusion-v1-5/stable-diffusion-v1-5"
PROMPT = "a product photo of {q}, single item, centered, plain white background, studio lighting"
NEGATIVE = "person, model, mannequin, text, watermark, multiple items, collage"

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=20)
ap.add_argument("--steps", type=int, default=20)
ap.add_argument("--seed", type=int, default=0)
args = ap.parse_args()

queries = [json.loads(l) for l in open("data/sample/queries.jsonl")]
chosen = sorted(random.Random(args.seed).sample(queries, args.n), key=lambda q: q["query_id"])
pathlib.Path("runs").mkdir(exist_ok=True)
json.dump([{"query_id": q["query_id"], "query": q["query"]} for q in chosen], open("runs/m2_queries.json", "w"), indent=2)

out = pathlib.Path("data/generated")
out.mkdir(parents=True, exist_ok=True)
sha = HfApi().model_info(REPO).sha
device = "mps" if torch.backends.mps.is_available() else "cpu"
pipe = StableDiffusionPipeline.from_pretrained(REPO, torch_dtype=torch.float16, variant="fp16", safety_checker=None,
                                               requires_safety_checker=False)
pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
pipe = pipe.to(device)
pipe.set_progress_bar_config(disable=True)

with open("runs/gen_sd15.jsonl", "w") as log:
    for q in chosen:
        prompt = PROMPT.format(q=q["query"])
        t = time.time()
        gen = torch.Generator("cpu").manual_seed(args.seed + q["query_id"] % 100000)
        img = pipe(prompt, negative_prompt=NEGATIVE, num_inference_steps=args.steps, guidance_scale=7.5,
                   height=512, width=512, generator=gen).images[0]
        secs = time.time() - t
        path = out / f"{q['query_id']}.png"
        img.save(path)
        log.write(json.dumps({"query_id": q["query_id"], "query": q["query"], "prompt": prompt, "image": str(path),
                              "seconds": round(secs, 2), "model": REPO, "model_revision": sha, "steps": args.steps,
                              "device": device, "torch": torch.__version__, "date": datetime.datetime.now().isoformat(timespec="seconds")}) + "\n")
        log.flush()
        print(f"{q['query']!r}: {secs:.1f}s", flush=True)
