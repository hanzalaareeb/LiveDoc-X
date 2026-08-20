import hashlib


def calculate_hash(file):
    """Calculate a SHA-256 digest without loading the whole upload into memory."""
    sha256_hash = hashlib.sha256()

    try:
        file.seek(0)
        chunks = file.chunks()
        for byte_block in chunks:
            sha256_hash.update(byte_block)
    finally:
        file.seek(0)

    return sha256_hash.hexdigest()
