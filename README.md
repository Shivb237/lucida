# Lucida

Fashion search that understands what you ask for, built on a measured foundation. (Formerly called GenKart v2; the Python package and some settings keep the name `genkart`.)

GenKart v1 (Flipkart GRiD 5.0, Level 2, 2023) turned a request into an AI-generated outfit picture and then found real catalogue products that looked like it. It had no real evaluation. Lucida starts by measuring: how well can a text query find the right products, and does the generated-image step help at all? Context (season, occasion, profile) and a user study come next.

## What this project found (every number is from a logged run in `runs/`)

- **Drawing the outfit first hurt.** The v1 idea (generate a picture, then match it) scored NDCG@10 0.214 against 0.549 for searching the text directly (20 queries, local Stable Diffusion 1.5).
- **More catalogues helped most.** On 50 fresh Indian-occasion prompts rated blind by a person (0-2), searching four catalogues beat one by +1.00 [+0.74, +1.26].
- **A language-model "plan" did not beat plain search.** Plan minus raw search was +0.08 [-0.14, +0.28] on one set and -0.26 on another. A Claude plan scored the same as a local Qwen3 4B plan (0.00 [-0.20, +0.22]), so the local model stays.
- **Serving.** A TypeScript router + Python shard workers (2 replicas each) on AWS Mumbai: 358 searches with a whole shard machine switched off gave 0 errors; past its limit the router refuses fast (HTTP 429) instead of slowing everyone. Details on the System and Docs pages of the site.

## Run it

- **Viewer** (public site, static): replays 8 recorded real runs and the evidence. `cd web && npm ci && VITE_VIEWER=1 npm run build`. A GitHub Actions workflow publishes it to GitHub Pages.
- **Lab** (live search, on YOUR computer): needs the product photos and index, which are not in this repository (licences differ per source; photos are fetched at run time). Build them once (about 4.3 GB of downloads, and the embedding step is slow on a laptop; the order below comes from each script's own usage line and has not been re-run from an empty machine):
  ```bash
  scripts/setup_env.sh
  .venv/bin/python scripts/fetch_pilot_shards.py && .venv/bin/python scripts/fetch_scale_shards.py
  .venv/bin/python scripts/build_scale_sample.py
  .venv/bin/python scripts/run_eval.py marqo-fashionsiglip --name scale-marqo-fashionsiglip --sample data/sample_scale --manifest data/raw/MANIFEST_scale.json
  .venv/bin/python scripts/build_index.py marqo-fashionsiglip
  GENKART_CATALOGUES=marqo .venv/bin/uvicorn genkart.server:app --app-dir src --port 8000   # Marqo catalogue only
  ```
  The sentence-reading step uses a local model (Ollama) or your own API key; the key goes from your browser to the server for that one request and is never stored. The Kaggle, Myntra and men's-western catalogues need their own downloads and index scripts (`scripts/build_kaggle_index.py`, `build_myntra2_index.py`, `build_mens3_index.py`).
- **Hosted Lab** (Google Cloud Run, all four catalogues): `scripts/make_space.sh` assembles `space-build/` (a Docker app: page and server on one address; the Marqo thumbnails are fetched from their dataset while the image is built and baked in, and the Kaggle, Myntra and men's-western photos are copied in as small thumbnails by `scripts/make_space_photos.py`; 20 searches per minute per visitor). Build it with Cloud Build and deploy with `gcloud run deploy` (see `space/Dockerfile`). It sleeps when idle: the first request after a quiet spell took about 36 to 48 seconds in three measurements. There is no built-in language model there; a visitor's own API key is the only way to use the sentence-reading step.
- **Viewer photos:** the static Viewer shows the photos of the recorded runs by loading them from the hosted Lab when the repository variable `PHOTO_BASE` (the Lab's address) is set; without it the tiles are sketches.
- **Study** (`#/study` on a server started with `GENKART_STUDY=firestore` or `jsonl:<file>`): a consented 5-minute study of whether an AI-drawn preview changes how people rate the same search results (20 prompts, a random half shown with the drawing). Only a random anonymous code, the prompt, with/without drawing, the rating, order, seconds and time are stored; participants can delete their answers with their code. `scripts/study_export.py` downloads the answers (you run it with your own Google sign-in) and writes `runs/study.summary.json`. There are no study results yet: nobody has taken part.
- Tests: `pip install -r requirements.txt && pytest`, and `cd services/router && npm test`.

## Data and licences

The code in this repository is MIT licensed (see `LICENSE`). The data and models below keep their own licences; the MIT licence does not cover them.

Marqo-GS-10M fashion subsets (Apache-2.0 on the dataset card; Zhu et al. 2024, arXiv:2404.08535), Kaggle fashion-product-images (declared MIT, used locally), a Myntra image set (PDDL as declared) and a men's western set (CC-BY-NC-SA). None of the photos are in this repository. The hosted Lab serves small copies of the photos of all four sources (Marqo-GS-10M; Kaggle `paramaggarwal/fashion-product-images-small`; Kaggle `hiteshsuthar101/myntra-fashion-product-dataset`; Kaggle `prashantsharma526/e-commerce-mens-clothing-dataset`, CC-BY-NC-SA, non-commercial use with attribution). The photos belong to the sellers and the licences above are as declared by the dataset uploaders, which may not cover every photo. To have a photo removed, open an issue at https://github.com/Shivb237/lucida/issues and it will be taken down. See each source's page for its terms.

**Status:** milestones 1-7 are done (evaluation harness, baselines, scale, prompt understanding, knowledge graph, sharded serving, AWS). The text and numbers below are from the first pilot (milestone 1) and are kept as the starting point.

## First results (pilot: 64 apparel queries, 3,128 products)

Text query against product photos. Relevance comes from Google Shopping rankings in [Marqo-GS-10M](https://huggingface.co/datasets/Marqo/marqo-GS-10M). Mean over queries, with a 95% bootstrap interval.

| Method | NDCG@10 | Recall@50 | MRR |
|---|---|---|---|
| Random | 0.005 | 0.016 | 0.010 |
| Keyword search on titles (BM25) | 0.397 [0.345, 0.446] | 0.471 [0.404, 0.544] | 0.383 [0.300, 0.473] |
| SigLIP base, query vs photo | 0.498 [0.463, 0.536] | 0.772 [0.713, 0.830] | 0.354 [0.283, 0.428] |
| Marqo-FashionSigLIP, query vs photo | 0.514 [0.480, 0.549] | 0.819 [0.767, 0.867] | 0.387 [0.301, 0.470] |
| Marqo-FashionSigLIP, query vs title | 0.355 | 0.266 | 0.302 |
| Marqo-FashionSigLIP, photo + title added | 0.436 | 0.411 | 0.367 |

Paired comparisons (same queries, interval of the difference):
- Embeddings beat keyword search clearly on NDCG@10 (+0.10 to +0.12) and Recall@50 (+0.30 to +0.35). On first-hit ranking (MRR) they do not clearly differ.
- The fashion-tuned model beats the general one on Recall@50 (+0.046, interval above zero) but **not clearly** on NDCG@10 (+0.017, interval includes zero).
- Naively adding title similarity to photo similarity hurt. That says nothing about better fusion.

## Limitations (read before quoting anything)
- 64 queries from two shards of a 10M-row dataset. Intervals are wide.
- "Apparel" was chosen by a keyword filter, audited by hand: 9 of the first 73 queries (shoe racks, cleaners, hangers) were wrongly kept and are now excluded; about 14 plausible apparel queries are missed.
- Relevance is incomplete: a product the dataset did not list for a query counts as irrelevant even if it is a good match.
- The corpus is small (3,128 products), so this is easier than a real catalogue.
- Not yet done: the v1 baseline (generate an image, then match), context and personalisation, a user study.

## Sources and citation
- Marqo-GS-10M: Apache-2.0 on its dataset card; please cite Zhu et al., "Generalized Contrastive Learning for Multi-Modal Retrieval and Ranking" (2024, [arXiv:2404.08535](https://arxiv.org/abs/2404.08535)). The product photos belong to their sellers: this repository does not contain them; scripts fetch them from the Hugging Face dataset, and the hosted Lab serves small Marqo copies (see Data and licences above).
- Models: [timm/ViT-B-16-SigLIP](https://huggingface.co/timm/ViT-B-16-SigLIP) and [Marqo/marqo-fashionSigLIP](https://huggingface.co/Marqo/marqo-fashionSigLIP), both Apache-2.0 on their cards. Loaded through open_clip (weights only, no remote code).
- No retailer sites are scraped.

## Reproduce
```bash
scripts/setup_env.sh                                # Python 3.14 venv in .venv from requirements.txt (+ diffusers, see below)
.venv/bin/python scripts/fetch_pilot_shards.py      # two parquet shards, about 0.4 GB, records the dataset revision
.venv/bin/python scripts/build_pilot_sample.py      # apparel queries + product photos (git-ignored)
.venv/bin/python scripts/run_eval.py bm25           # also: random, siglip-base, marqo-fashionsiglip[-title|-fused]
.venv/bin/python scripts/compare_runs.py            # table and paired comparisons
.venv/bin/python -m pytest
```
Every run writes `runs/<name>.jsonl` (one line per query) and `runs/<name>.summary.json` (setup, revisions, metrics with intervals). Built and measured on a MacBook Air (Apple M4), Python 3.14, PyTorch 2.14.1 on the Apple GPU (MPS).

## Web UI (see each step happen)
The page (working name: Lucida) runs one request through the whole pipeline and shows every step with its real time: a local language model (Ollama, `qwen3:4b-instruct`) turns the sentence into a plan, a knowledge graph adds related ideas, each piece is searched over four catalogues, and the pieces are matched into one outfit with colour read from the photos. It needs the data built by the milestone 3 and 5 scripts (catalogues, saved indexes under `data/index/`, Kaggle labels), all local and git-ignored; product photos are never stored in the repository.
```bash
ollama serve                                                      # if it is not already running; model: ollama pull qwen3:4b-instruct
.venv/bin/uvicorn genkart.server:app --app-dir src --port 8000   # web server (the first search loads the model and catalogues, about 8 s)
cd web && npm ci && npm run dev                                   # page at http://localhost:5173
scripts/cluster.sh start                                          # optional: encoder + 4 shards x 2 replicas + router; the page then searches through it
```
- **Search**: the real pipeline. Steps that cannot run say so (Ollama off, no graph data) and the rest still runs on the raw sentence. "Play the demo replay" shows a finished run with made-up data drawn as technical flats, labelled DEMO DATA.
- **Links**: `/?demo=1` plays the demo replay; `/?q=your+request` runs a request once the server is up.
- **Evidence**: every number is read from `runs/*.summary.json` when the page is built, including the human-rated tests (`scripts/summarise_blind.py` recomputes them from the raw ratings) and the 20 Stable Diffusion drawings from `data/generated/`.
- **System**: live health of the cluster, plus the recorded correctness, load, failure, replica and ingestion results.

## Two modes: Viewer and Lab (mode menu, top right of the page)
- **Viewer** (the default of a public build, `VITE_VIEWER=1 npm run build`, or `?mode=viewer`): replays 8 real runs recorded with their real step times, and a recording of the AWS system (Mumbai, `runs/aws-*`). Nothing is searched, no key is needed, and no product photos are published (photos appear only on a computer that has them).
- **Lab** (a server on YOUR computer): live searches. The step that reads your sentence uses the local model (Ollama) or **your own API key** (Anthropic, or any OpenAI-compatible provider). The key is typed into the mode menu, kept in the tab's memory only, sent in a POST body to your own server (never in a URL), passed only to the provider you chose, scrubbed from every error, never logged and never part of a recording. Limits: 600 output tokens per call, no retries, and the server stops after `GENKART_BYO_MAX_CALLS` (default 100) calls with a key per start. The model's answer goes through the same checks (`understand.finish`) as the local model's.
- Re-record the Viewer's runs: `.venv/bin/python scripts/record_runs.py "AWS Mumbai (ap-south-1)"` (with the server and Ollama up; refuses to write if any step failed).
