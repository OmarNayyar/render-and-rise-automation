from __future__ import annotations

import re
import argparse
import subprocess
from pathlib import Path
from typing import Tuple

from .dropbox_ops import (
    dbx_client,
    ensure_folder,
    upload_tree,
    upload_file,
    get_or_create_share_link,
    normalize_share_link,
)
from .delivery_pdf import make_delivery_pdf


def repo_root() -> Path:
    # This file is src/render_and_rise/run_pipeline.py -> repository root is 2 levels up.
    return Path(__file__).resolve().parents[2]


def run_py(script_rel: str, args_list: list[str]) -> None:
    root = repo_root()
    script_path = root / script_rel
    if not script_path.exists():
        raise FileNotFoundError(f"Missing script: {script_path}")

    cmd = [str(Path(subprocess.__file__).parent.parent / "python.exe")]  # best-effort; overridden below
    # Use current interpreter (works inside venv)
    cmd = [subprocess.sys.executable, str(script_path)] + args_list

    print("RUN:", " ".join(cmd))
    subprocess.check_call(cmd)


def build_exports(product: str, title: str, master_path: Path) -> Path:
    """
    Runs:
      build_product.py (stage master.png under product/master/)
      crop_exports.py (generate exports to product/exports/)
    Returns path to exports folder.
    """
    root = repo_root()
    products_dir = root / "products"
    product_dir = products_dir / product
    product_dir.mkdir(parents=True, exist_ok=True)

    run_py(
        "src/render_and_rise/build_product.py",
        ["--product", product, "--input", str(master_path)],
    )

    run_py(
        "src/render_and_rise/crop_exports.py",
        ["--product", product, "--base_name", title, "--format", "jpg"],
    )

    exports_dir = product_dir / "exports"
    if not exports_dir.exists():
        raise RuntimeError("Exports folder not created. crop_exports.py likely failed.")
    return exports_dir


def publish_to_dropbox(product: str, title: str) -> Tuple[str, str]:
    """
    Uploads the CONTENTS of:
      products/<product>/exports  -> /RenderandRise/<clean_title_folder>/

    The Dropbox folder will contain exactly:
      1x1/, 2x3/, 3x4/, 4x5/, 11x14/, ISO_A/, README-HowToPrint.pdf

    Creates share link for the product folder (view-only link normalized dl=0).
    Returns: (dropbox_folder, share_link)
    """
    root = repo_root()
    product_dir = root / "products" / product
    exports_dir = product_dir / "exports"

    if not exports_dir.exists():
        raise FileNotFoundError(f"Missing exports folder: {exports_dir}")

    dbx = dbx_client()

    base = "/RenderandRise"
    ensure_folder(dbx, base)

    # --- CLEAN folder name for customers ---
    # Prefer the passed-in title (should be human-friendly), fallback to product.
    # Strip RR-000x prefix if present.
    clean = re.sub(r"^RR-\d{4}[_\-\s]*", "", title, flags=re.IGNORECASE).strip()
    clean = re.sub(r"[^A-Za-z0-9\s\-\_]", "", clean).strip()
    clean = re.sub(r"\s+", " ", clean).strip()

    if not clean:
        clean = "Your Downloads"

    # Dropbox folder name (nice, not RR-coded)
    product_root = f"{base}/{clean}"

    ensure_folder(dbx, product_root)

    # --- Upload exports CONTENTS directly into product_root ---
    # Upload each aspect ratio folder + README directly.
    for p in exports_dir.iterdir():
        if p.is_dir():
            upload_tree(dbx, p, f"{product_root}/{p.name}", overwrite=True)
        elif p.is_file() and p.name.lower().endswith(".pdf"):
            upload_file(dbx, p, f"{product_root}/{p.name}", overwrite=True)

    share = get_or_create_share_link(dbx, product_root)
    share = normalize_share_link(share, dl=False)
    return product_root, share

def generate_and_upload_delivery_pdf(product: str, title: str, share_link: str) -> Path:
    """
    Creates delivery PDF locally, then uploads it to Dropbox delivery folder.
    """
    pdf_path = make_delivery_pdf(product=product, title=title, share_link=share_link)

    dbx = dbx_client()
    product_root = f"/RenderandRise/{product}"
    delivery_root = f"{product_root}/delivery"
    ensure_folder(dbx, "/RenderandRise")
    ensure_folder(dbx, product_root)
    ensure_folder(dbx, delivery_root)

    dropbox_pdf_path = f"{delivery_root}/{pdf_path.name}"
    upload_file(dbx, pdf_path, dropbox_pdf_path, overwrite=True)

    return pdf_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--master", required=True, help="Path to upscaled master image")
    args = ap.parse_args()

    product = args.product
    title = args.title
    master_path = Path(args.master).resolve()

    if not master_path.exists():
        raise FileNotFoundError(master_path)

    print("Building exports...")
    build_exports(product, title, master_path)

    print("Uploading exports to Dropbox...")
    _, share_link = publish_to_dropbox(product, title)

    print("Generating + uploading delivery PDF...")
    pdf_path = generate_and_upload_delivery_pdf(product, title, share_link)

    print("\nDONE")
    print("Share link:", share_link)
    print("Delivery PDF:", pdf_path)


if __name__ == "__main__":
    main()
