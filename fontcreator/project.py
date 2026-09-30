"""État du projet (dossier work/) : modèle imprimé, pages scannées, extraction, construction."""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from . import build as B
from . import layout as L
from . import scan

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
PAGES = WORK / "pages"
OUT = WORK / "out"
for d in (PAGES, OUT):
    d.mkdir(parents=True, exist_ok=True)

_page_cache: dict[int, np.ndarray] = {}
_trace_cache: dict[tuple, object] = {}


# --- modèle ----------------------------------------------------------------
def save_spec(groups: list[str], variants: int) -> list[L.Item]:
    groups = [g for g in groups if g in L.CHARSETS] or list(L.DEFAULT_GROUPS)
    variants = max(1, min(8, int(variants)))
    new = {"groups": groups, "variants": variants}
    if load_spec() != new:
        reset_pages()  # les cases ne correspondent plus à l'ancien modèle
    (WORK / "spec.json").write_text(json.dumps(new))
    return load_items()


def load_spec() -> dict:
    p = WORK / "spec.json"
    if p.exists():
        return json.loads(p.read_text())
    return {"groups": list(L.DEFAULT_GROUPS), "variants": 3}


def load_items() -> list[L.Item]:
    spec = load_spec()
    return L.build_items(spec["groups"], spec["variants"])


def make_pdf() -> Path:
    items = load_items()
    path = OUT / "feuille-modele.pdf"
    L.render_pdf(items, str(path))
    return path


# --- scans -----------------------------------------------------------------
def ingest(data: bytes) -> dict:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise scan.ScanError("Image illisible (formats acceptés : JPG, PNG, TIFF).")
    page, gray = scan.rectify(img)
    total = L.page_count(load_items())
    if page > total:
        raise scan.ScanError(f"Cette feuille est la page {page} mais le modèle actuel n'en a que {total}. "
                             "Le modèle a-t-il été modifié depuis l'impression ?")
    cv2.imwrite(str(PAGES / f"page_{page}.png"), gray)
    _page_cache.pop(page, None)
    _trace_cache.clear()
    return {"page": page, "total": total}


def pages_present() -> list[int]:
    return sorted(int(p.stem.split("_")[1]) for p in PAGES.glob("page_*.png"))


def reset_pages() -> None:
    for p in PAGES.glob("page_*.png"):
        p.unlink()
    _page_cache.clear()
    _trace_cache.clear()


def _page(n: int):
    if n not in _page_cache:
        f = PAGES / f"page_{n}.png"
        if not f.exists():
            return None
        _page_cache[n] = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
    return _page_cache[n]


def item_crop(it: L.Item):
    pg = _page(it.page)
    if pg is None:
        return None
    return scan.cell_crop(pg, it.row, it.col)


def status(threshold: int) -> dict:
    items = load_items()
    out = []
    for it in items:
        c = item_crop(it)
        ink = bool(c is not None and scan.has_ink(scan.ink_mask(c[0], threshold)))
        out.append({"i": it.index, "ch": it.char, "v": it.variant, "page": it.page,
                    "scanned": c is not None, "ink": ink})
    return {"items": out, "pages": pages_present(), "total": L.page_count(items), "spec": load_spec()}


def cell_png(i: int, threshold: int) -> bytes:
    it = load_items()[i]
    c = item_crop(it)
    if c is None:
        raise KeyError("page non scannée")
    crop, base = c
    mask = scan.ink_mask(crop, threshold)
    img = np.where(mask, 0, 255).astype(np.uint8)
    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    y = int(base)
    img[y:y + 1, :] = (235, 200, 160)  # ligne de base en bleu clair
    img = cv2.resize(img, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    return cv2.imencode(".png", img)[1].tobytes()


# --- construction ----------------------------------------------------------
def build(s: B.Settings) -> dict:
    items = load_items()
    per_char: dict[str, list] = {}
    excluded = set(s.excluded)
    for it in items:
        if it.index in excluded:
            continue
        c = item_crop(it)
        if c is None:
            continue
        key = (it.index, s.threshold, s.size, s.smooth)
        if key not in _trace_cache:
            _trace_cache[key] = B.trace_glyph(c[0], c[1], s)
        val = _trace_cache[key]
        if val:
            per_char.setdefault(it.char, []).append(val)
    fam = "".join(ch for ch in s.family if ch.isalnum() or ch in " -_") or "MaPolice"
    s.family = fam
    res = B.build_font(per_char, s, str(OUT / fam.replace(" ", "")))
    missing = sorted({it.char for it in items} - set(per_char))
    res["missing"] = "".join(missing)
    res["files"] = {k: Path(v).name for k, v in res["files"].items()}
    return res
