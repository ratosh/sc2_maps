#!/usr/bin/env python3
from __future__ import annotations
from collections import Counter
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional
from lxml import etree as ET


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


def xml_identity_key(node: ET._Element):
    """
    Determine a stable identity for SC2 XML.
    """
    a = node.attrib

    if "id" in a:
        return ("id", node.tag, a["id"])
    if "index" in a:
        return ("index", node.tag, a["index"])
    if "value" in a:
        return ("value", node.tag, a["value"])
    if a:
        return ("attrs", node.tag, tuple(sorted(a.items())))
    return ("unique", None)  # None because we won't use object id for uniqueness check here

def element_signature(node: ET._Element):
    tag = node.tag
    attrib_tuple = tuple(sorted(node.attrib.items()))
    text = (node.text.strip() if node.text and node.text.strip() else None)

    child_sigs = []
    for c in node:
        child_sigs.append(element_signature(c))

    children_counter = Counter(child_sigs)

    children_counter_tuple = tuple(sorted(children_counter.items()))

    return (tag, attrib_tuple, text, children_counter_tuple)

def merge_xml_children_nodes(target: ET._Element, source: ET._Element) -> None:
    """
    Merge sub-elements and attributes of matching XML nodes.
    """
    for k, v in source.attrib.items():
        target.attrib[k] = v

    key_map: dict[tuple, list[ET._Element]] = {}
    for c in target:
        key = xml_identity_key(c)
        key_map.setdefault(key, []).append(c)

    for child in source:
        key = xml_identity_key(child)
        if key[0] != "unique":
            targets = key_map.get(key)
            if targets:
                merge_xml_children_nodes(targets[0], child)
            else:
                target.append(child)
                key_map.setdefault(key, []).append(child)
        else:
            child_sig = element_signature(child)

            existing_list = []

            for k, lst in key_map.items():
                if k[0] == "unique" and k[1] == child.tag:
                    existing_list.extend(lst)

            found_equivalent = False
            for existing in existing_list:
                if element_signature(existing) == child_sig:
                    found_equivalent = True
                    break

            if not found_equivalent:
                target.append(child)
                key_map.setdefault(("unique", child.tag), []).append(child)


def merge_ini_files(base: Path, patch: Path, extra: Path, out_file: Path) -> None:
    """Merge three INI/TXT files with sections. Priority: map < patch < extra."""

    def read_ini(path: Path) -> dict[str, dict[str, str]]:
        data: dict[str, dict[str, str]] = {}
        if not path.exists():
            return data

        current = "__root__"
        data[current] = {}

        for raw in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue

            if line.startswith("[") and line.endswith("]"):
                current = line[1:-1].strip()
                data.setdefault(current, {})
                continue

            if "=" in line:
                k, v = line.split("=", 1)
                data.setdefault(current, {})[k.strip()] = v.strip()

        return data

    def merge_dicts(low: dict, high: dict, name: str) -> None:
        """Merge high-priority dict into low-priority dict, warn on conflict."""
        for section, kv in high.items():
            if section not in low:
                low[section] = kv.copy()
                continue

            for k, v in kv.items():
                if k in low[section] and low[section][k] != v:
                    print(f"⚠️ INI Merger Conflict: [{section}] {k} → using {name} value ({v})")
                low[section][k] = v

    if not patch.exists() and not extra.exists():
        shutil.copy(base, out_file)
        return

    base_ini = read_ini(base)
    patch_ini = read_ini(patch)
    extra_ini = read_ini(extra)

    merged = base_ini
    merge_dicts(merged, patch_ini, "patch")
    merge_dicts(merged, extra_ini, "extra")

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", encoding="utf-8", newline="\n") as f:
        if "__root__" in merged and merged["__root__"]:
            for k, v in sorted(merged["__root__"].items()):
                f.write(f"{k} = {v}\n")
            f.write("\n")

        for section in sorted(s for s in merged.keys() if s != "__root__"):
            f.write(f"[{section}]\n")
            for k, v in sorted(merged[section].items()):
                f.write(f"{k} = {v}\n")
            f.write("\n")

def merge_file_triple(base: Path, patch: Path, extra: Path, dest: Path) -> None:
    """Merge or copy directly into dest (no temp files)."""
    suffix = base.suffix or patch.suffix or extra.suffix
    exists = [p.exists() for p in (base, patch, extra)]
    if not any(exists):
        return

    dest.parent.mkdir(parents=True, exist_ok=True)

    if suffix == ".xml":
        if base.exists():
            shutil.copy(base, dest)
            
        if patch.exists():
            merge_catalog_xml(dest, patch, dest)
        if extra.exists():
            merge_catalog_xml(dest, extra, dest)
    elif suffix in [".txt", ".ini"]:
        merge_ini_files(base, patch, extra, dest)
    else:
        src = extra if extra.exists() else patch if patch.exists() else base
        shutil.copy(src, dest)


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
