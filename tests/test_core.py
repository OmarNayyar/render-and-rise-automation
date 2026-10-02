from __future__ import annotations

import numpy as np

from render_and_rise.crop_exports import crop_to_ratio
from render_and_rise.dropbox_ops import normalize_share_link


def test_crop_to_ratio_preserves_requested_shape() -> None:
    image = np.zeros((600, 900, 3), dtype=np.uint8)

    cropped = crop_to_ratio(image, 2, 3)

    assert cropped.shape[:2] == (600, 400)


def test_crop_to_ratio_handles_square_export() -> None:
    image = np.zeros((600, 900, 3), dtype=np.uint8)

    cropped = crop_to_ratio(image, 1, 1)

    assert cropped.shape[:2] == (600, 600)


def test_dropbox_link_normalization_replaces_download_flags() -> None:
    source = "https://www.dropbox.com/scl/fo/example?rlkey=placeholder&dl=1"

    normalized = normalize_share_link(source, dl=False)

    assert normalized.endswith("rlkey=placeholder&dl=0")
    assert "dl=1" not in normalized
