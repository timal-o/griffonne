import sys
import uharfbuzz as hb
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont
path = sys.argv[1]; text = sys.argv[2]; out = sys.argv[3]
blob = hb.Blob.from_file_path(path); face = hb.Face(blob); font = hb.Font(face)
buf = hb.Buffer(); buf.add_str(text); buf.guess_segment_properties()
hb.shape(font, buf, {"calt": True})
names = [font.glyph_to_string(i.codepoint) for i in buf.glyph_infos]
print(" ".join(names))
# rendu : on dessine glyphe par glyphe avec fontTools -> PIL via pen
from fontTools.pens.freetypePen import FreeTypePen
