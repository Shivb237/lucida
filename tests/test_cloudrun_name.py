"""The Cloud Run service must keep the live name genkart-lab (a new name is a new service with a new URL, which breaks the Pages site's PHOTO_BASE).
Read as text, so no YAML library is needed."""
import pathlib
import re

CFG = pathlib.Path(__file__).resolve().parents[1] / "space" / "cloudrun.yaml"


def test_service_name_is_the_live_one():
    text = CFG.read_text()
    block = re.search(r"^metadata:[ \t]*\n((?:[ \t]+[^\n]*\n|[ \t]*\n)*)", text, re.M)
    assert block, "no metadata block"
    name = re.search(r"^[ \t]+name:[ \t]*([^\s#]+)", block.group(1), re.M)
    assert name and name.group(1) == "genkart-lab", name and name.group(1)


def test_scale_cap_and_startup_probe_are_set():
    text = CFG.read_text()
    assert 'autoscaling.knative.dev/maxScale: "6"' in text
    assert 'run.googleapis.com/maxScale: "6"' in text
    assert "serviceAccountName: 746545184590-compute@developer.gserviceaccount.com" in text
    assert "image: asia-south1-docker.pkg.dev/cs-project-lex2cwgp/genkart/lab:" in text
    assert re.search(r"containerPort: 7860\b", text)
    assert re.search(r"startupProbe:\s*\n\s+httpGet:\s*\n\s+path: /api/ready\b", text)
    assert re.search(r"livenessProbe:\s*\n\s+httpGet:\s*\n\s+path: /api/health\b", text)
