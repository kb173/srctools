"""Functions for reading/writing VTF data."""
import array
import itertools


def blank(width: int, height: int) -> array.array:
    """Construct a blank image of the desired size."""
    return array.array('B', itertools.repeat(0, times=width * height * 4))


def ppm_convert(pixels, width, height) -> bytes:
    """Convert a frame into a PPM-format bytestring, for passing to tkinter."""
    header = b'P6 %i %i 255\n' % (width, height)
    img_off = len(header)
    buffer = bytearray(img_off + 3 * width * height)

    buffer[0:img_off] = header

    for off in range(width * height):
        buffer[img_off+3*off:img_off+3*off + 3] = pixels[4*off:4*off + 3]

    return bytes(buffer)


def decomp565(a: int, b: int):
    """Decompress 565-packed data into RGB triplets."""
    return (
        (a & 0b00011111) << 3,
        ((b & 0b00000111) << 5) | ((a & 0b11100000) >> 3),
        b & 0b11111000,
    )


def loader_rgba(mode: str):
    """Make the RGB loader functions."""
    r_off = mode.index('r')
    g_off = mode.index('g')
    b_off = mode.index('b')
    try:
        a_off = mode.index('a')
    except ValueError:
        def loader(pixels, data, width, height):
            for offset in range(width * height):
                pixels[4 * offset] = data[3 * offset + r_off]
                pixels[4 * offset + 1] = data[3 * offset + g_off]
                pixels[4 * offset + 2] = data[3 * offset + b_off]
                pixels[4 * offset + 3] = 255
    else:
        def loader(pixels, data, width, height):
            for offset in range(width * height):
                pixels[4 * offset] = data[4 * offset + r_off]
                pixels[4 * offset + 1] = data[4 * offset + g_off]
                pixels[4 * offset + 2] = data[4 * offset + b_off]
                pixels[4 * offset + 3] = data[4 * offset + a_off]
    return loader


load_rgba8888 = loader_rgba('rgba')
load_bgra8888 = loader_rgba('bgra')

# This is totally the wrong order, but it's how it's actually ordered.
load_argb8888 = loader_rgba('gbar')
load_abgr8888 = loader_rgba('abgr')

load_rgb888 = loader_rgba('rgb')
load_bgr888 = loader_rgba('bgr')


# These semantically operate differently, but just have 4 channels.
load_uvlx8888 = loader_rgba('rgba')
load_uvwq8888 = loader_rgba('rgba')


def upsample(bits, data):
    """Stretch bits worth of data to fill the byte.

    This is done by duplicating the MSB to fill the remaining space.
    """
    return data | (data >> bits)


def load_bgrx8888(pixels, data, width, height):
    """Strange - skip byte."""
    for offset in range(width * height):
        pixels[4 * offset] = data[4 * offset + 2]
        pixels[4 * offset + 1] = data[4 * offset + 1]
        pixels[4 * offset + 2] = data[4 * offset + 0]
        pixels[4 * offset + 3] = 255


def load_rgb565(pixels, data, width, height):
    """RGB format, packed into 2 bytes by dropping LSBs."""
    for offset in range(width * height):
        r, g, b = decomp565(data[2 * offset], data[2 * offset + 1])

        pixels[4 * offset] = upsample(5, r)
        pixels[4 * offset + 1] = upsample(6, g)
        pixels[4 * offset + 2] = upsample(5, b)
        pixels[4 * offset + 3] = 255


def load_bgr565(pixels, data, width, height):
    """BGR format, packed into 2 bytes by dropping LSBs."""
    for offset in range(width * height):
        b, g, r = decomp565(data[2 * offset], data[2 * offset + 1])

        pixels[4 * offset] = upsample(5, r)
        pixels[4 * offset + 1] = upsample(6, g)
        pixels[4 * offset + 2] = upsample(5, b)
        pixels[4 * offset + 3] = 255


def load_bgra4444(pixels, data, width, height):
    """BGRA format, only upper 4 bits. Bottom half is a copy of the top."""
    for offset in range(width * height):
        a = data[2 * offset]
        b = data[2 * offset + 1]
        pixels[4 * offset+1] = (a & 0b11110000) | (a & 0b11110000) >> 4
        pixels[4 * offset+2] = (a & 0b00001111) | (a & 0b00001111) << 4
        pixels[4 * offset] = (b & 0b00001111) | (b & 0b00001111) << 4
        pixels[4 * offset+3] = (b & 0b11110000) | (b & 0b11110000) >> 4


def load_bgra5551(pixels, data, width, height):
    """BGRA format, 5 bits per color plus 1 bit of alpha."""
    for offset in range(width * height):
        a = data[2 * offset]
        b = data[2 * offset + 1]
        pixels[4 * offset] = upsample(5, (b & 0b01111100) << 1)
        pixels[4 * offset+1] = upsample(5, (a & 0b11100000) >> 2 | (b & 0b00000011) << 6)
        pixels[4 * offset+2] = upsample(5, (a & 0b00011111) << 3)
        pixels[4 * offset+3] = 255 if b & 0b10000000 else 0


def load_bgrx5551(pixels, data, width, height):
    """BGR format, 5 bits per color, alpha ignored."""
    for offset in range(width * height):
        a = data[2 * offset]
        b = data[2 * offset + 1]
        pixels[4 * offset] = upsample(5, (b & 0b01111100) << 1)
        pixels[4 * offset+1] = upsample(5, (a & 0b11100000) >> 2 | (b & 0b00000011) << 6)
        pixels[4 * offset+2] = upsample(5, (a & 0b00011111) << 3)
        pixels[4 * offset+3] = 255


def load_i8(pixels, data, width, height):
    """I8 format, R=G=B"""
    for offset in range(width * height):
        pixels[4*offset] = pixels[4*offset+1] = pixels[4*offset+2] = data[offset]
        pixels[4*offset+3] = 255


def load_ia88(pixels, data, width, height):
    """I8 format, R=G=B + A"""
    for offset in range(width * height):
        pixels[4*offset] = pixels[4*offset+1] = pixels[4*offset+2] = data[2*offset]
        pixels[4*offset+3] = data[2*offset+1]


# ImageFormats.P8 is not implemented by Valve either.

def load_a8(pixels, data, width, height):
    """Single alpha bytes."""
    for offset in range(width * height):
        pixels[4*offset] = pixels[4*offset+1] = pixels[4*offset+2] = 0
        pixels[4*offset+3] = data[offset]


def load_uv88(pixels, data, width, height):
    """UV-only, which is mapped to RG."""
    for offset in range(width * height):
        pixels[4*offset] = data[2*offset]
        pixels[4*offset+1] = data[2*offset+1]
        pixels[4*offset+2] = 0
        pixels[4*offset+3] = 255


def load_rgb888_bluescreen(pixels, data, width, height):
    """RGB format, with 'bluescreen' mode for alpha.

    Pure blue pixels are transparent.
    """
    for offset in range(width * height):
        r = data[3 * offset]
        g = data[3 * offset + 1]
        b = data[3 * offset + 2]
        if r == g == 0 and b == 255:
            pixels[4*offset] = pixels[4*offset+1] = 0
            pixels[4*offset+2] = pixels[4*offset+3] = 0
        else:
            pixels[4 * offset] = r
            pixels[4 * offset + 1] = g
            pixels[4 * offset + 2] = b
            pixels[4 * offset + 3] = 255


def load_bgr888_bluescreen(pixels, data, width, height):
    """BGR format, with 'bluescreen' mode for alpha.

    Pure blue pixels are transparent.
    """
    for offset in range(width * height):
        r = data[3 * offset + 2]
        g = data[3 * offset + 1]
        b = data[3 * offset]
        if r == g == 0 and b == 255:
            pixels[4*offset] = pixels[4*offset+1] = 0
            pixels[4*offset+2] = pixels[4*offset+3] = 0
        else:
            pixels[4 * offset] = r
            pixels[4 * offset + 1] = g
            pixels[4 * offset + 2] = b
            pixels[4 * offset + 3] = 255

# Note - due to how VTFs are power of two only,
# we won't ever have partial blocks.
def load_dxt1(pixels, data, width, height):
    """Load compressed DXT1 data."""
    load_dxt1_impl(pixels, data, width, height, b'\0\0\0\xFF')


def load_dxt1_onebitalpha(pixels, data, width, height):
    """Load compressed DXT1 data, with an additional 1 bit of alpha squeezed in."""
    load_dxt1_impl(pixels, data, width, height, b'\0\0\0\0')


def load_dxt1_impl(
    pixels: array.array,
    data: bytes,
    width: int,
    height: int,
    black_color: bytes,
):
    """Does the actual decompression."""
    block_wid, mod = divmod(width, 4)
    if mod:
        block_wid += 1

    for block_y in range(0, height, 4):
        block_y //= 4
        for block_x in range(0, width, 4):
            block_x //= 4
            block_off = 8 * (block_wid * block_y + block_x)

            # First, load the 2 colors.
            c0 = c0r, c0g, c0b = decomp565(data[block_off], data[block_off+1])
            c1 = c1r, c1g, c1b = decomp565(data[block_off+2], data[block_off+3])

            # We store the lookup colors as bytes so we can directly copy them.

            # Equivalent to 16-bit comparison...
            if (
                data[block_off] > data[block_off+2] or
                data[block_off+1] > data[block_off+3]
            ):
                c2 = array.array('B', [
                    (2*c0b + c1b) // 3,
                    (2*c0g + c1g) // 3,
                    (2*c0r + c1r) // 3,
                    255
                ])
                c3 = array.array('B', [
                    (c0b + 2*c1b) // 3,
                    (c0g + 2*c1g) // 3,
                    (c0r + 2*c1r) // 3,
                    255
                ])
            else:
                c2 = array.array('B', [
                    (c0r + c1r) // 2,
                    (c0g + c1g) // 2,
                    (c0b + c1b) // 2,
                    255
                ])
                c3 = array.array('B', black_color)

            table = [
                array.array('B', bytes(c0)[::-1] + b'\xFF'),
                array.array('B', bytes(c1)[::-1] + b'\xFF'),
                c2,
                c3,
            ]
            for y in range(4):
                byte = data[block_off + 4 + y]
                row = 16*block_wid*(4*block_y+y) + 16*block_x
                pixels[row:row+4] = table[(byte & 0b11000000) >> 6]
                pixels[row+4:row+8] = table[(byte & 0b00110000) >> 4]
                pixels[row+8:row+12] = table[(byte & 0b00001100) >> 2]
                pixels[row+12:row+16] = table[byte & 0b00000011]

#
#
# def load_dxt3(pixels, data, width, height):
#     """Load compressed DXT3 data."""
#
#
# def load_dxt5(pixels, data, width, height):
#     """Load compressed DXT5 data."""



# Don't do the high-def 16-bit resolution.

# @loader(ImageFormats.RGBA16161616F)
# def load_16bit(pixels, offset, data, data_off):
#     """16-bit RGBA format - max resolution."""
#     pixels[offset] = data[data_off] << 8 + data[data_off+1]
#     pixels[offset + 1] = data[data_off+2] << 8 + data[data_off+3]
#     pixels[offset + 2] = data[data_off+4] << 8 + data[data_off+5]
#     pixels[offset + 3] = data[data_off+6] << 8 + data[data_off+7]
