from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import numpy as np
from PIL import Image


@dataclass
class TemplateCalibration:
    template_id: str                 # "m01"
    bbox: Tuple[int, int, int, int]  # (left, top, right, bottom)
    mask_crop: np.ndarray            # bool (bh, bw) where we should overwrite pixels
    s_crop: np.ndarray               # float32 (bh, bw) shading scalar
    a_crop: np.ndarray               # float32 (bh, bw, 3) ambient RGB add


def _err(msg: str) -> RuntimeError:
    return RuntimeError(f"[mockups/calibration] {msg}")


def _load_rgb(path: Path) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    return np.array(Image.open(path).convert("RGB"), dtype=np.uint8)


def _cover_resize_crop(img_rgba: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Canva-ish: cover + center crop into (target_w, target_h)."""
    ins = img_rgba.convert("RGBA")
    tw, th = ins.size
    scale = max(target_w / tw, target_h / th)
    new_w, new_h = int(round(tw * scale)), int(round(th * scale))
    ins_resized = ins.resize((new_w, new_h), Image.LANCZOS)

    cx, cy = new_w // 2, new_h // 2
    left = max(0, cx - target_w // 2)
    top = max(0, cy - target_h // 2)
    return ins_resized.crop((left, top, left + target_w, top + target_h))


def load_or_build_calibration(templates_dir: Path, template_id: str) -> TemplateCalibration:
    """
    Requires:
      templates/mockups/<template_id>.png           (real template, NOT calibration)
      templates/mockups/calibration/<template_id>_red.png
      templates/mockups/calibration/<template_id>_green.png

    Caches:
      templates/mockups/calibration/cache/<template_id>_calib.npz
    """
    cal_dir = templates_dir / "calibration"
    red_p = cal_dir / f"{template_id}_red.png"
    green_p = cal_dir / f"{template_id}_green.png"

    cache_dir = cal_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_p = cache_dir / f"{template_id}_calib.npz"

    if cache_p.exists():
        data = np.load(cache_p)
        bbox = tuple(data["bbox"].tolist())
        return TemplateCalibration(
            template_id=template_id,
            bbox=bbox,
            mask_crop=data["mask_crop"].astype(bool),
            s_crop=data["s_crop"].astype(np.float32),
            a_crop=data["a_crop"].astype(np.float32),
        )

    red = _load_rgb(red_p)
    green = _load_rgb(green_p)

    if red.shape != green.shape:
        raise _err(f"Red/Green size mismatch for {template_id}: {red.shape} vs {green.shape}")

    h, w = red.shape[:2]

    # diff mask: where red/green differ => frame area (mostly)
    diff = np.abs(red.astype(np.int16) - green.astype(np.int16)).sum(axis=2)
    mask = diff > 30

    if mask.sum() < (h * w * 0.005):
        raise _err(f"Diff mask too small for {template_id}. Did you export true #FF0000 and #00FF00 fills?")

    ys, xs = np.where(mask)
    left, right = int(xs.min()), int(xs.max()) + 1
    top, bottom = int(ys.min()), int(ys.max()) + 1
    bbox = (left, top, right, bottom)

    # Lighting model per pixel:
    # out = s*in + a
    # Using red/green fills:
    # aR = outR_green
    # aG = outG_red
    # aB = outB_red
    # s  = (outR_red - outR_green)/255 and (outG_green - outG_red)/255 averaged
    r_red = red[..., 0].astype(np.float32)
    g_red = red[..., 1].astype(np.float32)
    b_red = red[..., 2].astype(np.float32)

    r_green = green[..., 0].astype(np.float32)
    g_green = green[..., 1].astype(np.float32)

    s1 = (r_red - r_green) / 255.0
    s2 = (g_green - g_red) / 255.0
    s = np.clip((s1 + s2) * 0.5, 0.0, 2.5).astype(np.float32)

    a = np.stack([r_green, g_red, b_red], axis=2).astype(np.float32)

    # Crop everything to bbox for speed and simplicity
    mask_crop = mask[top:bottom, left:right].astype(bool)
    s_crop = s[top:bottom, left:right].astype(np.float32)
    a_crop = a[top:bottom, left:right, :].astype(np.float32)

    np.savez_compressed(
        cache_p,
        bbox=np.array(bbox, dtype=np.int32),
        mask_crop=mask_crop.astype(np.uint8),
        s_crop=s_crop,
        a_crop=a_crop,
    )

    return TemplateCalibration(
        template_id=template_id,
        bbox=bbox,
        mask_crop=mask_crop,
        s_crop=s_crop,
        a_crop=a_crop,
    )


def render_with_calibration(templates_dir: Path, cal: TemplateCalibration, artwork_path: Path) -> Image.Image:
    """
    Simple render (NO perspective):
      - base = real template image (mXX.png)
      - insert artwork into bbox (cover+crop)
      - apply lighting (s,a) only where mask_crop is True
    """
    if not artwork_path.exists():
        raise FileNotFoundError(f"Artwork not found: {artwork_path}")

    template_png = templates_dir / f"{cal.template_id}.png"
    if not template_png.exists():
        raise FileNotFoundError(f"Template not found: {template_png}")

    base = Image.open(template_png).convert("RGBA")
    base_np = np.array(base, dtype=np.uint8)

    left, top, right, bottom = cal.bbox
    bw, bh = right - left, bottom - top

    art = Image.open(artwork_path).convert("RGBA")
    art_fit = _cover_resize_crop(art, bw, bh)
    art_rgb = np.array(art_fit.convert("RGB"), dtype=np.float32)

    out_rgb = (cal.s_crop[..., None] * art_rgb) + cal.a_crop
    out_rgb = np.clip(out_rgb, 0, 255).astype(np.uint8)

    region = base_np[top:bottom, left:right, :3]
    region[cal.mask_crop] = out_rgb[cal.mask_crop]
    base_np[top:bottom, left:right, :3] = region

    return Image.fromarray(base_np, mode="RGBA")