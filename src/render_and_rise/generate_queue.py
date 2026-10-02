from __future__ import annotations

import csv
import os
import random
import re
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
QUEUE_CSV = Path(os.getenv("RR_QUEUE_CSV", REPO_ROOT / "data" / "products_queue.csv")).expanduser().resolve()

CORE_FIELDS = ["product_id", "title", "status", "notes", "master_path"]
NEW_FIELDS = ["animal", "activity", "scene", "room", "room_tag", "style_variant", "prompt", "negative_prompt"]
ALL_FIELDS = CORE_FIELDS + NEW_FIELDS

STYLE_VARIANT = "bw_hyperreal_photo_v1"

# ---------------------------
# Prompt bank (high-intent rooms + variety)
# ---------------------------
ANIMALS = [
    "raccoon", "otter", "fox", "cat", "dog", "bunny", "bear", "panda",
    "squirrel", "hedgehog", "penguin", "frog", "duck", "owl", "koala",
]

ROOM_SCENES: Dict[str, List[str]] = {
    "bathroom": ["spa bathroom", "vintage bathroom", "modern bathroom", "cozy bathroom"],
    "kitchen": ["cottage kitchen", "modern kitchen", "rustic kitchen", "minimal kitchen"],
    "laundry_room": ["laundry room", "utility room", "clean laundry nook"],
    "nursery": ["nursery", "kids room", "playroom"],
    "home_office": ["home office", "reading nook", "study corner"],
    "living_room": ["living room", "neutral living room", "boho living room"],
}

ROOM_TAGS: Dict[str, str] = {
    "bathroom": "bathroom wall art",
    "kitchen": "kitchen wall art",
    "laundry_room": "laundry room decor",
    "nursery": "nursery wall art",
    "home_office": "office wall decor",
    "living_room": "living room wall art",
}

ACTIVITIES: Dict[str, List[str]] = {
    "bathroom": [
        "taking a bubble bath", "wearing a towel turban with cucumber slices on its eyes",
        "doing a face mask spa routine", "brushing teeth at the sink",
        "relaxing by candlelight", "holding a rubber duck in the bath",
    ],
    "kitchen": [
        "baking cookies on a tray", "making pancakes", "brewing coffee with a french press",
        "cooking pasta", "chopping vegetables on a cutting board",
        "washing dishes at the sink", "sneaking a snack from an open fridge at midnight",
    ],
    "laundry_room": [
        "folding laundry", "sorting socks", "holding a laundry basket",
        "hanging clothes on a line", "waiting beside a washing machine",
    ],
    "nursery": [
        "reading a bedtime story", "playing with wooden blocks", "holding a teddy bear",
        "stacking toy rings", "rocking gently in a chair",
    ],
    "home_office": [
        "typing on a laptop", "writing notes in a notebook", "studying with a stack of books",
        "sipping tea while working", "organizing a desk with stationery",
    ],
    "living_room": [
        "cozy on a couch under a blanket", "watering a houseplant",
        "listening to music with headphones", "painting at a small easel",
        "napping by a window with soft light",
    ],
}

# Photographic vibe controls (keeps outputs varied but on-style)
LIGHTING = [
    "soft diffused window light", "moody low-key lighting", "gentle studio lighting",
    "warm lamp light (rendered in monochrome)", "cinematic lighting with soft shadows",
]
LENS = [
    "DSLR photo, 50mm lens", "DSLR photo, 85mm lens portrait", "cinematic photo, shallow depth of field",
]
COMPOSITION = [
    "centered subject, clean composition", "rule-of-thirds composition, clean background",
    "tight portrait framing, minimal clutter", "balanced composition, subtle background detail",
]

# Strong negatives to prevent sketchy/cartoon outputs
NEGATIVE = (
    "drawing, sketch, pencil, illustration, cartoon, anime, painting, watercolor, line art, CGI, 3D render, "
    "text, watermark, logo, signature, border, frame, collage, "
    "extra limbs, extra fingers, deformed, disfigured, mutated, blurry, lowres, "
    "oversaturated, color, chromatic aberration, harsh noise, messy clutter, gore, nsfw"
)


# ---------------------------
# Helpers
# ---------------------------
def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s


def read_rows(path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    if not path.exists():
        return [], ALL_FIELDS

    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or ALL_FIELDS
        rows = [dict(r) for r in reader]
    return rows, list(fieldnames)


def write_rows(path: Path, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    # Ensure required fields exist in header
    for f in ALL_FIELDS:
        if f not in fieldnames:
            fieldnames.append(f)

    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def next_rr_number(existing_ids: List[str]) -> int:
    nums = []
    for pid in existing_ids:
        m = re.match(r"RR-(\d{4})_", pid)
        if m:
            nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else 1


def normalize_activity_for_slug(activity: str) -> str:
    # keep slugs short and consistent
    s = activity.lower()
    replacements = [
        ("taking a ", ""),
        ("wearing a ", ""),
        ("doing a ", ""),
        ("making ", ""),
        ("brewing ", ""),
        ("holding a ", "holding "),
        ("with a ", "with "),
        ("at the ", "at "),
        ("beside a ", "beside "),
        ("under a ", "under "),
    ]
    for a, b in replacements:
        s = s.replace(a, b)
    s = s.strip()
    # shorten common phrases
    s = s.replace("french press", "coffee")
    s = s.replace("washing machine", "washer")
    s = s.replace("bubble bath", "bath")
    s = s.replace("bedtime story", "story")
    return s


def build_prompt(animal: str, activity: str, scene: str, room: str) -> str:
    lighting = random.choice(LIGHTING)
    lens = random.choice(LENS)
    comp = random.choice(COMPOSITION)
    room_tag = ROOM_TAGS[room]

    # Photoreal, monochrome, print-ready portrait
    return (
        f"Ultra photorealistic {lens}. "
        f"Monochrome black-and-white photo (not an illustration). "
        f"A cute {animal} {activity} in a {scene}. "
        f"Realistic fur texture, natural anatomy, lifelike whiskers/eyes, subtle film-like grain. "
        f"{lighting}. {comp}. "
        f"Clean background with minimal props, high-end home decor aesthetic for {room_tag}. "
        f"2:3 portrait orientation, print-ready, sharp focus on subject, soft background bokeh. "
        f"No text, no watermark, no border, no frame."
    )


def generate_batch(n: int = 30, seed: int | None = None) -> None:
    if seed is not None:
        random.seed(seed)

    rows, fieldnames = read_rows(QUEUE_CSV)
    existing_ids = [r.get("product_id", "") for r in rows if r.get("product_id")]
    rr = next_rr_number(existing_ids)
    used = set(existing_ids)

    for _ in range(n):
        room = random.choice(list(ROOM_SCENES.keys()))
        animal = random.choice(ANIMALS)
        activity = random.choice(ACTIVITIES[room])
        scene = random.choice(ROOM_SCENES[room])

        animal_s = slugify(animal)
        activity_s = slugify(normalize_activity_for_slug(activity))
        scene_s = slugify(scene)

        base_slug = f"{animal_s}-{activity_s}_{scene_s}"
        base_slug = base_slug[:60]

        product_id = f"RR-{rr:04d}_{base_slug}"
        while product_id in used:
            rr += 1
            product_id = f"RR-{rr:04d}_{base_slug}"

        used.add(product_id)

        prompt = build_prompt(animal, activity, scene, room)
        room_tag = ROOM_TAGS[room]

        rows.append({
            "product_id": product_id,
            "title": product_id,      # later you’ll overwrite with Etsy SEO title
            "status": "NEW",
            "notes": "",
            "master_path": "",
            "animal": animal,
            "activity": activity,
            "scene": scene,
            "room": room,
            "room_tag": room_tag,
            "style_variant": STYLE_VARIANT,
            "prompt": prompt,
            "negative_prompt": NEGATIVE,
        })

        rr += 1

    write_rows(QUEUE_CSV, rows, fieldnames)
    print(f"Added {n} rows to {QUEUE_CSV}")


if __name__ == "__main__":
    generate_batch(n=30, seed=1337)
