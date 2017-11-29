

# used from http://www.falatic.com/index.php/108/python-and-bitwise-rotation
# converted to def because pycodestyle complained to me
def rol(val: int, r_bits: int, max_bits: int) -> int:
    return (val << r_bits % max_bits) & (2 ** max_bits - 1) |\
           ((val & (2 ** max_bits - 1)) >> (max_bits - (r_bits % max_bits)))


def keygen(key_x: int, key_y: int) -> bytes:
    """Generate a normal key using the 3DS AES keyscrambler."""
    return rol((rol(key_x, 2, 128) ^ key_y) + 0x1FF9E9AAC5FE0408024591DC5D52768A, 87, 128).to_bytes(0x10, 'big')


def keygen_twl(key_x: int, key_y: int) -> bytes:
    # usually would convert to LE bytes in the end then flip with [::-1], but those just cancel out
    return rol((key_x ^ key_y) + 0xFFFEFB4E295902582A680F5F1A4F3E79, 42, 128).to_bytes(0x10, 'big')
