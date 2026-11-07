"""Read and patch an iPod Video (5G / 5.5G) firmware-partition dump made with
`ipodpatcher <N> -r backup.bin`.

Partition layout (offsets inside the dump):
  0x0000  "STOP" banner, ']ih[' header at 0x100
  0x4200  image directory, 40-byte entries: 'osos' (firmware), 'rsrc'
          (resources: a FAT16 volume holding the fonts), 'aupd', ...
Each directory entry stores the image's byte offset, length, entry offset and
a checksum which is the plain 32-bit byte sum of the image.
With the Rockbox bootloader installed, 'osos' = Apple firmware followed by the
bootloader, and the entry offset points at the bootloader.
"""
import struct
from .fat16 import FAT16

DIR_OFFSET = 0x4200
FONT_PATH = 'Resources/Fonts/PodiumSans18.ttf'
DB_OLD, DB_NEW = b'iTunesDB', b'iTunesHE'


class Image:
    def __init__(self, part, idx, entry_off, name, fields):
        self.part, self.idx, self.entry_off, self.name, self.f = part, idx, entry_off, name, fields

    # fields: [?, devOffset, length, addr, entryOffset, checksum, vers, loadAddr]
    @property
    def offset(self): return self.f[1] + self.part.sector
    @property
    def length(self): return self.f[2]
    @property
    def entry(self): return self.f[4]
    @property
    def checksum(self): return self.f[5]

    def data(self):
        return self.part.d[self.offset:self.offset + self.length]

    def put(self, new: bytes):
        assert len(new) == self.length, 'image size must not change'
        self.part.d[self.offset:self.offset + self.length] = new
        self.f[5] = sum(new) & 0xFFFFFFFF
        struct.pack_into('<8I', self.part.d, self.entry_off + 8, *self.f)

    def checksum_ok(self):
        return (sum(self.data()) & 0xFFFFFFFF) == self.checksum


class Partition:
    def __init__(self, data: bytes):
        self.d = bytearray(data)
        if self.d[0x100:0x104] != b']ih[':
            raise ValueError('not an iPod firmware partition dump (missing ]ih[ header)')
        self.images = {}
        for k in range(16):
            o = DIR_OFFSET + 40 * k
            name = bytes(self.d[o + 4:o + 8][::-1])
            if not name.strip(b'\x00\xff'):
                continue
            try:
                n = name.decode('ascii')
            except UnicodeDecodeError:
                continue
            if n in ('osos', 'rsrc', 'aupd', 'hibe', 'osbk'):
                self.images[n] = Image(self, k, o, n, list(struct.unpack_from('<8I', self.d, o + 8)))
        if 'osos' not in self.images:
            raise ValueError("no 'osos' firmware image found")
        # sector size: image data starts one sector after devOffset
        osos = self.images['osos']
        for sector in (0x800, 0x200):
            self.sector = sector
            if osos.data()[0x20:0x2c] == b'portalplayer':
                break
        else:
            raise ValueError('could not locate firmware image (unexpected sector size)')

    # ---- resource volume -----------------------------------------------------
    def _rsrc_fat(self):
        if 'rsrc' not in self.images:
            raise ValueError("no 'rsrc' resource image - this tool supports the iPod Video 5G/5.5G")
        r = bytearray(self.images['rsrc'].data())
        at = r.find(b'\xeb\x3c\x90')
        if at < 0 or r[at + 54:at + 57] != b'FAT':
            raise ValueError('resource image is not a FAT volume')
        return r, at

    def read_font(self) -> bytes:
        r, at = self._rsrc_fat()
        return FAT16(r[at:]).read(FONT_PATH)

    def replace_font(self, font: bytes):
        r, at = self._rsrc_fat()
        fat = FAT16(bytearray(r[at:]))
        fat.replace(FONT_PATH, font)
        assert fat.read(FONT_PATH) == font
        r[at:] = fat.img
        self.images['rsrc'].put(bytes(r))

    # ---- firmware strings ----------------------------------------------------
    def apple_firmware(self) -> bytes:
        o = self.images['osos']
        return o.data()[:o.entry] if o.entry else o.data()

    def patch_db_name(self) -> int:
        o = self.images['osos']
        data = bytearray(o.data())
        end = o.entry if o.entry else len(data)   # never touch the Rockbox bootloader
        n, i = 0, 0
        while True:
            i = data.find(DB_OLD, i, end)
            if i < 0:
                break
            data[i:i + len(DB_OLD)] = DB_NEW
            n += 1
            i += len(DB_OLD)
        o.put(bytes(data))
        return n

    def db_name_state(self):
        fw = self.apple_firmware()
        return fw.count(DB_OLD), fw.count(DB_NEW)
