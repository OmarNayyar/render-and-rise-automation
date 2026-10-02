from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Tuple

import dropbox
from dropbox.files import WriteMode
from dropbox.exceptions import ApiError
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _env(name: str) -> str:
    v = (os.getenv(name) or "").strip()
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v


def dbx_client() -> dropbox.Dropbox:
    """
    Uses refresh-token OAuth (recommended).
    Requires:
      DROPBOX_REFRESH_TOKEN
      DROPBOX_APP_KEY
      DROPBOX_APP_SECRET
    """
    refresh_token = _env("DROPBOX_REFRESH_TOKEN")
    app_key = _env("DROPBOX_APP_KEY")
    app_secret = _env("DROPBOX_APP_SECRET")

    return dropbox.Dropbox(
        oauth2_refresh_token=refresh_token,
        app_key=app_key,
        app_secret=app_secret,
    )


def ensure_folder(dbx: dropbox.Dropbox, folder_path: str) -> None:
    """
    Idempotent folder creation.
    folder_path must be Dropbox-style: "/RenderandRise/..."
    """
    try:
        dbx.files_create_folder_v2(folder_path)
    except ApiError as e:
        # ignore "folder already exists"
        if getattr(e.error, "is_path", lambda: False)():
            pe = e.error.get_path()
            if getattr(pe, "is_conflict", lambda: False)():
                return
        raise


def _iter_files(local_root: Path) -> Iterable[Path]:
    for p in local_root.rglob("*"):
        if p.is_file():
            yield p


def upload_file(
    dbx: dropbox.Dropbox,
    local_file: Path,
    dropbox_path: str,
    overwrite: bool = True,
) -> None:
    mode = WriteMode.overwrite if overwrite else WriteMode.add
    with local_file.open("rb") as f:
        dbx.files_upload(f.read(), dropbox_path, mode=mode, mute=True)


def upload_tree(
    dbx: dropbox.Dropbox,
    local_root: Path,
    dropbox_root: str,
    overwrite: bool = True,
) -> None:
    """
    Uploads all files under local_root to dropbox_root preserving relative paths.
    """
    local_root = local_root.resolve()
    ensure_folder(dbx, dropbox_root)

    for lf in _iter_files(local_root):
        rel = lf.relative_to(local_root).as_posix()
        dp = f"{dropbox_root.rstrip('/')}/{rel}"
        parent = "/" + "/".join(dp.strip("/").split("/")[:-1])
        if parent and parent != "/":
            ensure_folder(dbx, parent)
        upload_file(dbx, lf, dp, overwrite=overwrite)


def get_or_create_share_link(dbx: dropbox.Dropbox, dropbox_path: str) -> str:
    """
    Returns a share link for a Dropbox folder/path.
    """
    try:
        res = dbx.sharing_create_shared_link_with_settings(dropbox_path)
        return res.url
    except ApiError:
        # If already exists, list and return first
        listing = dbx.sharing_list_shared_links(path=dropbox_path, direct_only=True)
        if listing.links:
            return listing.links[0].url
        raise


def normalize_share_link(url: str, dl: bool = False) -> str:
    """
    Dropbox links come in several forms. This normalizes to dl=0/1.
    """
    if "dropbox.com" not in url:
        return url

    if "?" in url:
        base, qs = url.split("?", 1)
    else:
        base, qs = url, ""

    # remove existing dl/raw params
    parts = [p for p in qs.split("&") if p and not p.startswith("dl=") and not p.startswith("raw=")]
    parts.append(f"dl={'1' if dl else '0'}")
    return base + "?" + "&".join(parts)
