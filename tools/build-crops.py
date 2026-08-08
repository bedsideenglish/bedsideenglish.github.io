#!/usr/bin/env python3
"""Cut the close-up crops the landing page uses from the full-size captures.

The page leans on two crops that are too small to read when the whole phone
screen is scaled into a 330px device frame:

  hero-checklist   the live checklist at the moment it fills in (2 of 4), taken
                   from the hero clip's own poster frame so the still and the
                   video agree
  correction-wide  one saved correction at native resolution, wide enough to be
                   the full-width payoff band

Both are straight crops - nothing is retouched, scaled up or recoloured. Re-run
after replacing either source capture:

    python3 tools/build-crops.py      # needs Pillow
"""

import pathlib

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "android" / "detail"

# (source, box, destination). Boxes are in the source capture's own pixels.
CROPS = [
    (
        ROOT / "assets" / "video" / "encounter-loop-poster.webp",
        (8, 714, 612, 930),
        OUT / "hero-checklist.webp",
    ),
    (
        ROOT / "assets" / "android" / "corrections.webp",
        (40, 492, 740, 928),
        OUT / "correction-wide.webp",
    ),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for source, box, destination in CROPS:
        with Image.open(source) as image:
            crop = image.convert("RGB").crop(box)
            crop.save(destination, "WEBP", quality=92, method=6)
        print(f"{destination.relative_to(ROOT)}  {crop.width}x{crop.height}")


if __name__ == "__main__":
    main()
