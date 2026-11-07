#!/usr/bin/env python3
"""ipodhe-revival: Hebrew on the stock Apple firmware of the iPod Video (5G / 5.5G).

Commands
  info          BACKUP.bin                         show what's inside a firmware-partition dump
  extract-font  BACKUP.bin  -o apple_font.ttf      pull Apple's PodiumSans18.ttf out of your dump
  build-font    --apple apple_font.ttf --source FONT -o hebrew_font.ttf [--size 18]
  preview       FONT.ttf [FONT2.ttf ...] -o preview.png
  patch         BACKUP.bin --font hebrew_font.ttf -o patched.bin
  flip          DRIVE                              run after every iTunes sync (e.g. flip E:\\)

Typical flow:  ipodpatcher N -r backup.bin  ->  extract-font  ->  build-font  ->  preview
               ->  patch  ->  ipodpatcher N -w patched.bin  ->  sync with iTunes  ->  flip
"""
import argparse
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ipodhe import firmware  # noqa: E402


def cmd_info(a):
    p = firmware.Partition(open(a.backup, 'rb').read())
    print(f'firmware partition: {len(p.d):,} bytes, sector size {p.sector}')
    for n, im in p.images.items():
        extra = ''
        if n == 'osos' and im.entry:
            extra = f'  (Apple firmware {im.entry:,} bytes + bootloader {im.length - im.entry:,} bytes)'
        print(f'  {n}: {im.length:>10,} bytes  checksum {"OK" if im.checksum_ok() else "mismatch"}{extra}')
    old, new = p.db_name_state()
    state = 'stock' if old and not new else 'already patched' if new and not old else f'{old} iTunesDB / {new} iTunesHE'
    print(f'database name in firmware: {state}')
    try:
        font = p.read_font()
        print(f'menu font {firmware.FONT_PATH}: {len(font):,} bytes')
    except Exception as e:
        print(f'menu font: not found ({e})')


def cmd_extract(a):
    p = firmware.Partition(open(a.backup, 'rb').read())
    font = p.read_font()
    open(a.output, 'wb').write(font)
    print(f'wrote {a.output} ({len(font):,} bytes)')


def cmd_build(a):
    from ipodhe import fontbuild
    src = fontbuild.open_source(a.source, a.size)
    spacing = a.hebrew_spacing if a.hebrew_spacing is not None else (1 if a.source.lower().endswith('.fnt') else 0)
    out = fontbuild.build(open(a.apple, 'rb').read(), src, spacing)
    open(a.output, 'wb').write(out)
    print(f'wrote {a.output} ({len(out):,} bytes)')


def cmd_preview(a):
    from ipodhe import preview
    preview.render(a.fonts, a.output)
    print(f'wrote {a.output}')


def cmd_patch(a):
    data = open(a.backup, 'rb').read()
    p = firmware.Partition(data)
    for n in ('osos', 'rsrc'):
        if not p.images[n].checksum_ok():
            sys.exit(f"'{n}' checksum does not match - is the dump complete? Aborting.")
    old, new = p.db_name_state()
    if new:
        sys.exit('This dump is already patched (iTunesHE found). Use your original, unpatched backup.')
    if old != 3:
        print(f'warning: expected 3 iTunesDB references, found {old}')
    font = open(a.font, 'rb').read()
    p.replace_font(font)
    n = p.patch_db_name()
    for im in ('osos', 'rsrc'):
        assert p.images[im].checksum_ok()
    q = firmware.Partition(bytes(p.d))                 # re-parse the result as a check
    assert q.read_font() == font and q.db_name_state() == (0, n)
    open(a.output, 'wb').write(p.d)
    print(f'patched: font replaced, {n} iTunesDB -> iTunesHE, checksums updated')
    print(f'wrote {a.output}  sha256 {hashlib.sha256(p.d).hexdigest()}')
    print('flash with:  ipodpatcher N -w ' + a.output + '   (keep your original backup!)')


def cmd_flip(a):
    from ipodhe import flip
    flip.run(a.drive)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    s = sp.add_parser('info'); s.add_argument('backup'); s.set_defaults(fn=cmd_info)
    s = sp.add_parser('extract-font'); s.add_argument('backup'); s.add_argument('-o', '--output', default='apple_PodiumSans18.ttf'); s.set_defaults(fn=cmd_extract)
    s = sp.add_parser('build-font')
    s.add_argument('--apple', required=True, help="Apple's PodiumSans18.ttf (from extract-font)")
    s.add_argument('--source', required=True, help='Rockbox .fnt or TTF/OTF font with Hebrew')
    s.add_argument('--size', type=int, default=18, help='pixel size when --source is TTF/OTF (default 18)')
    s.add_argument('--hebrew-spacing', type=int, default=None, help='extra px after each Hebrew letter (default: 1 for .fnt, 0 for TTF/OTF)')
    s.add_argument('-o', '--output', default='PodiumSans18_hebrew.ttf'); s.set_defaults(fn=cmd_build)
    s = sp.add_parser('preview'); s.add_argument('fonts', nargs='+'); s.add_argument('-o', '--output', default='preview.png'); s.set_defaults(fn=cmd_preview)
    s = sp.add_parser('patch'); s.add_argument('backup'); s.add_argument('--font', required=True)
    s.add_argument('-o', '--output', default='fw_partition_hebrew.bin'); s.set_defaults(fn=cmd_patch)
    s = sp.add_parser('flip'); s.add_argument('drive', help=r'iPod drive, e.g. E:\ or /Volumes/IPOD'); s.set_defaults(fn=cmd_flip)
    a = ap.parse_args()
    a.fn(a)


if __name__ == '__main__':
    main()
