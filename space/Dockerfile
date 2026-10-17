FROM python:3.14-slim
# not root: the app needs no privileges
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR $HOME/app
# CPU-only torch (the host has no GPU), then the pinned rest
RUN pip install --no-cache-dir torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cpu
COPY --chown=user requirements-space.txt .
RUN pip install --no-cache-dir -r requirements-space.txt
COPY --chown=user . .
# the search model is downloaded now, into the image, so the first visitor does not wait for it
RUN PYTHONPATH=src python -c "from genkart import embed; embed.load('marqo-fashionsiglip')"
# the product photos are fetched once, at build time, from Marqo's dataset (small copies) and live inside the image: no download at start-up, and nothing in git
RUN PYTHONPATH=src python scripts/space_fetch_photos.py && ! grep -q 'missing [1-9]' data/images/.done
# one address for page and server; all four catalogues (the Marqo photos are baked in above, the other catalogues' thumbnails were copied in); per-visitor limits; the host's proxy appends the real client address to X-Forwarded-For
ENV PYTHONPATH=src GENKART_SERVE_WEB=1 GENKART_IMAGES_FLAT=1 GENKART_STUDY=firestore GENKART_BEHIND_PROXY=1 GENKART_RATE_PER_MIN=20 GENKART_MAX_RUNS=4 GENKART_BYO_MAX_CALLS=0 GENKART_HOSTED=1 HF_HUB_OFFLINE=1
EXPOSE 7860
CMD ["sh", "start.sh"]
