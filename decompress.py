"""
Kuro no Ken decompression algorithm.

Reverse-engineered from the game's decompression routine in BOD.COM
(found in memory at 0x8745-0x8b16).

The algorithm is a custom LZSS variant with Huffman-like variable-length
codes for both back-reference offsets and copy lengths.

Bit encoding (flag bits consumed MSB-first from 16-bit little-endian words):
  1           → literal byte (read 1 byte from stream)
  010 + B     → copy 2 bytes from offset (B+1), B = 1 stream byte
  011 + B + 3bits + 256 → copy 2 bytes from larger offset
                          (if offset >= 0x8FF: end signal or segment mgmt)
  001 + B + 1bit        → copy N bytes from offset (B*2 + bit + 1)
  0001 + B + 1bit       → copy N bytes from offset ((256+B)*2 + bit + 1)
  00001 + B + 2bits     → copy N bytes from offset ((256+B)*4 + 2bits + 1)
  000001 + B + 3bits    → copy N bytes from offset ((256+B)*8 + 3bits + 1)
  000000 + B + 4bits    → copy N bytes from offset ((256+B)*16 + 4bits + 1)

Length tree (for 00xxxx copy operations):
  1           → 3
  01          → 4
  001 + 1bit  → 5 + bit  (5-6)
  0001 + 2bits → 7 + val (7-10)
  00001 + 4bits → 11 + val (11-26)
  000001 → read byte from stream → byte + 27 (27-282)

Special: when offset is 0 in a variable-length copy, it's RLE
(repeat last output byte for the given length).

Note on the 6-byte pre-filled header:
  BSD files: the game writes b4 0b 5c 99 d8 16 to the output buffer before
  decompressing. SMI files: b4 0b 00 00 06 00. These headers are NOT part
  of the compressed data. Memory dumps include them, but this decompressor
  does not produce them. Use the header parameter in decompress() to prepend.
"""

import os
import sys
import struct


class BitStream:
    """Reads bits from a byte stream using 16-bit flag words."""

    def __init__(self, data):
        self.data = data
        self.pos = 0
        self.flag = 0
        self.bits_left = 0

    def _load_flag(self):
        if self.pos + 1 >= len(self.data):
            raise EOFError("Unexpected end of compressed data (loading flag)")
        self.flag = self.data[self.pos] | (self.data[self.pos + 1] << 8)
        self.pos += 2
        self.bits_left = 16

    def get_bit(self):
        """Read one bit from the flag. Returns 0 or 1."""
        if self.bits_left == 0:
            self._load_flag()
        self.bits_left -= 1
        bit = (self.flag >> 15) & 1
        self.flag = (self.flag << 1) & 0xFFFF
        return bit

    def read_byte(self):
        """Read one byte from the data stream."""
        if self.pos >= len(self.data):
            raise EOFError("Unexpected end of compressed data (reading byte)")
        b = self.data[self.pos]
        self.pos += 1
        return b


def decompress(data, expected_size=None, header=None):
    """
    Decompress data using the Kuro no Ken compression format.

    Args:
        data: bytes of compressed data
        expected_size: if known, the expected decompressed size (for validation)
        header: optional bytes to prepend to output (e.g. the 6-byte BSD/SMI
                header that the game pre-fills in memory before decompression)

    Returns:
        bytes of decompressed data (with header prepended if given)
    """
    bs = BitStream(data)
    output = bytearray()
    if header:
        output.extend(b'\x00' * len(header))

    # Load first flag word
    bs._load_flag()

    while True:
        # Main bit: 1=literal, 0=back-reference
        bit = bs.get_bit()

        if bit == 1:
            # Literal byte
            output.append(bs.read_byte())
            continue

        # Back-reference: check next bit for type
        bit = bs.get_bit()

        if bit == 1:
            # "01" prefix: 2-byte copy
            # Assembly reads bit C BEFORE the stream byte (flag reload may
            # advance the stream past a new flag word before the byte read).
            bit_c = bs.get_bit()
            ax = bs.read_byte()

            if bit_c == 0:
                # "010": short offset, copy 2
                offset = ax + 1
                src = len(output) - offset
                for _ in range(2):
                    output.append(output[src])
                    src += 1
            else:
                # "011": long offset, copy 2
                for _ in range(3):
                    ax = (ax << 1) | bs.get_bit()
                ax += 0x100

                if ax >= 0x8FF:
                    # End signal or segment management
                    bit = bs.get_bit()
                    if bit == 1:
                        # End of decompression
                        break
                    else:
                        # Segment boundary management (ignore for file decompression)
                        continue
                else:
                    offset = ax + 1
                    src = len(output) - offset
                    for _ in range(2):
                        output.append(output[src])
                        src += 1
        else:
            # "00" prefix: variable-length copy
            # Determine offset based on prefix depth
            bit = bs.get_bit()
            if bit == 1:
                # "001": short offset
                ax = bs.read_byte()  # ah=0
                extra_bits = 1
            else:
                bit = bs.get_bit()
                if bit == 1:
                    # "0001": medium offset
                    ax = 0x100 + bs.read_byte()  # ah=1
                    extra_bits = 1
                else:
                    bit = bs.get_bit()
                    if bit == 1:
                        # "00001"
                        ax = 0x100 + bs.read_byte()
                        extra_bits = 2
                    else:
                        # "000000" or "000001"
                        # Assembly reads bit before byte (same as "01" path)
                        bit = bs.get_bit()
                        byte_val = bs.read_byte()
                        ax = 0x100 + byte_val
                        if bit == 1:
                            # "000001"
                            extra_bits = 3
                        else:
                            # "000000"
                            extra_bits = 4

            # Shift extra_bits from flag into ax
            for _ in range(extra_bits):
                ax = (ax << 1) | bs.get_bit()

            # Now decode the length using the length Huffman tree
            length = _decode_length(bs)

            # Perform copy
            offset = ax + 1 if ax != 0 else 0

            if offset == 0:
                # RLE: repeat last output byte
                if len(output) > 0:
                    fill_byte = output[-1]
                else:
                    fill_byte = 0
                for _ in range(length):
                    output.append(fill_byte)
            else:
                src = len(output) - offset
                for _ in range(length):
                    output.append(output[src])
                    src += 1

    if expected_size is not None and len(output) != expected_size:
        print(f"WARNING: Expected {expected_size} bytes, got {len(output)} bytes",
              file=sys.stderr)

    return bytes(output)


def _decode_length(bs):
    """Decode copy length from the Huffman length tree."""
    bit = bs.get_bit()
    if bit == 1:
        return 3

    bit = bs.get_bit()
    if bit == 1:
        return 4

    bit = bs.get_bit()
    if bit == 1:
        # 1 more bit
        return 5 + bs.get_bit()

    bit = bs.get_bit()
    if bit == 1:
        # 2 more bits
        val = (bs.get_bit() << 1) | bs.get_bit()
        return 7 + val

    bit = bs.get_bit()
    if bit == 1:
        # 4 more bits
        val = 0
        for _ in range(4):
            val = (val << 1) | bs.get_bit()
        return 11 + val

    # Read byte from stream for length
    return bs.read_byte() + 27


def decompress_file(compressed_path, expected_size=None):
    """Decompress a file and return the decompressed bytes."""
    with open(compressed_path, 'rb') as f:
        data = f.read()
    return decompress(data, expected_size)


if __name__ == '__main__':
    # Test against known file pairs in original/ vs original/decompressed/
    import rominfo

    BSD_HEADER = b'\xb4\x0b\x5c\x99\xd8\x16'
    SMI_HEADER = b'\xb4\x0b\x00\x00\x06\x00'

    pairs_tested = 0
    exact_match = 0
    header_match = 0  # correct after accounting for pre-filled header
    runtime_mod = 0   # correct decompression, but game modified data at runtime
    exceptions = 0
    errors = []

    for bodfile in rominfo.FILES:
        comp_path = os.path.join('original', bodfile.name.decode())
        decomp_path = os.path.join('original', 'decompressed', bodfile.name.decode())

        if not os.path.exists(comp_path) or not os.path.exists(decomp_path):
            continue

        comp_size = os.path.getsize(comp_path)
        decomp_size = os.path.getsize(decomp_path)

        if comp_size >= decomp_size:
            continue

        pairs_tested += 1
        name = bodfile.name.decode()

        with open(decomp_path, 'rb') as f:
            expected = f.read()

        try:
            result = decompress_file(comp_path, len(expected))
        except Exception as e:
            exceptions += 1
            errors.append((name, f"EXCEPTION: {e}"))
            continue

        if result == expected:
            exact_match += 1
        elif len(result) == len(expected) and result[6:] == expected[6:]:
            # 6-byte header the game pre-fills in memory before decompression
            header_match += 1
        else:
            # Count differing bytes
            diffs = sum(1 for a, b in zip(result, expected) if a != b)
            runtime_mod += 1
            errors.append((name, f"{diffs} byte diffs (runtime modifications)"))

        if pairs_tested % 100 == 0:
            print(f"  ...tested {pairs_tested} files")

    total_correct = exact_match + header_match
    print(f"\nResults: {pairs_tested} files tested")
    print(f"  Exact match:        {exact_match}")
    print(f"  Header-only diff:   {header_match} (6-byte pre-filled BSD/SMI header)")
    print(f"  Runtime-modified:   {runtime_mod} (correct decompression, game modified data)")
    print(f"  Exceptions:         {exceptions}")
    print(f"  Effective accuracy: {total_correct}/{pairs_tested} "
          f"({100*total_correct/pairs_tested:.1f}%)")

    if errors:
        print(f"\nRuntime-modified / errored files:")
        for name, err in errors:
            print(f"  {name}: {err}")
