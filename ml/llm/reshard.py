"""Rewrite a safetensors checkpoint into small shards. Standard library only.

    python -m ml.llm.reshard <source_dir> <target_dir> [--max-mb 512]

Why: on Windows, mapping one 4 GB shard reserves commit for the whole file, and a
small page file refuses it (os error 1455). Small shards load one at a time within
the commit limit. The tensors are copied byte for byte, never converted: every
tensor's SHA-256 is checked against the source after writing. Tokenizer and config
files are copied unchanged. Nothing is downloaded and the source is not modified.
"""

import argparse
import hashlib
import json
import shutil
import struct
import sys
from pathlib import Path
from typing import Dict, List, Tuple

CHUNK = 8 * 1024 * 1024
COPY_SUFFIXES = (".json", ".txt", "LICENSE")


def read_header(path: Path) -> Tuple[int, Dict[str, dict]]:
    with path.open("rb") as f:
        (length,) = struct.unpack("<Q", f.read(8))
        header = json.loads(f.read(length).decode("utf-8"))
    return 8 + length, header


def _copy_range(src, dst, start: int, size: int, digest) -> None:
    src.seek(start)
    left = size
    while left:
        block = src.read(min(CHUNK, left))
        if not block:
            raise IOError("source ended early")
        dst.write(block)
        digest.update(block)
        left -= len(block)


def _hash_range(f, start: int, size: int) -> str:
    digest = hashlib.sha256()
    f.seek(start)
    left = size
    while left:
        block = f.read(min(CHUNK, left))
        digest.update(block)
        left -= len(block)
    return digest.hexdigest()


def plan(tensors: List[Tuple[str, Path, int, dict]], max_bytes: int) -> List[List[Tuple[str, Path, int, dict]]]:
    shards, current, size = [], [], 0
    for item in tensors:
        start, end = item[3]["data_offsets"]
        n = end - start
        if current and size + n > max_bytes:
            shards.append(current)
            current, size = [], 0
        current.append(item)
        size += n
    if current:
        shards.append(current)
    return shards


def reshard(source: Path, target: Path, max_mb: int = 512) -> Dict[str, object]:
    if target.exists() and any(target.iterdir()):
        raise SystemExit("target directory is not empty")
    target.mkdir(parents=True, exist_ok=True)
    tensors: List[Tuple[str, Path, int, dict]] = []
    for shard in sorted(source.glob("*.safetensors")):
        base, header = read_header(shard)
        for name, meta in header.items():
            if name != "__metadata__":
                tensors.append((name, shard, base, meta))
    tensors.sort(key=lambda t: (str(t[1]), t[3]["data_offsets"][0]))
    groups = plan(tensors, max_mb * 1024 * 1024)
    weight_map: Dict[str, str] = {}
    total = 0
    for i, group in enumerate(groups, 1):
        name = f"model-{i:05d}-of-{len(groups):05d}.safetensors"
        header, offset = {"__metadata__": {"format": "pt"}}, 0
        for tname, _, _, meta in group:
            start, end = meta["data_offsets"]
            header[tname] = {"dtype": meta["dtype"], "shape": meta["shape"],
                             "data_offsets": [offset, offset + end - start]}
            offset += end - start
        raw = json.dumps(header, separators=(",", ":")).encode("utf-8")
        raw += b" " * (-len(raw) % 8)
        with (target / name).open("wb") as out:
            out.write(struct.pack("<Q", len(raw)))
            out.write(raw)
            for tname, src_path, base, meta in group:
                start, end = meta["data_offsets"]
                digest = hashlib.sha256()
                with src_path.open("rb") as src:
                    _copy_range(src, out, base + start, end - start, digest)
                meta["_sha256"] = digest.hexdigest()
                weight_map[tname] = name
        total += offset
    # Verify every tensor in the new files against the source hash.
    for i in range(1, len(groups) + 1):
        name = f"model-{i:05d}-of-{len(groups):05d}.safetensors"
        base, header = read_header(target / name)
        with (target / name).open("rb") as f:
            for tname, meta in header.items():
                if tname == "__metadata__":
                    continue
                start, end = meta["data_offsets"]
                expected = next(t[3]["_sha256"] for t in tensors if t[0] == tname)
                if _hash_range(f, base + start, end - start) != expected:
                    raise SystemExit("tensor mismatch after copy")
    (target / "model.safetensors.index.json").write_text(
        json.dumps({"metadata": {"total_size": total}, "weight_map": weight_map}, indent=1), encoding="utf-8")
    for item in source.iterdir():
        if item.is_file() and item.suffix != ".safetensors" and item.name != "model.safetensors.index.json" \
                and (item.suffix in COPY_SUFFIXES or item.name in COPY_SUFFIXES):
            shutil.copy2(item, target / item.name)
    return {"shards": len(groups), "tensors": len(tensors), "bytes": total, "verified": True}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ml.llm.reshard")
    parser.add_argument("source")
    parser.add_argument("target")
    parser.add_argument("--max-mb", type=int, default=512)
    args = parser.parse_args(argv)
    print(json.dumps(reshard(Path(args.source), Path(args.target), args.max_mb)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
