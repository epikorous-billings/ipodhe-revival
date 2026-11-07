"""Render iPod-style 320x240 menu mock-ups from a built font, so you can judge it
before flashing. Hebrew rows are drawn exactly as the patched firmware will:
visual-order text drawn left to right."""
from PIL import Image, ImageDraw
import freetype
from .flip import visual


def _draw(img, face, text, x, baseline, color):
    for ch in text:
        face.load_char(ch, freetype.FT_LOAD_RENDER)
        g, bm = face.glyph, face.glyph.bitmap
        for r in range(bm.rows):
            for c in range(bm.width):
                if bm.pixel_mode == freetype.FT_PIXEL_MODE_GRAY4:
                    byte = bm.buffer[r * bm.pitch + c // 2]
                    v = ((byte >> 4) if c % 2 == 0 else (byte & 15)) / 15
                else:
                    v = bm.buffer[r * bm.pitch + c] / 255
                if v:
                    p = (x + g.bitmap_left + c, baseline - g.bitmap_top + r)
                    if 0 <= p[0] < img.width and 0 <= p[1] < img.height:
                        bg = img.getpixel(p)
                        img.putpixel(p, tuple(int(bg[i] * (1 - v) + color[i] * v) for i in range(3)))
        x += face.glyph.advance.x >> 6


def _screen(font_path, title, rows, sel):
    face = freetype.Face(font_path)
    face.select_size(0)
    img = Image.new('RGB', (320, 240), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 320, 22], fill=(228, 232, 238))
    d.line([0, 22, 320, 22], fill=(150, 150, 160))
    w = 0
    for ch in title:
        face.load_char(ch)
        w += face.glyph.advance.x >> 6
    _draw(img, face, title, 160 - w // 2, 16, (0, 0, 0))
    for i, t in enumerate(rows):
        y = 23 + i * 24
        if i == sel:
            d.rectangle([0, y, 320, y + 23], fill=(52, 120, 205))
        col = (255, 255, 255) if i == sel else (0, 0, 0)
        _draw(img, face, visual(t), 8, y + 17, col)
        _draw(img, face, '>', 302, y + 17, col)
    return img


MUSIC = ['Playlists', 'Artists', 'Albums', 'Songs', 'Genres', 'Composers', 'Audiobooks', 'Search', 'Settings']
ARTISTS = ['עפרה חזה', 'שלמה ארצי', 'אריק איינשטיין', 'Jane Bordeaux', 'בחזרה לאלבום הראשון (Live)',
           'יובל שם טוב', 'Static & Ben El', 'משינה', 'כוורת']


def render(fonts, out_path):
    """fonts: list of font file paths; one column per font."""
    out = Image.new('RGB', (10 + 330 * len(fonts), 510), (40, 40, 44))
    for col, fp in enumerate(fonts):
        out.paste(_screen(fp, 'Music', MUSIC, 3), (10 + col * 330, 10))
        out.paste(_screen(fp, 'Artists', ARTISTS, 1), (10 + col * 330, 260))
    out.save(out_path)
