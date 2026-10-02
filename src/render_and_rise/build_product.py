import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--product", required=True, help="Product folder name inside /products (e.g., RR-DEMO-001)")
    parser.add_argument("--input", required=True, help="Path to master/upscaled image (png/jpg)")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    product_dir = root / "products" / args.product

    # Day 2: one-button flow -> auto-create product folder if it doesn't exist
    product_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input image not found: {input_path}")

    master_dir = product_dir / "master"
    master_dir.mkdir(parents=True, exist_ok=True)

    # Copy input into master folder as a standard name
    # Keep extension sane so downstream readers don't choke.
    ext = input_path.suffix.lower()
    if ext in [".jpg", ".jpeg"]:
        out_master = master_dir / "master.jpg"
    else:
        out_master = master_dir / "master.png"
    out_master.write_bytes(input_path.read_bytes())

    print("OK: staged master image")
    print(f"Product: {product_dir.name}")
    print(f"Master:  {out_master}")

if __name__ == "__main__":
    main()
