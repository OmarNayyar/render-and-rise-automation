import argparse
from pathlib import Path

import cv2
import numpy as np


RATIOS = {
    "1x1": (1, 1),
    "2x3": (2, 3),
    "3x4": (3, 4),
    "4x5": (4, 5),
    "11x14": (11, 14),
    "ISO_A": (1, 1.41421356237),  # sqrt(2)
}


def load_rgb(path: Path) -> np.ndarray:
    img = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Failed to read image: {path}")
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def save_rgb(path: Path, rgb: np.ndarray):
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    ext = path.suffix.lower()
    if ext not in [".png", ".jpg", ".jpeg"]:
        raise ValueError("Output must be .png or .jpg")
    params = []
    if ext in [".jpg", ".jpeg"]:
        params = [int(cv2.IMWRITE_JPEG_QUALITY), 95]
    ok, buf = cv2.imencode(ext, bgr, params)
    if not ok:
        raise ValueError(f"Failed to encode: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    buf.tofile(str(path))


def saliency_center(rgb: np.ndarray) -> tuple[int, int]:
    # “Good enough” saliency: edge + contrast weighted center of mass
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (0, 0), 1.2)

    edges = cv2.Canny(gray, 80, 160).astype(np.float32)
    lap = cv2.Laplacian(gray, cv2.CV_32F)
    lap = np.abs(lap)

    sal = edges + 0.6 * lap
    sal = cv2.GaussianBlur(sal, (0, 0), 3.0)

    s = sal.sum()
    h, w = sal.shape
    if s < 1e-6:
        return w // 2, h // 2

    ys, xs = np.mgrid[0:h, 0:w]
    cx = int((xs * sal).sum() / s)
    cy = int((ys * sal).sum() / s)
    return cx, cy


def crop_to_ratio(rgb: np.ndarray, ratio_w: float, ratio_h: float) -> np.ndarray:
    h, w = rgb.shape[:2]
    target = ratio_w / ratio_h
    cur = w / h

    cx, cy = saliency_center(rgb)

    if cur > target:
        # too wide -> reduce width
        new_w = int(h * target)
        new_h = h
    else:
        # too tall -> reduce height
        new_w = w
        new_h = int(w / target)

    # center crop around (cx, cy), clamp to image bounds
    x1 = max(0, min(w - new_w, cx - new_w // 2))
    y1 = max(0, min(h - new_h, cy - new_h // 2))
    x2 = x1 + new_w
    y2 = y1 + new_h

    return rgb[y1:y2, x1:x2].copy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", required=True)
    ap.add_argument("--format", default="png", choices=["png", "jpg"])
    ap.add_argument("--max_px", type=int, default=0, help="Optional: limit longest side (0 = no limit)")
    ap.add_argument("--base_name", default="",
                    help="Optional: filename base for exports (no extension). If blank, uses product.")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[2]
    product_dir = root / "products" / args.product

    master_path = product_dir / "master" / "master.png"
    if not master_path.exists():
        # allow jpg master too
        master_path = product_dir / "master" / "master.jpg"
    if not master_path.exists():
        raise FileNotFoundError("master.png/master.jpg not found in product/master/")

    rgb = load_rgb(master_path)

    exports_dir = product_dir / "exports"
    for key, (rw, rh) in RATIOS.items():
        cropped = crop_to_ratio(rgb, float(rw), float(rh))

        # optional downscale if max_px set
        if args.max_px and args.max_px > 0:
            h, w = cropped.shape[:2]
            longest = max(h, w)
            if longest > args.max_px:
                scale = args.max_px / longest
                new_w = int(w * scale)
                new_h = int(h * scale)
                cropped = cv2.resize(cropped, (new_w, new_h), interpolation=cv2.INTER_AREA)

        base = (args.base_name or args.product).strip()

        suffix_map = {
            "1x1": "1_1",
            "2x3": "2_3",
            "3x4": "3_4",
            "4x5": "4_5",
            "11x14": "11_14",
            "ISO_A": "ISO_A",
        }

        suffix = suffix_map.get(key, key)
        out_path = exports_dir / key / f"{base}_{suffix}.{args.format}"
        save_rgb(out_path, cropped)

        print(f"OK: {key} -> {out_path.relative_to(product_dir)} ({cropped.shape[1]}x{cropped.shape[0]})")

    print("DONE: exports generated")


if __name__ == "__main__":
    main()