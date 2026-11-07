"""Reader for Rockbox compiled bitmap fonts (.fnt, format RB12).

Anti-aliased (depth=1) fonts store 4-bit pixels, 2 per byte, low nibble first,
with 15 = background; glyph() returns 0..15 where 15 = full ink."""
import struct
class RBFont:
    def __init__(s,path):
        d=open(path,'rb').read(); s.d=d
        assert d[:4]==b'RB12'
        s.maxw,s.height,s.ascent,s.depth=struct.unpack('<4H',d[4:12])
        s.first,s.default,s.size,s.nbits,s.noff,s.nwid=struct.unpack('<6I',d[12:36])
        s.bits=d[36:36+s.nbits]; off=36+s.nbits
        s.osz=2 if s.nbits<0xFFDB else 4
        if off%s.osz: off+=s.osz-off%s.osz
        fmt='<H' if s.osz==2 else '<I'
        s.offs=[struct.unpack_from(fmt,d,off+i*s.osz)[0] for i in range(s.noff)] if s.noff else None
        wo=off+s.noff*s.osz; s.widths=d[wo:wo+s.nwid] if s.nwid else None
    def idx(s,cp):
        i=cp-s.first
        return i if 0<=i<s.size else s.default-s.first
    def width(s,cp): return s.widths[s.idx(cp)] if s.widths else s.maxw
    def has(s,cp):
        i=cp-s.first
        if not 0<=i<s.size: return False
        di=s.default-s.first
        return i==di or (s.offs[i]!=s.offs[di] if s.offs else True)
    def glyph(s,cp):
        """returns (w,h,rows) rows=list of lists alpha 0..15 (15=ink)"""
        i=s.idx(cp); w=s.width(cp); h=s.height
        o=s.offs[i] if s.offs else i*((w*h+1)//2 if s.depth else w*((h+7)//8))
        px=[[0]*w for _ in range(h)]
        if s.depth:  # 4bpp, row-major, 2 px per byte
            for n in range(w*h):
                b=s.bits[o+n//2]; v=(b>>4) if n%2 else (b&15)
                px[n//w][n%w]=15-v
        else:  # mono, column-major 8-row pages
            for x in range(w):
                for y in range(h):
                    b=s.bits[o+(y//8)*w+x]
                    px[y][x]=15 if b>>(y%8)&1 else 0
        return w,h,px
