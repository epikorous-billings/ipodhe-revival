"""Minimal FAT12/FAT16 reader/writer for the iPod 'rsrc' resource volume.

Note: Apple labels the volume "FAT16", but it has fewer than 4085 clusters,
which by the FAT spec makes it FAT12 - the cluster count decides, not the label.

Only what this project needs: walk directories (long file names supported),
read a file, and replace a file's contents in place (growing or shrinking its
cluster chain). Operates on an in-memory bytearray; nothing touches a disk.
"""
import struct
import time



class FAT16:
    def __init__(self, img: bytearray):
        self.img = img
        (self.bps, self.spc, self.reserved, self.nfats, self.nroot,
         tot16, _media, self.spf) = struct.unpack_from('<HBHBHHBH', img, 11)
        tot32 = struct.unpack_from('<I', img, 32)[0]
        self.total_sectors = tot16 or tot32
        if img[54:57] != b'FAT':
            raise ValueError('not a FAT volume')
        self.fat_off = self.reserved * self.bps
        self.root_off = self.fat_off + self.nfats * self.spf * self.bps
        self.data_off = self.root_off + self.nroot * 32
        self.csize = self.spc * self.bps
        self.nclusters = (self.total_sectors * self.bps - self.data_off) // self.csize + 2
        self.fat12 = (self.nclusters - 2) < 4085
        self.EOC = 0xFF8 if self.fat12 else 0xFFF8
        self.EOC_MARK = 0xFFF if self.fat12 else 0xFFFF

    # ---- FAT helpers -------------------------------------------------------
    def _fat_get(self, c):
        if self.fat12:
            v = struct.unpack_from('<H', self.img, self.fat_off + c + c // 2)[0]
            return (v >> 4) if c & 1 else (v & 0xFFF)
        return struct.unpack_from('<H', self.img, self.fat_off + 2 * c)[0]

    def _fat_set(self, c, v):
        for i in range(self.nfats):
            base = self.fat_off + i * self.spf * self.bps
            if self.fat12:
                o = base + c + c // 2
                cur = struct.unpack_from('<H', self.img, o)[0]
                cur = ((cur & 0x000F) | (v << 4)) if c & 1 else ((cur & 0xF000) | (v & 0xFFF))
                struct.pack_into('<H', self.img, o, cur & 0xFFFF)
            else:
                struct.pack_into('<H', self.img, base + 2 * c, v)

    def _chain(self, c):
        out = []
        while 2 <= c < self.EOC:
            out.append(c)
            c = self._fat_get(c)
            if len(out) > self.nclusters:
                raise ValueError('FAT loop')
        return out

    def _coff(self, c):
        return self.data_off + (c - 2) * self.csize

    # ---- directories -------------------------------------------------------
    def _dir_bytes_offsets(self, first_cluster):
        """Yield absolute offsets of every 32-byte entry in a directory."""
        if first_cluster == 0:          # root directory
            for i in range(self.nroot):
                yield self.root_off + 32 * i
        else:
            for c in self._chain(first_cluster):
                base = self._coff(c)
                for i in range(self.csize // 32):
                    yield base + 32 * i

    def listdir(self, first_cluster=0):
        """Return [(long_name, entry_offset)] for a directory."""
        out, lfn = [], {}
        for off in self._dir_bytes_offsets(first_cluster):
            e = self.img[off:off + 32]
            if e[0] == 0x00:
                break
            if e[0] == 0xE5:
                lfn = {}
                continue
            if e[11] == 0x0F:  # long-name fragment
                seq = e[0] & 0x1F
                chars = e[1:11] + e[14:26] + e[28:32]
                lfn[seq] = chars.decode('utf-16-le', 'ignore').split('\x00')[0].replace('￿', '')
                continue
            short = e[0:8].decode('latin-1').rstrip() + ('.' + e[8:11].decode('latin-1').rstrip() if e[8:11].strip() else '')
            name = ''.join(lfn[k] for k in sorted(lfn)) if lfn else short
            lfn = {}
            if e[11] & 0x08:  # volume label
                continue
            out.append((name, off))
        return out

    def _lookup(self, path):
        cluster, off = 0, None
        for part in [p for p in path.replace('\\', '/').split('/') if p]:
            for name, eoff in self.listdir(cluster):
                if name.lower() == part.lower():
                    off = eoff
                    cluster = struct.unpack_from('<H', self.img, eoff + 26)[0]
                    break
            else:
                raise FileNotFoundError(path)
        return off

    # ---- files -------------------------------------------------------------
    def read(self, path) -> bytes:
        off = self._lookup(path)
        first = struct.unpack_from('<H', self.img, off + 26)[0]
        size = struct.unpack_from('<I', self.img, off + 28)[0]
        data = b''.join(bytes(self.img[self._coff(c):self._coff(c) + self.csize]) for c in self._chain(first))
        return data[:size]

    def replace(self, path, data: bytes):
        """Overwrite an existing file with new contents (any size that fits)."""
        off = self._lookup(path)
        first = struct.unpack_from('<H', self.img, off + 26)[0]
        chain = self._chain(first)
        need = max(1, -(-len(data) // self.csize))
        if need > len(chain):                       # grow
            free = [c for c in range(2, self.nclusters) if self._fat_get(c) == 0]
            extra = need - len(chain)
            if len(free) < extra:
                raise ValueError('not enough free space on the resource volume')
            new = free[:extra]
            prev = chain[-1]
            for c in new:
                self._fat_set(prev, c)
                prev = c
            self._fat_set(prev, self.EOC_MARK)
            chain += new
        elif need < len(chain):                     # shrink
            self._fat_set(chain[need - 1], self.EOC_MARK)
            for c in chain[need:]:
                self._fat_set(c, 0)
            chain = chain[:need]
        for i, c in enumerate(chain):
            chunk = data[i * self.csize:(i + 1) * self.csize]
            o = self._coff(c)
            self.img[o:o + self.csize] = chunk + b'\x00' * (self.csize - len(chunk))
        struct.pack_into('<I', self.img, off + 28, len(data))
        # update modification date/time
        t = time.localtime()
        struct.pack_into('<H', self.img, off + 22, (t.tm_hour << 11) | (t.tm_min << 5) | (t.tm_sec // 2))
        struct.pack_into('<H', self.img, off + 24, ((t.tm_year - 1980) << 9) | (t.tm_mon << 5) | t.tm_mday)
