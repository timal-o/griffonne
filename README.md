<div align="center">

# ✎ Griffonne

**Turn your handwriting into a real font, with several variants of every letter that alternate naturally.**

Print a sheet · write · scan · install your font.

<img src="docs/img/variantes.png" alt="Comparison without and with variants" width="720">

<sub>Example generated from a system cursive font, not from real handwriting. With yours, the effect is more pronounced. (Captions are in French: *sans variantes* = without variants, *avec Griffonne* = with Griffonne.)</sub>

</div>

---

## Why Griffonne?

A typical handwriting font repeats the exact same "a", the same "e"… and it shows immediately: the text looks *computer-made*. Griffonne keeps **several handwritten versions of each character** and picks which one to display based on context, the way a real hand would.

- 🖨️ **Ready-to-print template sheet** (A4 PDF) with guide lines so your letters sit on the baseline
- 📷 **Scan or just take a photo**: automatic deskewing, shadow correction, pages in any order or upside down
- 🔁 **Natural variants**: 3 to 8 shapes per character, never the same one twice in a row
- 🧬 **Synthetic variants**: if you wrote 3 versions, Griffonne derives more, slightly distorted
- 🔤 **`.otf` and `.ttf` output**, including French accents, punctuation and digits
- 🔒 **100% local**: nothing leaves your machine

<div align="center">
<img src="docs/img/interface.png" alt="Griffonne interface" width="640">
</div>

## Installation

Requirements: **Python 3.10 or newer**.

```bash
git clone https://github.com/timal-o/griffonne.git
cd griffonne
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

On Windows, replace `.venv/bin/` with `.venv\Scripts\`.

## Usage

```bash
.venv/bin/python app.py
```

The interface opens at <http://localhost:8765>. Pass `--no-open` to keep the browser from opening.

> The interface is currently in French.

### 1. Print the sheet

Pick the character sets and how many variants to write per letter (**3 to 5** is a good compromise), then download the PDF.

| | |
|---|---|
| Format | A4, **100% scale**, no "fit to page" |
| Pen | Black or dark blue, bold stroke. Avoid light pencil |
| Writing | Put the **bottom of your letters on the solid line**; let descenders (g, p, y…) hang below it |
| Edges | Don't touch the frames and stay inside your box |
| Variants | Deliberately write each version a little differently |

<div align="center"><img src="docs/img/feuille.png" alt="Page 1 of the template sheet" width="420"></div>

### 2. Scan or photograph

Drop your images into the page. Each sheet must show **all 4 black corner squares**. Page order doesn't matter.

- A well-lit photo is enough; a 200-300 dpi scan is ideal.
- The gallery shows what was extracted from each box. **Click a bad box** to exclude it.
- The *ink threshold* slider: lower it if guide lines show up, raise it if your writing is thin.

### 3. Create the font

| Setting | Effect |
|---|---|
| Variants per character | Total number of shapes available (real + synthetic) |
| Synthetic variation | Strength of the distortions applied to generated variants (0 = exact copies) |
| Letter spacing | Margin on each side of every glyph |
| Space width | Width of the space character |
| Size | Global scale relative to what you wrote |
| Contour smoothing | 0 = sharp corners, 1.33 = very round |

Download the `.otf` or `.ttf` and double-click to install it. The built-in preview lets you compare with and without variants, and "Autre tirage" (another draw) changes the random seed.

## Compatibility

Variant selection relies on the OpenType **`calt`** feature (*contextual alternates*).

| Environment | Variants |
|---|---|
| Web browsers (tested in Chrome) | ✅ |
| Desktop publishing (Adobe, Affinity) | ✅ expected, untested |
| Word, Google Docs, Canva, Pages… | ⚠️ Depends on the app. If it ignores `calt`, you get a single shape per letter |

The font stays usable everywhere: the base shape of every letter is always present.

## Known limitations

- The selection is **deterministic**: the same text always renders the same way (the variant depends on neighboring letters, not on true randomness at display time).
- No ligatures or joined letters (continuous cursive).
- No kerning: spacing is uniform, adjustable globally.
- Accented capitals are unchecked by default to keep the page count down.
- Outlines are traced from an image, so quality depends on your scan.

## Try it without writing by hand

A script fabricates fake photos of filled-in sheets using a system cursive font (macOS):

```bash
.venv/bin/python -c "from fontcreator import project; project.save_spec(['lower','upper','digits','punct','fr_lower'], 3)"
.venv/bin/python tests/fake_scan.py       # creates work/fake/scan_*.jpg
.venv/bin/python tests/run_pipeline.py    # ingests them and builds work/out/TestHand.otf
```

## Project structure

```
app.py                 local server (standard library only)
static/                web interface (HTML + JS, no dependencies)
fontcreator/
  layout.py            sheet geometry, PDF rendering
  scan.py              corner detection, deskewing, box extraction
  build.py             vectorization, synthetic variants, GSUB table, OTF/TTF
  project.py           project state (work/ folder)
tests/                 fake photo generation, end-to-end pipeline
docs/                  technical documentation
```

How it works in detail is described in [docs/fonctionnement.md](docs/fonctionnement.md) (in French).

## Built with

[fontTools](https://github.com/fonttools/fonttools) (font assembly, OpenType rule compilation) ·
[OpenCV](https://opencv.org/) (deskewing, thresholding) ·
[potracer](https://github.com/tatarize/potrace) (vectorization, Python port of [Potrace](https://potrace.sourceforge.net/)) ·
[Pillow](https://python-pillow.org/) (sheet rendering)

## License

Griffonne is released under the [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)](LICENSE) license.

[![CC BY-NC-SA 4.0](https://licensebuttons.net/l/by-nc-sa/4.0/88x31.png)](https://creativecommons.org/licenses/by-nc-sa/4.0/)

- ✅ **Use, copy, share and modify** freely.
- 📝 **Attribution**: credit the author and indicate any changes you made.
- ❌ **No commercial use**: you may not sell it or include it in a paid product or service.
- 🔁 **ShareAlike**: a modified version must be published under the same license.

Copyright (c) 2026 Malo

> Creative Commons does not recommend its licenses for source code (they don't address patents, for example). Here they have the advantage of being widely known and recognized by GitHub. This is not an "open source" license in the OSI sense, since it forbids commercial use.
