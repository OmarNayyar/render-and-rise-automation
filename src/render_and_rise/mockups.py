from __future__ import annotations

import random
from pathlib import Path

from PIL import Image

from .mockup_calibration import load_or_build_calibration, render_with_calibration


def _pick_first_image(folder: Path) -> Path:
    exts = (".png", ".jpg", ".jpeg", ".webp")
    imgs = sorted([p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in exts])
    if not imgs:
        raise FileNotFoundError(f"No images found in: {folder}")
    return imgs[0]


def _detect_info_slides(templates_dir: Path) -> list[Path]:
    slides = [
        templates_dir / "info_01.png",
        templates_dir / "info_02.png",
        templates_dir / "info_03.png",
    ]
    if all(p.exists() for p in slides):
        return slides
    missing = [p.name for p in slides if not p.exists()]
    raise FileNotFoundError(f"Missing info slides in {templates_dir}: {missing} (expected info_01..info_03.png)")


def _list_template_ids(templates_dir: Path) -> list[str]:
    """
    Templates are m01.png, m02.png, ... in templates_dir.
    Return ['m01','m02',...]
    """
    ids = []
    blacklist = {"m07"}  # disable tilted tile-floor template for now
    for p in templates_dir.glob("m*.png"):
        if len(p.stem) == 3 and p.stem[1:].isdigit():
            if p.stem in blacklist:
                continue
            ids.append(p.stem)
    return sorted(ids)


def _has_calibration_files(templates_dir: Path, template_id: str) -> bool:
    cal_dir = templates_dir / "calibration"
    return (cal_dir / f"{template_id}_red.png").exists() and (cal_dir / f"{template_id}_green.png").exists()


def build_all_mockups_for_product(
    product_dir: Path,
    templates_dir: Path,
    exports_subdir: str = "exports/2x3",
    out_subdir: str = "mockups/etsy/all",
) -> list[Path]:
    exports_dir = product_dir / exports_subdir
    if not exports_dir.exists():
        raise FileNotFoundError(f"Exports folder not found: {exports_dir}")

    artwork_path = _pick_first_image(exports_dir)

    out_dir = product_dir / out_subdir
    out_dir.mkdir(parents=True, exist_ok=True)

    outputs: list[Path] = []

    for tid in _list_template_ids(templates_dir):
        if not _has_calibration_files(templates_dir, tid):
            continue
        cal = load_or_build_calibration(templates_dir, tid)
        out_img = render_with_calibration(templates_dir, cal, artwork_path)
        out_path = out_dir / f"{tid}.png"
        out_img.save(out_path)
        outputs.append(out_path)

    return outputs


def build_final_etsy_set_for_product(
    product_dir: Path,
    templates_dir: Path,
    exports_subdir: str = "exports/2x3",
    out_subdir: str = "mockups/etsy",
    seed: int | None = None,
) -> list[Path]:
    if seed is not None:
        random.seed(seed)

    exports_dir = product_dir / exports_subdir
    if not exports_dir.exists():
        raise FileNotFoundError(f"Exports folder not found: {exports_dir}")

    artwork_path = _pick_first_image(exports_dir)

    out_dir = product_dir / out_subdir
    out_dir.mkdir(parents=True, exist_ok=True)

    info_slides = _detect_info_slides(templates_dir)

    templates = [t for t in _list_template_ids(templates_dir) if _has_calibration_files(templates_dir, t)]
    if "m01" not in templates:
        raise RuntimeError("m01.png must exist AND have calibration files m01_red/m01_green.")

    candidates = [t for t in templates if t != "m01"]
    if len(candidates) < 2:
        raise RuntimeError(f"Need at least 2 more calibrated templates besides m01. Found: {candidates}")

    chosen = ["m01"] + random.sample(candidates, 2)

    outputs: list[Path] = []

    for idx, tid in enumerate(chosen, start=1):
        cal = load_or_build_calibration(templates_dir, tid)
        out_img = render_with_calibration(templates_dir, cal, artwork_path)
        out_path = out_dir / f"mockup_{idx:02d}.png"
        out_img.save(out_path)
        outputs.append(out_path)

    for src in info_slides:
        dst = out_dir / src.name
        Image.open(src).save(dst)
        outputs.append(dst)

    return outputs


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    product_dir = root / "products" / "RR-0001_raccoon-bath"
    templates_dir = root / "factory" / "templates" / "mockups"

    print("Generating ALL mockups...")
    outs_all = build_all_mockups_for_product(product_dir, templates_dir)
    for p in outs_all:
        print(" -", p)

    print("\nGenerating FINAL 3+3 set...")
    outs_final = build_final_etsy_set_for_product(product_dir, templates_dir, seed=1337)
    for p in outs_final:
        print(" -", p)
