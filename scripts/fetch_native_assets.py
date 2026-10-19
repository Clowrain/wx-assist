"""Extract pinned native resources from the original author's release, without running it."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import struct
import urllib.request
import zlib

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path(__file__).with_name("native-assets.json")
COOKIE = struct.Struct("!8sIIII64s")
ENTRY = struct.Struct("!IIIIBc")
MAGIC = b"MEI\x0c\x0b\x0a\x0b\x0e"


def verify(data, expected, label):
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch for {label}: {actual}")


def extract_resources(data, manifest):
    """Parse only the allowlisted PyInstaller CArchive members; execute no archive code."""
    verify(data, manifest["sha256"], "upstream release")
    if len(data) != manifest["size"]:
        raise ValueError("Unexpected upstream release size")
    cookie_offset = data.rfind(MAGIC)
    if cookie_offset < 0 or cookie_offset + COOKIE.size > len(data):
        raise ValueError("Missing PyInstaller cookie")
    _, package_size, toc_offset, toc_size, _, _ = COOKIE.unpack_from(data, cookie_offset)
    archive_start = cookie_offset + COOKIE.size - package_size
    cursor = archive_start + toc_offset
    end = cursor + toc_size
    if not 0 <= archive_start <= cursor <= end <= cookie_offset:
        raise ValueError("Invalid archive bounds")
    resources = {}
    while cursor < end:
        if cursor + ENTRY.size > end:
            raise ValueError("Truncated archive table")
        size, offset, stored_size, raw_size, compressed, kind = ENTRY.unpack_from(data, cursor)
        if size <= ENTRY.size or cursor + size > end:
            raise ValueError("Invalid archive entry")
        name = data[cursor + ENTRY.size:cursor + size].rstrip(b"\0").decode("utf-8").replace("\\", "/")
        cursor += size
        if name not in manifest["files"]:
            continue
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or ":" in name or name in resources:
            raise ValueError(f"Unsafe or duplicate resource: {name}")
        start = archive_start + offset
        if kind not in (b"b", b"x") or not 0 < raw_size <= 10 * 1024 * 1024:
            raise ValueError(f"Unexpected resource type or size: {name}")
        if not archive_start <= start <= start + stored_size <= archive_start + toc_offset:
            raise ValueError(f"Invalid resource bounds: {name}")
        payload = data[start:start + stored_size]
        if compressed:
            decoder = zlib.decompressobj()
            payload = decoder.decompress(payload, raw_size + 1)
            if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                raise ValueError(f"Invalid compressed resource: {name}")
        if len(payload) != raw_size:
            raise ValueError(f"Invalid uncompressed size: {name}")
        verify(payload, manifest["files"][name], name)
        resources[name] = payload
    if set(resources) != set(manifest["files"]):
        raise ValueError(f"Missing resources: {set(manifest['files']) - set(resources)}")
    return resources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="Use an already downloaded release")
    parser.add_argument("--output-dir", type=Path, default=ROOT, help="Parent directory for lib/")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    archive = args.archive or ROOT / "build/downloads/wx-assist-v1.7.0-no-rag.exe"
    if not archive.exists():
        if args.archive:
            raise FileNotFoundError(archive)
        archive.parent.mkdir(parents=True, exist_ok=True)
        part = archive.with_suffix(".part")
        try:
            request = urllib.request.Request(manifest["url"], headers={"User-Agent": "wx-assist-build"})
            with urllib.request.urlopen(request, timeout=120) as response, part.open("wb") as output:
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > manifest["size"]:
                        raise ValueError("Download exceeds pinned release size")
                    output.write(chunk)
            verify(part.read_bytes(), manifest["sha256"], "download")
            part.replace(archive)
        finally:
            part.unlink(missing_ok=True)
    resources = extract_resources(archive.read_bytes(), manifest)
    output_root = args.output_dir.resolve()
    # Validate all members before writing any. Never follow an output symlink out of the root.
    for name in resources:
        if not (output_root / name).resolve().is_relative_to(output_root):
            raise ValueError(f"Resource escapes output root: {name}")
    for name, payload in resources.items():
        target = output_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        print(f"Verified {name}: {len(payload)} bytes, sha256={manifest['files'][name]}")


if __name__ == "__main__":
    main()
