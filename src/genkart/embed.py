"""Text and image embeddings through open_clip (weights only: no remote code is executed)."""
from __future__ import annotations

import numpy as np
import torch
from PIL import Image

# Both models are Apache-2.0 on their Hugging Face cards (checked 2026-10-11).
MODELS = {
    "siglip-base": "hf-hub:timm/ViT-B-16-SigLIP",
    "marqo-fashionsiglip": "hf-hub:Marqo/marqo-fashionSigLIP",
    # SigLIP 2 family: Apache-2.0 on the cards (checked 2026-10-12), loaded with transformers (weights only, no remote code).
    # ZooClaw-FashionSigLIP2 claims (vendor-reported, preprint arXiv:2606.27708) are NOT trusted until our own run agrees.
    "siglip2-base-384": "transformers:google/siglip2-base-patch16-384",
    "zooclaw-fashionsiglip2": "transformers:srpone/zooclaw-fashionsiglip2",
}
TEXT_LEN = 64  # SigLIP 2 text length per the model cards


def pick_device() -> str:
    return "mps" if torch.backends.mps.is_available() else "cpu"


class _HFSigLIP:
    """Gives a transformers SigLIP 2 model the same encode_image / encode_text surface as an open_clip model."""

    def __init__(self, model):
        self.m = model

    def to(self, device):
        self.m = self.m.to(device)
        return self

    def eval(self):
        self.m.eval()
        return self

    def encode_image(self, pixel_values):
        # transformers 5 returns a wrapper; pooler_output was checked equal to the model's documented image_embeds
        return self.m.get_image_features(pixel_values=pixel_values).pooler_output

    def encode_text(self, input_ids):
        return self.m.get_text_features(input_ids=input_ids).pooler_output


# Exact Hugging Face revisions (commit hashes) of the model files that produced every logged result, read from the local download cache
# on 2026-10-15. Every model is loaded at exactly this revision: the transformers ones through `revision=`, the open_clip ones by downloading
# that snapshot first (huggingface_hub.snapshot_download) and loading it from the folder ("local-dir:"), since open_clip's hf-hub loader has no
# revision argument. A changed model upstream therefore cannot change a result; a missing revision fails loudly instead.
REVISIONS = {
    "siglip-base": "41f575766f40e752fdd1383e9565b7f02388c1c4",
    "marqo-fashionsiglip": "c56244cc94f92419e8369fa71efdaf403b124ce8",
    "siglip2-base-384": "f775b65a79762255128c981547af89addcfe0f88",
    "zooclaw-fashionsiglip2": "d2c0c98de9cd1e27c114267ddfbb584eb98b5ebf",
}


def repo_of(name: str) -> str:
    return MODELS[name].removeprefix("hf-hub:").removeprefix("transformers:")


def _load_transformers(name: str):
    from transformers import AutoModel, AutoProcessor

    repo = repo_of(name)
    processor = AutoProcessor.from_pretrained(repo, revision=REVISIONS[name])
    model = _HFSigLIP(AutoModel.from_pretrained(repo, revision=REVISIONS[name]))

    def preprocess(img):
        return processor(images=img, return_tensors="pt")["pixel_values"][0]

    def tokenizer(texts):
        # SigLIP 2 was trained on lowercase text. Without this, a title finds its own photo 0.7% of the time instead of 57.3%
        # (300-product check, 2026-10-12, no evaluation labels used).
        texts = [t.lower() for t in texts]
        return processor(text=texts, padding="max_length", max_length=TEXT_LEN, truncation=True, return_tensors="pt")["input_ids"]

    device = pick_device()
    return model.to(device).eval(), preprocess, tokenizer, device


# What open_clip reads from a model folder (the Marqo repo also holds ONNX exports and a second copy of the weights, which are not downloaded).
# The tokenizer then comes from the model's own folder instead of the hf_tokenizer_name repo (timm/ViT-B-16-SigLIP) its config names; the two
# tokenizers gave identical token ids on all 852 logged scale queries plus the built-in examples (checked 2026-10-18).
OPEN_CLIP_FILES = ["open_clip_config.json", "open_clip_model.safetensors", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json", "spiece.model"]


def snapshot(name: str) -> str:
    """Local folder of the model files at exactly REVISIONS[name] (downloaded once; with HF_HUB_OFFLINE=1 read from the cache only).
    The cache names each snapshot folder after its commit hash, which is checked, so a wrong folder can never be used silently."""
    import pathlib

    from huggingface_hub import snapshot_download

    path = snapshot_download(repo_of(name), revision=REVISIONS[name], allow_patterns=OPEN_CLIP_FILES)
    if pathlib.Path(path).name != REVISIONS[name]:
        raise RuntimeError(f"{repo_of(name)}: got snapshot {pathlib.Path(path).name}, expected revision {REVISIONS[name]}")
    missing = [f for f in ("open_clip_config.json", "open_clip_model.safetensors") if not (pathlib.Path(path) / f).is_file()]
    if missing:      # open_clip only warns when a folder has no weights, then builds a model with random ones: every search would be noise
        raise RuntimeError(f"{repo_of(name)}@{REVISIONS[name]}: {', '.join(missing)} not in the snapshot")
    return path


def load(name: str, text_only: bool = False):
    """(model, preprocess, tokenizer, device). text_only=True (open_clip models): the image half of the model is dropped right after loading,
    for a process that only ever encodes text (the web server; the photo vectors were all computed ahead of time). encode_images then fails
    loudly instead of quietly using memory nobody needs. The transformers models ignore it (none of them is served)."""
    if MODELS[name].startswith("transformers:"):
        return _load_transformers(name)
    import gc

    import open_clip

    spec = f"local-dir:{snapshot(name)}"                 # the pinned revision, not whatever the hub's main branch holds today
    model, _, preprocess = open_clip.create_model_and_transforms(spec)
    tokenizer = open_clip.get_tokenizer(spec)
    if text_only and hasattr(model, "visual"):
        model.visual = None                               # the image tower's weights go with it (about half the model)
        gc.collect()
    device = pick_device()
    return model.to(device).eval(), preprocess, tokenizer, device


def _normalise(x: torch.Tensor) -> np.ndarray:
    return (x / x.norm(dim=-1, keepdim=True)).float().cpu().numpy()


@torch.no_grad()
def encode_images(model, preprocess, paths: list[str], device: str, batch: int = 64) -> np.ndarray:
    out = []
    for i in range(0, len(paths), batch):
        imgs = torch.stack([preprocess(Image.open(p).convert("RGB")) for p in paths[i : i + batch]]).to(device)
        out.append(_normalise(model.encode_image(imgs)))
    return np.concatenate(out)


@torch.no_grad()
def encode_texts(model, tokenizer, texts: list[str], device: str, batch: int = 128) -> np.ndarray:
    out = []
    for i in range(0, len(texts), batch):
        tokens = tokenizer(texts[i : i + batch]).to(device)
        out.append(_normalise(model.encode_text(tokens)))
    return np.concatenate(out)
