"""Lecture d'une feuille scannée/photographiée : redressement + extraction des cases."""
from __future__ import annotations

import cv2
import numpy as np

from . import layout as L

S = 12  # pixels par mm dans la page redressée


class ScanError(Exception):
    pass


def _normalize(gray: np.ndarray, kernel: int) -> np.ndarray:
    """Corrige l'éclairage : divise par le fond estimé (fermeture morphologique)."""
    k = kernel | 1
    bg = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    bg = cv2.GaussianBlur(bg, (0, 0), k / 4)
    out = gray.astype(np.float32) / np.maximum(bg.astype(np.float32), 1.0) * 255.0
    return np.clip(out, 0, 255).astype(np.uint8)


def _find_markers(gray: np.ndarray) -> np.ndarray:
    """Retourne les 4 centres de marqueurs (px image d'origine), ordre cyclique horaire."""
    h, w = gray.shape
    scale = min(1.0, 1600.0 / max(h, w))
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else gray
    norm = _normalize(small, int(0.09 * max(small.shape)))
    bw = (norm < 120).astype(np.uint8)
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cands = []
    for c in cnts:
        area = cv2.contourArea(c)
        if area < 120:
            continue
        (_, _), (rw, rh), _ = cv2.minAreaRect(c)
        if rw < 1 or rh < 1:
            continue
        aspect = max(rw, rh) / min(rw, rh)
        fill = area / (rw * rh)
        if aspect < 1.6 and fill > 0.78:
            m = cv2.moments(c)
            cands.append((area, (m["m10"] / m["m00"], m["m01"] / m["m00"])))
    cands.sort(reverse=True)
    if len(cands) < 4 or cands[3][0] < 0.35 * cands[0][0]:
        raise ScanError("Les 4 carrés noirs des coins n'ont pas été trouvés. "
                        "Vérifie qu'ils sont visibles en entier sur la photo/le scan.")
    pts = np.array([p for _, p in cands[:4]], dtype=np.float32) / scale
    ctr = pts.mean(axis=0)
    ang = np.arctan2(pts[:, 1] - ctr[1], pts[:, 0] - ctr[0])
    return pts[np.argsort(ang)]  # y vers le bas => angle croissant = sens horaire


def _mm_to_px(pts, s):
    return np.array(pts, dtype=np.float32) * s


def _dark_at(norm: np.ndarray, s: float, cx: float, cy: float, size: float) -> float:
    r = size * 0.3 * s
    x, y = cx * s, cy * s
    patch = norm[int(y - r):int(y + r) + 1, int(x - r):int(x + r) + 1]
    return float((patch < 128).mean()) if patch.size else 0.0


def rectify(img_bgr: np.ndarray) -> tuple[int, np.ndarray]:
    """Renvoie (n° de page, image grise redressée et normalisée à S px/mm)."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    quad = _find_markers(gray)
    dst_mm = np.array(L.MARKERS, dtype=np.float32)

    # 1) on cherche la rotation (0/90/180/270°) grâce à la marque d'orientation
    s0 = 4
    best = None
    for shift in range(4):
        src = np.roll(quad, -shift, axis=0)
        M = cv2.getPerspectiveTransform(src, _mm_to_px(dst_mm, s0))
        w0 = cv2.warpPerspective(gray, M, (int(L.PAGE_W * s0), int(L.PAGE_H * s0)))
        n0 = _normalize(w0, 41)
        score = _dark_at(n0, s0, *L.ORIENT, L.ORIENT_SIZE) + _dark_at(n0, s0, L.CODE_X0, L.CODE_Y, L.CODE_SIZE)
        if best is None or score > best[0]:
            best = (score, src, n0)
    score, src, n0 = best
    if score < 1.3:
        raise ScanError("Feuille non reconnue (marque d'orientation introuvable). "
                        "Est-ce bien une feuille générée par cet outil ?")

    bits = [1 if _dark_at(n0, s0, L.CODE_X0 + L.CODE_DX * i, L.CODE_Y, L.CODE_SIZE) > 0.5 else 0
            for i in range(L.CODE_BITS)]
    page = int("".join(map(str, bits[1:])), 2)
    if page < 1:
        raise ScanError("Numéro de page illisible.")

    # 2) redressement final en pleine résolution
    M = cv2.getPerspectiveTransform(src, _mm_to_px(dst_mm, S))
    warped = cv2.warpPerspective(gray, M, (int(L.PAGE_W * S), int(L.PAGE_H * S)), flags=cv2.INTER_CUBIC)
    return page, _normalize(warped, 61)


def cell_crop(page_gray: np.ndarray, row: int, col: int) -> tuple[np.ndarray, float]:
    """Zone d'écriture d'une case (niveaux de gris) + ordonnée de la ligne de base dans ce crop (px)."""
    x0, y0 = L.cell_origin(row, col)
    i = L.CROP_INSET
    xa, xb = round((x0 + i) * S), round((x0 + L.CELL_W - i) * S)
    ya, yb = round((y0 + i) * S), round((y0 + L.WRITE_H - i) * S)
    return page_gray[ya:yb, xa:xb], (L.BASE_Y - i) * S


def ink_mask(crop: np.ndarray, threshold: int, min_speck_px: int = 14) -> np.ndarray:
    """Masque booléen de l'encre, sans les poussières."""
    mask = (crop < threshold).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    keep = np.zeros(n, dtype=bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_speck_px
    return keep[lab]


def has_ink(mask: np.ndarray) -> bool:
    return int(mask.sum()) >= 70  # ~0,5 mm²
