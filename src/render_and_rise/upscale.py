import os
import subprocess
from pathlib import Path
from typing import Optional


def _which(cmd: str) -> Optional[str]:
    from shutil import which
    return which(cmd)


def detect_upscaler() -> str:
    """
    Finds Upscayl backend exe (upscayl-bin.exe).
    Priority:
      1) env var UPSCAYL_CLI
      2) default install path
      3) PATH
    Raises RuntimeError if not found.
    """
    env_path = os.getenv("UPSCAYL_CLI")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return str(p)

    default = Path(r"C:\Program Files\Upscayl\resources\bin\upscayl-bin.exe")
    if default.exists():
        return str(default)

    for name in ("upscayl-bin", "upscayl-bin.exe"):
        p = _which(name)
        if p:
            return p

    raise RuntimeError(
        "Upscayl backend not found.\n"
        "Expected one of:\n"
        " - Set env var UPSCAYL_CLI to: C:\\Program Files\\Upscayl\\resources\\bin\\upscayl-bin.exe\n"
        " - Or ensure upscayl-bin.exe is on PATH."
    )


def upscale_image(
    input_path: Path,
    output_path: Path,
    *,
    scale: int = 4,
    model: str = "ultrasharp-4x",
    tile_size: int = 256,
    models_dir: Optional[str] = None,
    upscaler_exe: Optional[str] = None,
) -> Path:
    """
    Upscales an image using Upscayl's backend (upscayl-bin.exe).
    """
    input_path = input_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"Input image not found: {input_path}")

    exe = upscaler_exe or detect_upscaler()

    models = (
        models_dir
        or os.getenv("UPSCAYL_MODELS_DIR")
        or r"C:\Program Files\Upscayl\resources\models"
    )

    if not Path(models).exists():
        raise FileNotFoundError(
            f"Models directory not found: {models}\n"
            "Set UPSCAYL_MODELS_DIR to your models folder if different."
        )

    cmd = [
        exe,
        "-i", str(input_path),
        "-o", str(output_path),
        "-m", str(models),
        "-s", str(scale),
        "-t", str(tile_size),
        "-n", model,
        "-f", "png",
    ]

    subprocess.check_call(cmd)

    if not output_path.exists():
        raise RuntimeError("Upscayl finished but output file was not created.")

    return output_path