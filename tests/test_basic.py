"""Self-contained tests (no Apple files needed):  python -m pytest tests"""
import os, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ipodhe import flip
from ipodhe.fat16 import FAT16


def _mhod(typ, text):
    b = text.encode('utf-16-le')
    return b'mhod' + struct.pack('<III', 24, 40 + len(b), typ) + b'\0' * 8 + struct.pack('<IIII', 1, len(b), 1, 0) + b


def _read(db, typ_wanted):
    out, i = [], 0
    while (i := db.find(b'mhod', i)) >= 0:
        tot, typ = struct.unpack_from('<II', db, i + 8)
        ln = struct.unpack_from('<I', db, i + 28)[0]
        if typ == typ_wanted:
            out.append(db[i + 40:i + 40 + ln].decode('utf-16-le'))
        i += tot
    return out


def test_flip_reorders_hebrew_only():
    db = bytearray(b'mhbd' + b'\0' * 100 + _mhod(1, 'שלום עולם') + _mhod(4, 'Jane Bordeaux')
                   + _mhod(3, 'בחזרה לאלבום הראשון (Live)') + _mhod(2, ':iPod_Control:Music:F01:שלום.mp3'))
    size = len(db)
    assert flip.flip(db) == 2
    assert len(db) == size
    assert _read(db, 1) == ['םלוע םולש']
    assert _read(db, 4) == ['Jane Bordeaux']
    assert _read(db, 3) == ['(Live) ןושארה םובלאל הרזחב']
    assert _read(db, 2) == [':iPod_Control:Music:F01:שלום.mp3']      # file paths untouched


def _tiny_fat12():
    """Build a 1 MB FAT12 volume with /Res/Fonts/A.ttf (no LFN)."""
    bps, spc, res, nfat, nroot, tot, spf = 512, 4, 1, 2, 64, 2048, 2
    img = bytearray(tot * bps)
    img[0:3] = b'\xeb\x3c\x90'
    struct.pack_into('<HBHBHHBH', img, 11, bps, spc, res, nfat, nroot, tot, 0xF8, spf)
    img[54:62] = b'FAT12   '
    fat = res * bps; root = fat + nfat * spf * bps; data = root + nroot * 32; cs = spc * bps
    fs = FAT16(img)
    for c, v in ((0, 0xFF8), (1, 0xFFF), (2, 0xFFF), (3, 0xFFF), (4, 0xFFF)):
        fs._fat_set(c, v)
    def ent(off, name, attr, clus, size=0):
        img[off:off + 11] = name; img[off + 11] = attr
        struct.pack_into('<HI', img, off + 26, clus, size)
    ent(root, b'RES        ', 0x10, 2)
    ent(data + (2 - 2) * cs, b'FONTS      ', 0x10, 3)
    ent(data + (3 - 2) * cs, b'A       TTF', 0x20, 4, 5)
    img[data + (4 - 2) * cs:data + (4 - 2) * cs + 5] = b'hello'
    return img


def test_fat12_read_replace_grow_shrink():
    img = _tiny_fat12()
    fs = FAT16(img)
    assert fs.fat12 and fs.read('Res/Fonts/A.ttf') == b'hello'
    big = os.urandom(5000)                       # needs 3 clusters
    fs.replace('Res/Fonts/A.ttf', big)
    assert FAT16(fs.img).read('/res/fonts/a.ttf') == big
    fs.replace('Res/Fonts/A.ttf', b'x')   # shrink back to 1 cluster
    assert FAT16(fs.img).read('Res/Fonts/A.ttf') == b'x'
