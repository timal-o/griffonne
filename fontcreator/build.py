"""Vectorisation des glyphes et assemblage de la police (OTF + TTF) avec variantes aléatoires."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import cv2
import numpy as np
import potrace
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen

from . import layout as L
from . import scan

UPM = 1000
UNITS_PER_MM = 62.5          # 12 mm de ligne de base à la ligne d'ascendante = 750 unités
ASCENT, DESCENT = 850, -350
UPSCALE = 2                  # sur-échantillonnage avant vectorisation (contours plus doux)


@dataclass
class Settings:
    family: str = "MaPolice"
    threshold: int = 150
    size: float = 100.0          # % de la taille écrite
    sidebearing: float = 40.0    # unités de chaque côté d'un glyphe
    space: float = 280.0         # largeur de l'espace
    variants: int = 5            # nb total de variantes par caractère (réelles + synthétiques)
    jitter: float = 70.0         # 0-100 : force des variations synthétiques
    smooth: float = 1.0          # alphamax potrace (0 = angles vifs, 1.33 = très arrondi)
    seed: int = 7
    excluded: list = field(default_factory=list)   # index d'items à ignorer


# --- Vectorisation ---------------------------------------------------------
def trace_glyph(crop: np.ndarray, baseline_px: float, s: Settings):
    """Renvoie une liste d'opérations de tracé (RecordingPen.value), coordonnées en unités de police,
    origine = ligne de base, x brut (non normalisé). None si vide."""
    mask = scan.ink_mask(crop, s.threshold)
    if not scan.has_ink(mask):
        return None
    ys, xs = np.where(mask)
    pad = 3
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad + 1, crop.shape[1])
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad + 1, crop.shape[0])
    g = crop[y0:y1, x0:x1].astype(np.float32)
    m = mask[y0:y1, x0:x1]
    g = np.where(m, g, np.maximum(g, s.threshold + 1))  # les poussières effacées deviennent du fond
    up = cv2.resize(g, None, fx=UPSCALE, fy=UPSCALE, interpolation=cv2.INTER_CUBIC)
    up = cv2.GaussianBlur(up, (0, 0), 0.9 * UPSCALE / 2)
    ink = np.pad(up < s.threshold, 2, constant_values=False)
    bm = potrace.Bitmap(~ink)  # potracer trace les pixels False
    plist = bm.trace(turdsize=6, turnpolicy=potrace.POTRACE_TURNPOLICY_MINORITY,
                     alphamax=s.smooth, opticurve=True, opttolerance=0.25)
    k = UNITS_PER_MM * s.size / 100.0 / scan.S  # px page -> unités de police

    def P(pt):
        px = (pt.x - 2) / UPSCALE + x0
        py = (pt.y - 2) / UPSCALE + y0
        return (px * k, (baseline_px - py) * k)

    pen = RecordingPen()
    for curve in plist:
        pen.moveTo(P(curve.start_point))
        for seg in curve.segments:
            if seg.is_corner:
                pen.lineTo(P(seg.c))
                pen.lineTo(P(seg.end_point))
            else:
                pen.curveTo(P(seg.c1), P(seg.c2), P(seg.end_point))
        pen.closePath()
    return pen.value


def _map_points(value, fn):
    out = []
    for op, args in value:
        out.append((op, tuple(fn(p) for p in args)))
    return out


def _bounds(value):
    bp = BoundsPen(None)
    _replay(value, bp)
    return bp.bounds


def _replay(value, pen):
    for op, args in value:
        getattr(pen, op)(*args)


def _signed_area(value) -> float:
    """Aire signée (repère y vers le haut) du plus grand contour."""
    best, cur = 0.0, []
    for op, args in value:
        if op == "moveTo":
            cur = [args[0]]
        elif op in ("lineTo", "curveTo"):
            cur.extend(args)
        elif op == "closePath" and len(cur) > 2:
            a = sum(cur[i][0] * cur[(i + 1) % len(cur)][1] - cur[(i + 1) % len(cur)][0] * cur[i][1]
                    for i in range(len(cur))) / 2
            if abs(a) > abs(best):
                best = a
    return best


def _oriented(value, want_ccw: bool):
    """Oriente les contours extérieurs : anti-horaire pour CFF, horaire pour TrueType."""
    a = _signed_area(value)
    if (a > 0) == want_ccw:
        return value
    rp = RecordingPen()
    _replay(value, ReverseContourPen(rp))
    return rp.value


# --- Variations synthétiques -----------------------------------------------
def synth_variation(value, rng: random.Random, strength: float):
    """Déforme légèrement un glyphe (rotation, échelle, cisaillement, ondulation douce)."""
    st = strength / 100.0
    rot = math.radians(rng.uniform(-5, 5) * st)
    sx, sy = 1 + rng.uniform(-0.12, 0.12) * st, 1 + rng.uniform(-0.10, 0.10) * st
    shear = rng.uniform(-0.14, 0.14) * st
    dy = rng.uniform(-18, 18) * st
    amp = 22 * st
    f1, f2 = rng.uniform(0.5, 1.8), rng.uniform(0.5, 1.8)
    p1, p2 = rng.uniform(0, 6.28), rng.uniform(0, 6.28)
    cr, sr = math.cos(rot), math.sin(rot)

    def fn(p):
        x, y = p
        x2 = x + shear * y + amp * math.sin(y / 260 * f1 + p1)
        y2 = y + amp * math.sin(x / 260 * f2 + p2)
        x2, y2 = x2 * sx, y2 * sy
        return (x2 * cr - y2 * sr, x2 * sr + y2 * cr + dy)

    return _map_points(value, fn)


# --- Assemblage ------------------------------------------------------------
def gname(ch: str, v: int) -> str:
    base = f"uni{ord(ch):04X}"
    return base if v == 0 else f"{base}.v{v}"


def make_calt(chars: list[str], N: int, seed: int) -> str:
    """Génère les règles calt (choix pseudo-aléatoire de variante selon le contexte)."""
    rng = random.Random(seed)
    base = " ".join(gname(c, 0) for c in chars)
    lines = [f"@base = [{base}];"]
    for j in range(N):
        lines.append(f"@V{j} = [{' '.join(gname(c, j) for c in chars)}];")   # état = n° de variante
    lines.append("@ANY = [" + " ".join(f"@V{j}" for j in range(N)) + "];")
    body = []
    # deux glyphes de contexte -> variante suivante tirée au hasard (jamais la même que la précédente)
    for i in range(N):
        for j in range(N):
            k = rng.choice([x for x in range(N) if x != j])
            body.append(f"    sub @V{i} @V{j} @base' by @V{k};")
    for j in range(N):  # un seul glyphe de contexte (2e lettre d'un mot)
        k = rng.choice([x for x in range(N) if x != j])
        body.append(f"    sub @V{j} @base' by @V{k};")
    # début de mot : variante choisie d'après la lettre suivante
    for m in range(N):
        grp = " ".join(gname(c, 0) for idx, c in enumerate(chars) if idx % N == m)
        if grp:
            body.append(f"    sub @base' [{grp}] by @V{m};")
    fea = "\n".join(lines)
    fea += "\nfeature calt {\n" + "\n".join(body) + "\n} calt;\n"
    return fea


def build_font(glyph_variants: dict[str, list], s: Settings, out_base: str, log=print) -> dict:
    """glyph_variants : caractère -> liste de tracés bruts (RecordingPen.value).
    Écrit out_base + '.otf' / '.ttf'. Retourne un résumé."""
    rng = random.Random(s.seed)
    chars = [c for c, vs in glyph_variants.items() if vs]
    if not chars:
        raise ValueError("Aucun glyphe exploitable.")
    N = max(1, s.variants)

    # 1) N variantes par caractère : réelles d'abord, puis synthétiques
    final: dict[str, list] = {}
    n_synth = 0
    for c in chars:
        real = list(glyph_variants[c])
        rng.shuffle(real) if len(real) > N else None
        vs = real[:N]
        while len(vs) < N:
            src = rng.choice(real)
            vs.append(synth_variation(src, rng, s.jitter) if s.jitter > 0 else src)
            n_synth += 1
        final[c] = vs

    # 2) normalisation horizontale : xMin -> sidebearing, avance = largeur + 2*sidebearing
    glyphs: dict[str, tuple[list, int]] = {}
    for c in chars:
        for v, val in enumerate(final[c]):
            b = _bounds(val)
            if b is None:
                continue
            dx = s.sidebearing - b[0]
            val = _map_points(val, lambda p, dx=dx: (p[0] + dx, p[1]))
            glyphs[gname(c, v)] = (val, round(b[2] - b[0] + 2 * s.sidebearing))

    order = [".notdef", "space"] + list(glyphs.keys())
    cmap = {32: "space"}
    for c in chars:
        cmap[ord(c)] = gname(c, 0)
    fea = make_calt(chars, N, s.seed) if N > 1 else ""

    def make(kind: str):
        isTTF = kind == "ttf"
        fb = FontBuilder(UPM, isTTF=isTTF)
        fb.setupGlyphOrder(order)
        fb.setupCharacterMap(cmap)
        pens = {}
        # .notdef : simple rectangle
        nd = RecordingPen()
        for pts in ([(80, 0), (80, 700), (500, 700), (500, 0)], [(130, 50), (450, 50), (450, 650), (130, 650)]):
            nd.moveTo(pts[0]); [nd.lineTo(p) for p in pts[1:]]; nd.closePath()
        specs = {".notdef": (nd.value, 580), "space": ([], round(s.space))}
        specs.update(glyphs)
        for name in order:
            val, _ = specs[name]
            val = _oriented(val, want_ccw=not isTTF) if val else val
            if isTTF:
                pen = TTGlyphPen(None)
                _replay(val, Cu2QuPen(pen, 1.0, reverse_direction=False))
                pens[name] = pen.glyph()
            else:
                pen = T2CharStringPen(specs[name][1], None)
                _replay(val, pen)
                pens[name] = pen.getCharString()
        family = s.family
        ps = family.replace(" ", "") + "-Regular"
        lsb = {}
        for n in order:
            b = _bounds(specs[n][0]) if specs[n][0] else None
            lsb[n] = (specs[n][1], round(b[0]) if b else 0)
        if isTTF:
            fb.setupGlyf(pens)
        else:
            fb.setupCFF(ps, {"FullName": f"{family} Regular", "FamilyName": family}, pens, {})
        fb.setupHorizontalMetrics(lsb)
        fb.setupHorizontalHeader(ascent=ASCENT, descent=DESCENT)
        fb.setupNameTable({"familyName": family, "styleName": "Regular"})
        fb.setupOS2(sTypoAscender=ASCENT, sTypoDescender=DESCENT, sTypoLineGap=0,
                    usWinAscent=1000, usWinDescent=450, sxHeight=400, sCapHeight=750, fsType=0)
        fb.setupPost()
        if fea:
            addOpenTypeFeaturesFromString(fb.font, fea)
        path = f"{out_base}.{kind}"
        fb.save(path)
        return path

    files = {k: make(k) for k in ("otf", "ttf")}
    return {"files": files, "chars": len(chars), "variants": N, "synthetic": n_synth, "glyphs": len(glyphs)}
