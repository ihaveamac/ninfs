

def readle(b: bytes) -> int:
    """Return little-endian bytes to an int."""
    return int.from_bytes(b, 'little')


def readbe(b: bytes) -> int:
    """Return big-endian bytes to an int."""
    return int.from_bytes(b, 'big')
