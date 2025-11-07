#!/usr/bin/env python3
from __future__ import annotations
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional
from lxml import etree as ET

# ──────────────────────────────────────────────────────────────────────────────
# XML MERGE
# ──────────────────────────────────────────────────────────────────────────────

def merge_catalog_xml(file_a: Path, file_b: Path, out_file: Path) -> None:
    """Merge two SC2 catalog XML files node-by-node and child-by-child."""
    parser = ET.XMLParser(remove_blank_text=True)

    def safe_parse(file: Path) -> Optional[ET._Element]:
        if not file.exists():
            return None
        try:
            return ET.parse(str(file), parser).getroot()
        except ET.XMLSyntaxError:
            print(f"⚠️  Skipping invalid XML: {file}")
            return None

    root_a = safe_parse(file_a)
    root_b = safe_parse(file_b)

    if root_a is None and root_b is not None:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(file_b, out_file)
        return
    elif root_b is None and root_a is not None:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(file_a, out_file)
        return
    elif root_a is None and root_b is None:
        return

    merged = ET.Element(root_a.tag, root_a.attrib)
    by_id: dict[str, ET._Element] = {}

    for child in root_a:
        cid = child.attrib.get("id")
        if cid:
            by_id[cid] = child
        merged.append(child)

    for child_b in root_b:
        cid = child_b.attrib.get("id")
        if cid in by_id:
            merge_xml_children_nodes(by_id[cid], child_b)
        else:
            merged.append(child_b)

    out_file.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(merged).write(str(out_file), encoding="utf-8", pretty_print=True, xml_declaration=True)

def merge_xml_children_nodes(target: ET._Element, source: ET._Element) -> None:
    """Merge sub-elements and attributes of matching XML nodes."""
    for k, v in source.attrib.items():
        target.attrib[k] = v
    index_map = {(c.tag, c.attrib.get("index")): c for c in target}
    for c in source:
        key = (c.tag, c.attrib.get("index"))
        if key in index_map:
            merge_xml_children_nodes(index_map[key], c)
        else:
            target.append(c)

# ──────────────────────────────────────────────────────────────────────────────
# TXT MERGE (key=value lines)
# ──────────────────────────────────────────────────────────────────────────────

def merge_txt_files(base: Path, patch: Path, extra: Path, out_file: Path) -> None:
    """Merge three txt files (map < patch < extra). On conflict, higher wins."""
    def read_kv(path: Path) -> dict[str, str]:
        data = {}
        if not path.exists():
            return data
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip()
        return data

    base_kv = read_kv(base)
    patch_kv = read_kv(patch)
    extra_kv = read_kv(extra)

    merged = base_kv.copy()
    for src, name in [(patch_kv, "patch"), (extra_kv, "extra")]:
        for k, v in src.items():
            if k in merged and merged[k] != v:
                print(f"⚠️  Conflict on '{k}' → using {name} value ({v})")
            merged[k] = v

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", encoding="utf-8") as f:
        for k, v in sorted(merged.items()):
            f.write(f"{k}={v}\n")

# ──────────────────────────────────────────────────────────────────────────────
# FILE MERGING STRATEGY
# ──────────────────────────────────────────────────────────────────────────────

def merge_file_triple(base: Path, patch: Path, extra: Path, dest: Path) -> None:
    """Merge or copy directly into dest (no temp files)."""
    suffix = base.suffix or patch.suffix or extra.suffix
    exists = [p.exists() for p in (base, patch, extra)]
    if not any(exists):
        return

    dest.parent.mkdir(parents=True, exist_ok=True)

    if suffix == ".xml":
        # Start with map or patch
        if base.exists():
            shutil.copy(base, dest)
        elif patch.exists():
            shutil.copy(patch, dest)
        # Merge patch and extra over it
        if patch.exists():
            merge_catalog_xml(dest, patch, dest)
        if extra.exists():
            merge_catalog_xml(dest, extra, dest)
    elif suffix == ".txt":
        merge_txt_files(base, patch, extra, dest)
    else:
        # Copy the highest-priority existing file
        src = extra if extra.exists() else patch if patch.exists() else base
        shutil.copy(src, dest)

# ──────────────────────────────────────────────────────────────────────────────
# MERGE PIPELINE: MAP < PATCH < EXTRA
# ──────────────────────────────────────────────────────────────────────────────

def merge_all(map_dir: Path, patch_dir: Path, extra_dir: Path, out_dir: Path) -> None:
    """Merge map < patch < extra directly into out_dir."""
    print(f"🔧 Merging map ({map_dir.name}) < patch ({patch_dir.name}) < extra ({extra_dir.name})")

    all_files: set[Path] = set()
    for src in [map_dir, patch_dir, extra_dir]:
        if src.exists():
            for f in src.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(src)
                    all_files.add(rel)

    for rel in sorted(all_files):
        base = map_dir / rel
        patch = patch_dir / rel
        extra = extra_dir / rel
        dest = out_dir / rel
        merge_file_triple(base, patch, extra, dest)

# ──────────────────────────────────────────────────────────────────────────────
# PACK MAP
# ──────────────────────────────────────────────────────────────────────────────

def pack_map_folder(src_folder: Path, out_file: Path, force: bool = False) -> None:
    """Pack a map folder into a .SC2Map (MPQ) using Docker + mpqcli."""
    src_folder = src_folder.resolve()
    out_file = out_file.resolve()

    if not src_folder.exists():
        raise FileNotFoundError(f"Map folder not found: {src_folder}")

    out_file.parent.mkdir(parents=True, exist_ok=True)
    if out_file.exists():
        if force:
            out_file.unlink()
        else:
            raise FileExistsError(f"Output exists: {out_file}. Use --force to overwrite.")

    print("🐳 Using Docker (ghcr.io/thegraydot/mpqcli:latest) to pack map → MPQ")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        mpq_out = tmpdir / "output.mpq"

        cmd = [
            "docker", "run", "--rm",
            "-v", f"{src_folder}:/data/map:ro",
            "-v", f"{tmpdir}:/data/output",
            "ghcr.io/thegraydot/mpqcli:latest",
            "create", "/data/map", "--output", "/data/output/output.mpq"
        ]

        subprocess.run(cmd, check=True)
        if not mpq_out.exists():
            raise RuntimeError("mpqcli did not produce an MPQ file!")

        shutil.move(str(mpq_out), str(out_file))
        print(f"✅ Packed SC2Map created → {out_file}")

# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Merge SC2 map, patch, and extra fixes into a packed .SC2Map")
    parser.add_argument("map_folder", type=Path, help="Path to the base map folder")
    parser.add_argument("game_patch", type=Path, help="Path to the Game Patch mod folder")
    parser.add_argument("extra_fixes", type=Path, help="Path to Extra Fixes mod folder")
    parser.add_argument("output", type=Path, help="Output map name (without extension)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output files")
    args = parser.parse_args()

    map_dir = args.map_folder.resolve()
    patch_dir = args.game_patch.resolve()
    extra_dir = args.extra_fixes.resolve()
    out_name = args.output.stem

    cwd = Path.cwd()
    out_dir = cwd / "Output" / out_name
    out_file = cwd / "Output" / f"{out_name}.SC2Map"

    if out_dir.exists() and args.force:
        shutil.rmtree(out_dir)
    elif out_dir.exists():
        print(f"❌ Output folder exists: {out_dir} (use --force)")
        sys.exit(1)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"📦 Merging into {out_dir}")
    merge_all(map_dir, patch_dir, extra_dir, out_dir)

    print(f"🗜️  Packing → {out_file}")
    pack_map_folder(out_dir, out_file, force=args.force)
    print("✅ Build complete!")

if __name__ == "__main__":
    main()
