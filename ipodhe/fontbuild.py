"""Build the iPod Video menu font (PodiumSans18.ttf replacement).

Starts from Apple's own PodiumSans18.ttf (extracted from *your* firmware dump),
redraws every glyph the source font provides, keeps Apple's glyphs for anything
it lacks (UI icons, rare characters) and appends the Hebrew letters.
The output keeps Apple's table layout: an 18 ppem, 4-bit grey EBDT/EBLC strike.

Glyph source can be:
  * a Rockbox .fnt (anti-aliased), e.g. 19-GoogleSans.fnt
  * any TTF/OTF outline font, rendered with FreeType at --size pixels
"""
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph
from fontTools.ttLib.tables.BitmapGlyphMetrics import SmallGlyphMetrics
from fontTools.ttLib.tables.E_B_D_T_ import ebdt_bitmap_format_1
import io

PPEM = 18
HEBREW = list(range(0x5D0, 0x5EB))


class Source:
    """Glyph provider: has(cp) and bitmap(cp) -> (advance, left, top, rows[0..15])."""


class RockboxSource(Source):
    def __init__(self, path):
        from .rbfnt import RBFont
        self.f = RBFont(path)

    def has(self, cp):
        return self.f.has(cp)

    def bitmap(self, cp):
        w, h, px = self.f.glyph(cp)
        rows = [y for y in range(h) if any(px[y])]
        if not rows:
            return self.f.width(cp), 0, 0, []
        cols = [x for x in range(w) if any(px[y][x] for y in range(h))]
        t, b, l, r = rows[0], rows[-1], cols[0], cols[-1]
        crop = [px[y][l:r + 1] for y in range(t, b + 1)]
        return self.f.width(cp), l, self.f.ascent - t, crop


class OutlineSource(Source):
    def __init__(self, path, size):
        import freetype
        self.face = freetype.Face(path)
        self.face.set_pixel_sizes(0, size)
        self.ft = freetype

    def has(self, cp):
        return self.face.get_char_index(cp) != 0

    def bitmap(self, cp):
        ft = self.ft
        self.face.load_char(chr(cp), ft.FT_LOAD_RENDER | ft.FT_LOAD_TARGET_LIGHT)
        g = self.face.glyph
        bm = g.bitmap
        adv = (g.advance.x + 32) >> 6
        if bm.rows == 0 or bm.width == 0:
            return adv, 0, 0, []
        rows = [[(bm.buffer[y * bm.pitch + x] * 15 + 127) // 255 for x in range(bm.width)]
                for y in range(bm.rows)]
        return adv, g.bitmap_left, g.bitmap_top, rows


def open_source(path, size=PPEM):
    if path.lower().endswith('.fnt'):
        return RockboxSource(path)
    return OutlineSource(path, size)


def _pack(rows):
    """rows of 0..15 -> EBDT format-1 data (byte-aligned, 4 bpp, high nibble first)."""
    if not rows:
        return 1, 1, b'\x00'
    w, h = len(rows[0]), len(rows)
    rb = (w * 4 + 7) // 8
    out = bytearray()
    for row in rows:
        row = list(row) + [0]
        for i in range(rb):
            out.append((row[2 * i] << 4) | (row[2 * i + 1] if 2 * i + 1 < w else 0))
    return w, h, bytes(out)


def build(apple_font: bytes, src: Source, hebrew_spacing=1, log=print) -> bytes:
    f = TTFont(io.BytesIO(apple_font), recalcTimestamp=False)  # reproducible builds
    f.ensureDecompiled()
    hdmx = {k: dict(v.items()) for k, v in f['hdmx'].hdmx.items()} if 'hdmx' in f else None
    upem = f['head'].unitsPerEm

    # 1. append Hebrew glyph slots that Apple's font lacks
    order = list(f.getGlyphOrder())
    cmap = f.getBestCmap()
    new = [cp for cp in HEBREW if cp not in cmap and src.has(cp)]
    for cp in new:
        order.append('uni%04X' % cp)
    f.setGlyphOrder(order)
    f['glyf'].glyphOrder = order
    for cp in new:
        n = 'uni%04X' % cp
        f['glyf'].glyphs[n] = Glyph()
        f['hmtx'].metrics[n] = (0, 0)
        for st in f['cmap'].tables:
            if st.isUnicode():
                st.cmap[cp] = n
    if 'LTSH' in f:
        f['LTSH'].yPels.update({'uni%04X' % cp: 1 for cp in new})
    if hdmx is not None:
        f['hdmx'].hdmx = {k: {g: v.get(g, 0) for g in order} for k, v in hdmx.items()}
    strike = f['EBDT'].strikeData[0]
    ist = f['EBLC'].strikes[0].indexSubTables[-1]
    if ist.indexFormat != 1 or ist.imageFormat != 1:
        raise ValueError('unexpected font layout (Apple PodiumSans18 uses index/image format 1)')
    for cp in new:
        n = 'uni%04X' % cp
        strike[n] = ebdt_bitmap_format_1(b'', f)
        ist.names.append(n)

    # 2. redraw glyphs from the source font
    cmap = f.getBestCmap()
    redrawn = kept = 0
    for cp, n in cmap.items():
        if n not in strike:
            continue
        if not src.has(cp):
            kept += 1
            continue
        adv, left, top, rows = src.bitmap(cp)
        if cp in HEBREW:
            adv += hebrew_spacing
        w, h, data = _pack(rows)
        m = SmallGlyphMetrics()
        m.width, m.height = w, h
        m.BearingX = max(-128, min(127, left))
        m.BearingY = max(-128, min(127, top))
        m.Advance = max(0, min(255, adv))
        g = strike[n]
        g.metrics, g.imageData = m, data
        f['hmtx'].metrics[n] = (round(m.Advance * upem / PPEM), f['hmtx'].metrics[n][1])
        if hdmx is not None and PPEM in f['hdmx'].hdmx:
            f['hdmx'].hdmx[PPEM][n] = m.Advance
        redrawn += 1
    f['maxp'].numGlyphs = len(order)
    out = io.BytesIO()
    f.save(out)
    log(f'font: {len(order)} glyphs (+{len(new)} Hebrew), {redrawn} redrawn, {kept} kept from Apple')
    return out.getvalue()
