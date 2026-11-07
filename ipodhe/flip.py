"""flip.py - make Hebrew readable on an iPod running the Hebrew-patched Apple firmware.

The patched firmware reads iPod_Control/iTunes/iTunesHE instead of iTunesDB.
This script copies iTunesDB -> iTunesHE and rewrites every Hebrew text tag
(title, artist, album, genre, composer, ...) into *visual* order, because the
iPod draws text strictly left-to-right. iTunes keeps its own iTunesDB untouched.

Run it after every sync:   python ipod_he_flip.py I:\
Requires once:  pip install python-bidi
"""
import os, struct, sys

# mhod string types that hold display text (2 = file path: never touch it)
TEXT_TYPES = {1, 3, 4, 5, 6, 7, 8, 9, 12, 13, 14, 18, 22, 23, 24, 25, 27, 28, 29, 30, 31, 200, 201, 202, 300}
# 52/53 are sort indexes, 50/51 smart-playlist data, 100+ playlist prefs: binary, skipped

try:
    from bidi.algorithm import get_display          # python-bidi: full Unicode bidi algorithm
except ImportError:                                 # pragma: no cover
    get_display = None

def visual(s):
    """Logical Hebrew text -> the order the iPod must draw it left-to-right."""
    if get_display is None:
        sys.exit('Missing dependency. Install it once with:   pip install python-bidi')
    return get_display(s, base_dir='R') if has_hebrew(s) else s

def has_hebrew(s): return any('\u0590' <= c <= '\u05FF' for c in s)

def flip(db: bytearray):
    changed = 0
    i = 0
    n = len(db)
    while True:
        i = db.find(b'mhod', i)
        if i < 0 or i + 24 > n: break
        hdr, total, typ = struct.unpack_from('<III', db, i + 4)
        if hdr == 24 and 24 < total <= n - i and typ in TEXT_TYPES and total >= 40:
            enc, slen = struct.unpack_from('<II', db, i + 24)  # position/encoding, byte length
            body = i + 40
            if body + slen <= i + total and slen % 2 == 0 and enc in (0, 1):
                s = bytes(db[body:body + slen]).decode('utf-16-le', 'replace')
                if has_hebrew(s):
                    v = visual(s)
                    out = v.encode('utf-16-le')
                    if len(out) == slen and out != db[body:body + slen]:
                        db[body:body + slen] = out
                        changed += 1
            i += total
        else:
            i += 4
    return changed

def run(root, log=print):
    d = os.path.join(root, 'iPod_Control', 'iTunes')
    src, dst = os.path.join(d, 'iTunesDB'), os.path.join(d, 'iTunesHE')
    if not os.path.exists(src):
        sys.exit(f'No iTunesDB at {src}. Is the iPod mounted there, with "Enable disk use" on?')
    db = bytearray(open(src, 'rb').read())
    if db[:4] != b'mhbd':
        sys.exit('Not an iPod database: ' + src)
    n = flip(db)
    tmp = dst + '.tmp'
    with open(tmp, 'wb') as fh:
        fh.write(db)
    os.replace(tmp, dst)
    log(f'iTunesHE written: {n} Hebrew text fields reordered ({len(db):,} bytes).')
    return n
