"""Milestone 4: write messy, realistic versions of real Marqo shopper searches with the local model (free).

For 200 searches (seed 0) from the scaled sample the model writes four rewrites, one per style. A rewrite must ask for the SAME kind
of item, so the dataset's product labels for the original search still apply and the messy version can be scored.
Limit to remember: the rewrites are written by a 4B language model, so they sound realistic but are not human-written.
Output: runs/messy_prompts.jsonl (one row per rewrite, with whether it copies the original wording).
Usage: .venv/bin/python scripts/make_messy_prompts.py [--n 200]
"""
import argparse
import datetime
import json
import random
import re
import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

STYLES = {
    "conversational": "Write it the way a real person would text a shop assistant: casual, 1-2 sentences, a bit chatty.",
    "typos_slang": "Write it the way someone types fast on a phone: all lowercase, text-speak, and one or two typos. One short line.",
    "hinglish": "Write it the way an Indian shopper might: mix a few Hindi words written in English letters (like chahiye, mujhe, kuch, accha, ke liye) with English. Keep the product words in English.",
    "with_reason": "Add a short real-life reason (who it is for or what event) and one vague preference (comfy, not too loud, good quality). Still ask for the SAME type of item and nothing else.",
}
SYSTEM = ("You rewrite a shop search into how a real shopper would actually type or say it. Rules: ask for exactly the same kind of "
          "item and KEEP EVERY detail the original search has (colour, material, fit, size, gender or age group, brand); never add a "
          "detail or item the original does not have; never add a budget; reply with the rewritten request only, on one line, no quotes, under 30 words.")
ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=200)
ap.add_argument("--seed", type=int, default=0)
args = ap.parse_args()

queries = [json.loads(l) for l in open("data/sample_scale/queries.jsonl")]
chosen = sorted(random.Random(args.seed).sample(queries, args.n), key=lambda q: q["query_id"])
llm = ChatOllama(model="qwen3:4b-instruct", temperature=0.7, seed=args.seed, num_ctx=2048, num_predict=80)  # num_predict stops runaway loops


def degenerate(text):
    """A runaway or broken rewrite: too long, or a character repeated many times (the model sometimes loops)."""
    return len(text.split()) > 40 or bool(re.search(r"(.)\1{5,}", text)) or not text.strip()


def words(s):
    return re.findall(r"[a-z0-9']+", s.lower())


start = time.time()
with open("runs/messy_prompts.jsonl", "w") as out:
    for n, q in enumerate(chosen, 1):
        for style, how in STYLES.items():
            msg = [SystemMessage(SYSTEM), HumanMessage(f'Search: "{q["query"]}"\nStyle: {how}')]
            attempts = 0
            while True:
                reply = llm.invoke(msg).content.strip().strip('"')
                text = reply.splitlines()[0].strip() if reply else ""
                attempts += 1
                if not degenerate(text) or attempts >= 3:
                    break
            orig = q["query"].lower()
            row = {"query_id": q["query_id"], "original": q["query"], "style": style, "messy": text,
                   "contains_original": orig in text.lower(), "degenerate": degenerate(text), "attempts": attempts,
                   "dropped_words": sorted(set(words(orig)) - set(words(text))),
                   "word_overlap": round(len(set(words(orig)) & set(words(text))) / max(1, len(set(words(orig)))), 2),
                   "model": "qwen3:4b-instruct", "temperature": 0.7, "seed": args.seed, "date": datetime.datetime.now().isoformat(timespec="seconds")}
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
        if n % 10 == 0:
            print(f"{n}/{len(chosen)} searches done, {time.time()-start:.0f}s", flush=True)
print("done")
