#!/bin/sh
# Rebuild every requirements lock from its .in file, with hashes, so an install can only get exactly the files that were checked:
#   requirements.in               -> requirements.txt                (the laptop / CI environment; the source of every version)
#   space/requirements-space.in   -> space/requirements-space.txt    (the hosted Lab image)
#   deploy/requirements-*.in      -> deploy/requirements-*.txt       (the AWS encoder, shard and ingest hosts)
#   PyTorch's CPU index           -> space/requirements-torch-cpu.txt
# Every smaller .in file starts with `-c ../requirements.txt`, so a package has the same version everywhere. pip-compile keeps the pins already in an
# output file; to move a version, change it in requirements.in (or delete the line from requirements.txt) and run this again.
# Needs pip-tools in the project environment (.venv/bin/python -m pip install pip-tools; it is a tool for this script only, not a project dependency).
#
# torch and torchvision on Linux: the CPU builds (2.14.1+cpu) live only on PyTorch's own index, and pip-compile cannot resolve them from this Mac
# (they have no macOS wheel, and pip-compile resolves for the machine it runs on). So they are left out of the space and encoder locks
# (--unsafe-package) and pinned in requirements-torch-cpu.txt instead, with the sha256 that PyTorch's index publishes for each Linux wheel
# (read from the index page below, never typed by hand). Install order: requirements-torch-cpu.txt with --no-deps, then the lock, both --require-hashes.
# The locks are resolved here, for Python 3.14 on macOS; the hashes cover every wheel of each pinned version on PyPI, so the same files install on
# Linux and on the AWS hosts' Python 3.12. A package whose dependencies differ by platform would need its own run on that platform (none do today).
# Hashes: pip-compile asks PyPI's JSON API for each file's sha256 and, when it gets none (the case for every package in 2026), downloads every wheel
# of every version to hash it itself (gigabytes for torch alone). The package index already publishes the sha256 of each file (the same value pip
# checks when it installs), so pip-compile is run with a small patch that takes that published value whenever the index gives one.
set -eu
cd "$(dirname "$0")/.."
PC_PY='import sys
from piptools.repositories.pypi import PyPIRepository
slow = PyPIRepository._get_file_hash
def published(self, link):
    return f"sha256:{link.hash}" if link.hash_name == "sha256" and link.hash else slow(self, link)
PyPIRepository._get_file_hash = published
from piptools.scripts.compile import cli
sys.exit(cli())'
PC() { .venv/bin/python -c "$PC_PY" --quiet --generate-hashes --strip-extras --no-emit-index-url "$@"; }
PC --allow-unsafe -o requirements.txt requirements.in
PC --unsafe-package torch --unsafe-package torchvision -o space/requirements-space.txt space/requirements-space.in
PC --unsafe-package torch --unsafe-package torchvision -o deploy/requirements-encoder.txt deploy/requirements-encoder.in
PC --allow-unsafe -o deploy/requirements-shard.txt deploy/requirements-shard.in
PC --allow-unsafe -o deploy/requirements-ingest.txt deploy/requirements-ingest.in

TORCH=$(sed -n 's/^torch==\([0-9.]*\).*/\1/p' requirements.txt)
VISION=$(sed -n 's/^torchvision==\([0-9.]*\).*/\1/p' requirements.txt)
INDEX=https://download.pytorch.org/whl/cpu
hashes() {   # $1 package, $2 version: the published sha256 of its CPU wheels for Linux, CPython 3.12 and 3.14, x86_64 and aarch64
  curl -fsS "$INDEX/$1/" | grep -o "$1-$2%2Bcpu-cp31[24]-cp31[24]-manylinux[^\"#]*#sha256=[0-9a-f]*" | sed 's/.*#sha256=/    --hash=sha256:/' | sort -u
}
{
  echo "# CPU builds of torch and torchvision for the Linux images and hosts (made by scripts/lock.sh from $INDEX: the hashes are the ones the index publishes)."
  echo "# Install: pip install --require-hashes --no-deps --index-url $INDEX -r requirements-torch-cpu.txt"
  echo "torch==$TORCH+cpu \\"
  hashes torch "$TORCH" | sed '$!s/$/ \\/'
  echo "torchvision==$VISION+cpu \\"
  hashes torchvision "$VISION" | sed '$!s/$/ \\/'
} > space/requirements-torch-cpu.txt
grep -q 'sha256:' space/requirements-torch-cpu.txt || { echo "no torch hashes found on $INDEX"; exit 1; }
echo "locks rebuilt: requirements.txt space/requirements-space.txt space/requirements-torch-cpu.txt deploy/requirements-{encoder,shard,ingest}.txt"
