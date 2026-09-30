"""Géométrie de la feuille modèle (en mm) et rendu de cette feuille en image.

Le même module sert à générer le PDF à imprimer et à retrouver les cases
lors de l'analyse du scan : les deux ne peuvent donc pas se désynchroniser.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

# --- Page A4 ---------------------------------------------------------------
PAGE_W, PAGE_H = 210.0, 297.0

# Marqueurs de coin (carrés noirs pleins) : centres et taille
MARKERS = [(12.0, 12.0), (198.0, 12.0), (198.0, 285.0), (12.0, 285.0)]  # tl, tr, br, bl
MARK_SIZE = 8.0

# Marque d'orientation + code de page (bits) le long du haut de la page
ORIENT = (24.0, 12.0)
ORIENT_SIZE = 4.0
CODE_X0, CODE_DX, CODE_BITS = 100.0, 7.0, 7  # bit 0 toujours plein, puis 6 bits de n° de page
CODE_Y, CODE_SIZE = 12.0, 4.0

# --- Grille de cases -------------------------------------------------------
COLS, ROWS = 10, 10
CELL_W, CELL_H = 18.0, 24.0
LABEL_H = 4.0                       # bandeau d'étiquette au-dessus de la zone d'écriture
WRITE_H = CELL_H - LABEL_H          # 20 mm
GRID_X, GRID_Y = 15.0, 22.0
PER_PAGE = COLS * ROWS

# Lignes-guides dans la zone d'écriture (mm depuis le haut de la zone)
ASC_Y, XH_Y, BASE_Y = 2.5, 8.0, 14.5
CROP_INSET = 0.7                    # on ignore le bord de case à l'extraction

# Couleur des guides : assez claire pour disparaître au seuillage
GUIDE = (170, 200, 235)
GUIDE_DARK = (120, 160, 215)


def cell_origin(row: int, col: int) -> tuple[float, float]:
    """Coin haut-gauche de la ZONE D'ÉCRITURE de la case (mm)."""
    return GRID_X + col * CELL_W, GRID_Y + row * CELL_H + LABEL_H


# --- Jeux de caractères ----------------------------------------------------
CHARSETS = {
    "lower": ("Minuscules", "abcdefghijklmnopqrstuvwxyz"),
    "upper": ("Majuscules", "ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    "digits": ("Chiffres", "0123456789"),
    "punct": ("Ponctuation", ".,;:!?'\"()-–/&@#%+=*_«»€$"),
    "fr_lower": ("Accents minuscules", "àâäçéèêëîïôöùûüÿœæ"),
    "fr_upper": ("Accents majuscules", "ÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸŒÆ"),
}
DEFAULT_GROUPS = ["lower", "upper", "digits", "punct", "fr_lower"]


@dataclass(frozen=True)
class Item:
    index: int
    char: str
    variant: int   # 0-based
    page: int      # 1-based
    row: int
    col: int


def build_items(groups: list[str], variants: int) -> list[Item]:
    chars: list[str] = []
    for g in groups:
        if g in CHARSETS:
            for c in CHARSETS[g][1]:
                if c not in chars:
                    chars.append(c)
    items: list[Item] = []
    i = 0
    for c in chars:
        for v in range(variants):
            page, pos = divmod(i, PER_PAGE)
            row, col = divmod(pos, COLS)
            items.append(Item(i, c, v, page + 1, row, col))
            i += 1
    return items


def page_count(items: list[Item]) -> int:
    return items[-1].page if items else 0


# --- Rendu -----------------------------------------------------------------
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _label_font(px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, px)
            except OSError:
                continue
    return ImageFont.load_default(px)


def page_code_bits(page: int) -> list[int]:
    return [1] + [(page >> (5 - i)) & 1 for i in range(6)]


def render_page(items: list[Item], page: int, total: int, dpi: int = 300) -> Image.Image:
    k = dpi / 25.4
    img = Image.new("RGB", (round(PAGE_W * k), round(PAGE_H * k)), "white")
    d = ImageDraw.Draw(img)

    def box(cx, cy, size):
        h = size / 2
        return [round((cx - h) * k), round((cy - h) * k), round((cx + h) * k) - 1, round((cy + h) * k) - 1]

    for cx, cy in MARKERS:
        d.rectangle(box(cx, cy, MARK_SIZE), fill="black")
    d.rectangle(box(*ORIENT, ORIENT_SIZE), fill="black")
    for i, bit in enumerate(page_code_bits(page)):
        b = box(CODE_X0 + CODE_DX * i, CODE_Y, CODE_SIZE)
        if bit:
            d.rectangle(b, fill="black")
        else:
            d.rectangle(b, outline=GUIDE_DARK, width=2)

    small, big = _label_font(round(3.0 * k)), _label_font(round(4.2 * k))
    d.text((32 * k, 12 * k), f"Page {page}/{total}", fill=(90, 90, 90), font=big, anchor="lm")
    d.text((PAGE_W / 2 * k, 273 * k),
           "Écris chaque caractère dans sa case, en posant le bas des lettres sur la ligne pleine.",
           fill=(90, 90, 90), font=small, anchor="mm")
    d.text((PAGE_W / 2 * k, 279 * k),
           "Ne touche pas aux bords. Varie un peu ton écriture d'une case à l'autre : c'est le but.",
           fill=(90, 90, 90), font=small, anchor="mm")

    for it in items:
        if it.page != page:
            continue
        x0, y0 = cell_origin(it.row, it.col)
        # étiquette (hors zone d'extraction)
        d.text(((x0 + 1.2) * k, (y0 - LABEL_H / 2) * k), it.char, fill=(40, 40, 40), font=big, anchor="lm")
        d.text(((x0 + CELL_W - 1.2) * k, (y0 - LABEL_H / 2) * k), str(it.variant + 1),
               fill=(140, 140, 140), font=small, anchor="rm")
        d.rectangle([round(x0 * k), round((y0 - LABEL_H) * k), round((x0 + CELL_W) * k), round((y0 + WRITE_H) * k)],
                    outline=GUIDE, width=2)
        d.line([(round(x0 * k), round(y0 * k)), (round((x0 + CELL_W) * k), round(y0 * k))], fill=GUIDE, width=2)
        # lignes-guides
        by = round((y0 + BASE_Y) * k)
        d.line([(round((x0 + 0.5) * k), by), (round((x0 + CELL_W - 0.5) * k), by)], fill=GUIDE_DARK, width=3)
        for gy in (ASC_Y, XH_Y):
            yy = (y0 + gy) * k
            x = (x0 + 0.5) * k
            while x < (x0 + CELL_W - 0.5) * k:
                d.line([(round(x), round(yy)), (round(x + 1.2 * k), round(yy))], fill=GUIDE, width=2)
                x += 2.4 * k
    return img


def render_pdf(items: list[Item], path: str, dpi: int = 300) -> None:
    total = page_count(items)
    pages = [render_page(items, p, total, dpi) for p in range(1, total + 1)]
    pages[0].save(path, "PDF", resolution=dpi, save_all=True, append_images=pages[1:])
