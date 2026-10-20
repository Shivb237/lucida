# The base image pinned by digest: python:3.14-slim, the multi-arch index read from Docker Hub's registry on 2026-10-18.
# To move to a newer base: docker buildx imagetools inspect python:3.14-slim   (the "Digest:" line), then rebuild and re-run the checks in README.md.
FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
# not root: the app needs no privileges
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR $HOME/app
# every package is hash-checked (scripts/lock.sh made both files): first CPU-only torch from PyTorch's own index (the host has no GPU), then the rest
COPY --chown=user requirements-torch-cpu.txt requirements-space.txt ./
RUN pip install --no-cache-dir --require-hashes --no-deps --index-url https://download.pytorch.org/whl/cpu -r requirements-torch-cpu.txt
RUN pip install --no-cache-dir --require-hashes -r requirements-space.txt
# the two slow downloads come BEFORE the rest of the code is copied in, each after only the files it reads, so a change anywhere else (the server,
# the page, an index) reuses both cached layers instead of downloading the model and Marqo's 20 photo files again.
# the search model is downloaded now, into the image, at the revision every logged result used (embed.REVISIONS): the build fails on any other one
COPY --chown=user src/genkart/__init__.py src/genkart/embed.py src/genkart/
RUN PYTHONPATH=src python -c "from genkart import embed; import pathlib; p = embed.snapshot('marqo-fashionsiglip'); assert pathlib.Path(p).name == embed.REVISIONS['marqo-fashionsiglip'], p; embed.load('marqo-fashionsiglip')"
# the product photos are fetched once, at build time, from Marqo's dataset (small copies) and live inside the image: no download at start-up, and nothing in git.
# The script reads only the dataset manifest (repo, revision, sha256 per file) and the list of products the index knows.
COPY --chown=user scripts/space_fetch_photos.py scripts/
COPY --chown=user data/raw/MANIFEST_scale.json data/raw/
COPY --chown=user data/sample_scale/products.jsonl data/sample_scale/
RUN python scripts/space_fetch_photos.py && ! grep -q 'missing [1-9]' data/images/.done
# everything else (the code, the page, the indexes, the other catalogues' thumbnails, which join the Marqo photos in data/images/)
COPY --chown=user . .
# one address for page and server; all four catalogues (the Marqo photos are baked in above, the other catalogues' thumbnails were copied in); per-visitor limits
# (no server-wide count of key calls, GENKART_BYO_MAX_CALLS=0: it would refuse every visitor once the first ones used it up; each address has 30 an hour);
# the host's proxy appends the real client address to X-Forwarded-For (one hop). GENKART_STUDY is NOT set here: it is set at deploy time (space/cloudrun.yaml),
# so a copy of this image run anywhere else never writes to the study's database.
ENV PYTHONPATH=src GENKART_SERVE_WEB=1 GENKART_IMAGES_FLAT=1 GENKART_BEHIND_PROXY=1 GENKART_XFF_HOPS=1 GENKART_RATE_PER_MIN=20 GENKART_MAX_RUNS=4 GENKART_BYO_MAX_CALLS=0 GENKART_BYO_PER_ADDR_PER_HOUR=30 GENKART_HOSTED=1 HF_HUB_OFFLINE=1
EXPOSE 7860
# ready = the model, the catalogues and the knowledge graph are loaded (/api/health only says the process is alive). Cloud Run uses the startup probe in cloudrun.yaml instead.
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/ready' % os.environ.get('PORT', '7860'), timeout=4)"
CMD ["sh", "start.sh"]
