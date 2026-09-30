"""Fabrique de fausses photos de feuilles remplies « à la main » pour tester la chaîne complète."""
import math
import random
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fontcreator import layout as L  # noqa: E402

HAND = "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf"


def fill_page(page: int, items, total: int, dpi=300, seed=1) -> Image.Image:
    rnd = random.Random(seed + page)
    img = L.render_page(items, page, total, dpi)
    k = dpi / 25.4
    font = ImageFont.truetype(HAND, round(15.5 * k))  # ~ hauteur de capitale de 12 mm
    for it in items:
        if it.page != page:
            continue
        x0, y0 = L.cell_origin(it.row, it.col)
        layer = Image.new("L", (round(L.CELL_W * 2 * k), round(40 * k)), 0)
        ld = ImageDraw.Draw(layer)
        ox, oy = round(L.CELL_W * k), round(20 * k)
        ld.text((ox, oy), it.char, fill=255, font=font, anchor="ls")
        layer = layer.rotate(rnd.uniform(-5, 5), center=(ox, oy), resample=Image.BICUBIC)
        # placement : baseline de la case + petit décalage aléatoire
        dx = rnd.uniform(1.0, 6.0)
        dy = rnd.uniform(-0.5, 0.5)
        px = round((x0 + dx) * k - ox)
        py = round((y0 + L.BASE_Y + dy) * k - oy)
        ink = Image.new("RGB", layer.size, (25, 25, 60))
        img.paste(ink, (px, py), layer)
    return img


def photograph(img: Image.Image, rot90=0, seed=3) -> np.ndarray:
    rnd = random.Random(seed)
    a = np.array(img)[:, :, ::-1].copy()
    h, w = a.shape[:2]
    out_w, out_h = 2400, 3200
    m = 200
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[m + rnd.uniform(0, 60), m + rnd.uniform(0, 80)],
                      [out_w - m - rnd.uniform(0, 60), m + rnd.uniform(0, 40)],
                      [out_w - m - rnd.uniform(0, 80), out_h - m - rnd.uniform(0, 60)],
                      [m + rnd.uniform(0, 60), out_h - m - rnd.uniform(0, 30)]])
    M = cv2.getPerspectiveTransform(src, dst)
    bg = np.full((out_h, out_w, 3), (60, 70, 85), np.uint8)
    warped = cv2.warpPerspective(a, M, (out_w, out_h), borderValue=(60, 70, 85))
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), M, (out_w, out_h))
    photo = np.where(mask[..., None] > 0, warped, bg).astype(np.float32)
    # éclairage inégal + bruit + flou
    yy, xx = np.mgrid[0:out_h, 0:out_w].astype(np.float32)
    shade = 0.75 + 0.25 * (xx / out_w) * 0.8 + 0.15 * (1 - yy / out_h)
    photo *= shade[..., None]
    photo += np.random.default_rng(seed).normal(0, 4, photo.shape)
    photo = cv2.GaussianBlur(np.clip(photo, 0, 255).astype(np.uint8), (0, 0), 1.2)
    return np.rot90(photo, rot90).copy()


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "work/fake")
    out.mkdir(parents=True, exist_ok=True)
    from fontcreator import project
    items = project.load_items()
    total = L.page_count(items)
    for p in range(1, total + 1):
        filled = fill_page(p, items, total)
        rot = 2 if p == 2 else 0  # une page à l'envers pour tester l'orientation
        cv2.imwrite(str(out / f"scan_{p}.jpg"), photograph(filled, rot, seed=p), [cv2.IMWRITE_JPEG_QUALITY, 88])
        print("écrit", out / f"scan_{p}.jpg")
