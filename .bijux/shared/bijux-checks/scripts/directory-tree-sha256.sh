#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 1 ]]; then
  echo "usage: directory-tree-sha256.sh <directory>" >&2
  exit 2
fi

target_dir="$1"
if [[ ! -d "${target_dir}" ]]; then
  echo "ERROR: missing directory ${target_dir}" >&2
  exit 1
fi

(
  cd "${target_dir}"
  find . \
    \( -type d \( \
      -name __pycache__ -o \
      -name .mypy_cache -o \
      -name .pytest_cache -o \
      -name .ruff_cache \
    \) -prune \) -o \
    \( -type f \
      ! -name .DS_Store \
      ! -name '*.py[co]' \
      -print \
    \) |
    LC_ALL=C sort |
    python3 -c '
import os
import subprocess
import sys

# Bounded batches preserve the sorted Perl shasum byte stream without per-file startup.
max_arguments = 125
max_argument_bytes = 32768
fixed_argument_bytes = sum(len(value) + 1 for value in (b"shasum", b"-a", b"256"))
batch = []
argument_bytes = fixed_argument_bytes

def hash_batch(paths):
    try:
        subprocess.run(["shasum", "-a", "256", *paths], check=True)
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode)

for line in sys.stdin.buffer:
    file_bytes = line[:-1] if line.endswith(b"\n") else line
    file_rel = os.fsdecode(file_bytes)
    size = len(file_bytes) + 1
    if fixed_argument_bytes + size > max_argument_bytes:
        print("ERROR: hash argument exceeds the bounded batch budget", file=sys.stderr)
        raise SystemExit(1)
    if batch and (len(batch) >= max_arguments or argument_bytes + size > max_argument_bytes):
        hash_batch(batch)
        batch = []
        argument_bytes = fixed_argument_bytes
    batch.append(file_rel)
    argument_bytes += size
if batch:
    hash_batch(batch)
'
) | shasum -a 256 | awk '{print $1}'
