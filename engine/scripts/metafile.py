"""Recover a full-frame bitmap stored in EMF+; refuse transformed/vector drawings.

Layout: MS-EMFPLUS EmfPlusBitmap and EmfPlusDrawImage records:
https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-emfplus/112a5e2c-6bb3-4daf-8ee3-0f3d3984410f
"""
import struct
from PIL import Image, ImageChops


def embedded_bitmap(path, destination):
    data = path.read_bytes()
    records, position = [], 0
    while position + 8 <= len(data):
        kind, size = struct.unpack_from('<II', data, position)
        if size < 8 or position + size > len(data) or kind not in {1, 14, 70}:
            return False
        if kind == 70 and data[position+12:position+16] == b'EMF+':
            cursor, end = position + 16, position + size
            while cursor + 12 <= end:
                tag, flags, length, count = struct.unpack_from('<HHII', data, cursor)
                if length < 12 or cursor + length > end or count > length - 12:
                    return False
                records.append((tag, flags, data[cursor+12:cursor+12+count]))
                cursor += length
        position += size
    if not records or any(t not in {0x4001,0x4002,0x4030,0x4009,0x4023,0x4008,0x401a} for t,_,_ in records):
        return False
    bitmaps, draws = [], []
    for tag, flags, payload in records:
        if tag == 0x4030 and (flags != 2 or payload != struct.pack('<f', 1)):
            return False
        if tag == 0x4009 and (len(payload) != 4 or payload[3] != 0):
            return False
        if tag == 0x4023 and flags != 0:
            return False
        if tag == 0x4008:
            object_type = (flags >> 8) & 127
            if flags & 0x8000 or object_type not in {5, 8}:
                return False
            if object_type == 5:
                if len(payload) < 28:
                    return False
                version, image_type, width, height, stride, pixel_format, encoding = struct.unpack_from('<IIiiiII', payload)
                if image_type != 1 or encoding != 0 or pixel_format not in {0x26200a,0xe200b} or not (0 < width <= 20000 and 0 < height <= 20000) or stride != width * 4 or len(payload) != 28 + stride * height:
                    return False
                im = Image.frombytes('RGBA', (width,height), payload[28:], 'raw', 'BGRA', stride, 1)
                if pixel_format == 0xe200b:
                    im = Image.frombytes('RGBa', im.size, im.tobytes()).convert('RGBA')
                bitmaps.append((flags & 255, im))
        if tag == 0x401a:
            draws.append((flags,payload))
    if len(bitmaps) != 1 or len(draws) != 1:
        return False
    object_id, im = bitmaps[0]
    flags, payload = draws[0]
    if flags != object_id or len(payload) != 40:
        return False
    _, unit, *rectangles = struct.unpack('<II8f',payload)
    if unit != 2 or rectangles != [0,0,*im.size,0,0,*im.size]:
        return False
    im.save(destination)
    return True


def require_visible(path):
    with Image.open(path) as image:
        rgba = image.convert('RGBA')
        canvas = Image.new('RGBA', rgba.size, 'white')
        canvas.alpha_composite(rgba)
        if ImageChops.difference(canvas.convert('RGB'), Image.new('RGB',rgba.size,'white')).getbbox() is None:
            raise ValueError(f'Figure conversion is blank: {path.name}; provide a verified PNG/PDF export of the original')
