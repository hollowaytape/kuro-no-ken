"""
Kuro no Ken compression algorithm.

Compresses data using the same custom LZSS format the game uses.
See decompress.py for the full format specification.

The compressor uses a greedy match-finding approach with the following
encoding priority:
  1. Variable-length copy (length >= 3, offset 1-8192) or RLE
  2. 2-byte copy (offset 1-2304)
  3. Literal byte
"""

import os
import sys
import struct


class BitWriter:
    """
    Writes bits as 16-bit flag words interleaved with data bytes.

    Uses a single-pass approach that mirrors the decompressor's flag management:
    - Flag words are allocated lazily (only when the next bit is needed)
    - Data bytes are written at the current stream position
    - This ensures flag words appear exactly where the decompressor expects them,
      even when get_bit() triggers a flag reload before read_byte().
    """

    def __init__(self):
        self.output = bytearray()
        self.flag_pos = -1  # position of current flag word in output
        self.flag = 0       # current flag word being built (MSB-first)
        self.bits_left = 0  # bits remaining in current flag word

    def _alloc_flag(self):
        """Finalize the previous flag word and allocate a new one."""
        if self.flag_pos >= 0:
            # Pad and finalize previous flag
            self.flag <<= self.bits_left
            self.output[self.flag_pos] = self.flag & 0xFF
            self.output[self.flag_pos + 1] = (self.flag >> 8) & 0xFF
        self.flag_pos = len(self.output)
        self.output.extend([0, 0])  # placeholder for new flag word
        self.flag = 0
        self.bits_left = 16

    def write_bit(self, bit):
        """Write a single flag bit."""
        if self.bits_left == 0:
            self._alloc_flag()
        self.flag = (self.flag << 1) | (bit & 1)
        self.bits_left -= 1

    def write_byte(self, byte_val):
        """Write a data byte to the output stream."""
        if self.flag_pos < 0:
            # No flag word allocated yet — shouldn't happen in normal use,
            # but handle gracefully by allocating one
            self._alloc_flag()
        self.output.append(byte_val & 0xFF)

    def write_bits(self, bits):
        """Write multiple flag bits."""
        for b in bits:
            self.write_bit(b)

    def finish(self):
        """Finalize the last flag word and return the compressed stream."""
        if self.flag_pos >= 0:
            self.flag <<= self.bits_left
            self.output[self.flag_pos] = self.flag & 0xFF
            self.output[self.flag_pos + 1] = (self.flag >> 8) & 0xFF
        return bytes(self.output)


def _find_best_match(data, pos, window_size=8192, max_length=282):
    """Find the longest match in the sliding window."""
    if pos >= len(data):
        return 0, 0

    best_offset = 0
    best_length = 0

    # Check for RLE first (repeat of last byte)
    if pos > 0:
        rle_byte = data[pos - 1]
        rle_len = 0
        while pos + rle_len < len(data) and rle_len < max_length:
            if data[pos + rle_len] == rle_byte:
                rle_len += 1
            else:
                break
        if rle_len >= 3:
            best_offset = 0  # RLE marker
            best_length = rle_len

    # Search sliding window for longest match
    start = max(0, pos - window_size)
    remaining = len(data) - pos

    for offset_back in range(1, min(pos - start + 1, window_size + 1)):
        src = pos - offset_back
        match_len = 0
        while match_len < min(remaining, max_length):
            if data[src + match_len] == data[pos + match_len]:
                match_len += 1
            else:
                break
        if match_len > best_length or (match_len == best_length and offset_back < best_offset):
            best_offset = offset_back
            best_length = match_len

    return best_offset, best_length


def _encode_offset_bits(offset):
    """
    Determine the prefix and encoding for a given offset.

    The "00" prefix for variable-length copy is written separately by the caller.
    This function returns only the bits AFTER that "00" prefix.

    Returns (prefix_bits, byte_val, extra_bits) where:
      - prefix_bits: list of flag bits for the offset-depth prefix
      - byte_val: the stream byte to write
      - extra_bits: list of additional flag bits after the byte
    """
    if offset == 0:
        # RLE: use smallest offset encoding with ax=0
        return [1], 0, [0]

    actual = offset - 1  # stored value = offset - 1

    if actual < 0x200:
        # "001" path: 1 prefix bit after "00", B + 1 extra bit
        byte_val = (actual >> 1) & 0xFF
        extra = [actual & 1]
        return [1], byte_val, extra

    if actual < 0x400:
        # "0001" path: B + 1 extra bit, ah=1
        val = actual - 0x200
        byte_val = val >> 1
        extra = [val & 1]
        return [0, 1], byte_val, extra

    if actual < 0x800:
        # "00001" path: B + 2 extra bits, ah=1
        val = actual - 0x400
        byte_val = (val >> 2) & 0xFF
        extra = [(val >> 1) & 1, val & 1]
        return [0, 0, 1], byte_val, extra

    if actual < 0x1000:
        # "000001" path: B + 3 extra bits
        val = actual - 0x800
        byte_val = (val >> 3) & 0xFF
        extra = [(val >> 2) & 1, (val >> 1) & 1, val & 1]
        return [0, 0, 0, 1], byte_val, extra

    # "000000" path: B + 4 extra bits
    val = actual - 0x1000
    byte_val = (val >> 4) & 0xFF
    extra = [(val >> 3) & 1, (val >> 2) & 1, (val >> 1) & 1, val & 1]
    return [0, 0, 0, 0], byte_val, extra


def _encode_length_bits(length):
    """
    Encode a copy length (3-282) into flag bits and optional stream byte.

    Returns (bits, stream_byte) where stream_byte is None if not needed.
    """
    if length == 3:
        return [1], None
    if length == 4:
        return [0, 1], None
    if 5 <= length <= 6:
        val = length - 5
        return [0, 0, 1, val], None
    if 7 <= length <= 10:
        val = length - 7
        return [0, 0, 0, 1, (val >> 1) & 1, val & 1], None
    if 11 <= length <= 26:
        val = length - 11
        return [0, 0, 0, 0, 1,
                (val >> 3) & 1, (val >> 2) & 1, (val >> 1) & 1, val & 1], None
    if 27 <= length <= 282:
        # 5 zeros → decompressor falls through to read byte (no trailing "1")
        return [0, 0, 0, 0, 0], length - 27
    raise ValueError(f"Length {length} out of range 3-282")


def _cost_variable_copy(offset, length):
    """Estimate the bit cost of a variable-length copy."""
    prefix_bits, _, extra_bits = _encode_offset_bits(offset)
    len_bits, len_byte = _encode_length_bits(length)
    # 2 bits for "00" main prefix + offset depth prefix + 8 for byte + extra + length
    cost = 2 + len(prefix_bits) + 8 + len(extra_bits) + len(len_bits)
    if len_byte is not None:
        cost += 8
    return cost


def _cost_2byte_copy(offset):
    """Estimate the bit cost of a 2-byte copy."""
    if 1 <= offset <= 256:
        return 3 + 8  # "010" + byte
    elif 257 <= offset <= 2303:
        return 3 + 8 + 3  # "011" + byte + 3 bits (2304 reserved for END)
    return float('inf')


def compress(data, header_size=0):
    """
    Compress data using the Kuro no Ken compression format.

    Args:
        data: bytes of uncompressed data
        header_size: number of bytes at the start to skip (e.g. 6 for BSD/SMI
                     pre-filled header). These bytes are NOT included in the
                     compressed output.

    Returns:
        bytes of compressed data
    """
    data = data[header_size:]
    bw = BitWriter()
    pos = 0

    while pos < len(data):
        offset, match_len = _find_best_match(data, pos)

        # Decide encoding
        if match_len >= 3:
            # Variable-length copy (or RLE when offset=0)
            var_cost = _cost_variable_copy(offset, match_len)
            lit_cost = match_len * 9  # 1 bit + 8 data bits per literal

            # Check if a 2-byte copy would be sufficient
            if match_len == 3 and offset <= 2303:
                # For length 3, compare: 2-byte copy + 1 literal vs variable copy
                two_cost = _cost_2byte_copy(offset) + 9
                if two_cost < var_cost:
                    # Do 2-byte copy + literal instead
                    pass  # fall through to 2-byte check below
                else:
                    bw.write_bits([0, 0])  # "00" prefix
                    prefix_bits, byte_val, extra_bits = _encode_offset_bits(offset)
                    bw.write_bits(prefix_bits)
                    bw.write_byte(byte_val)
                    bw.write_bits(extra_bits)
                    len_bits, len_byte = _encode_length_bits(match_len)
                    bw.write_bits(len_bits)
                    if len_byte is not None:
                        bw.write_byte(len_byte)
                    pos += match_len
                    continue
            else:
                # Variable-length copy is usually better for length >= 4
                bw.write_bits([0, 0])  # "00" prefix
                prefix_bits, byte_val, extra_bits = _encode_offset_bits(offset)
                bw.write_bits(prefix_bits)
                bw.write_byte(byte_val)
                bw.write_bits(extra_bits)
                len_bits, len_byte = _encode_length_bits(match_len)
                bw.write_bits(len_bits)
                if len_byte is not None:
                    bw.write_byte(len_byte)
                pos += match_len
                continue

        if match_len >= 2 and offset >= 1:
            # 2-byte copy
            if 1 <= offset <= 256:
                # "010" encoding
                bw.write_bits([0, 1, 0])
                bw.write_byte(offset - 1)
                pos += 2
                continue
            elif 257 <= offset <= 2303:
                # "011" encoding (offset 2304 is reserved for END signal)
                ax = offset - 1 - 0x100  # remove the +256 offset
                byte_val = (ax >> 3) & 0xFF
                extra = [(ax >> 2) & 1, (ax >> 1) & 1, ax & 1]
                bw.write_bits([0, 1, 1])
                bw.write_byte(byte_val)
                bw.write_bits(extra)
                pos += 2
                continue

        # Literal byte
        bw.write_bit(1)
        bw.write_byte(data[pos])
        pos += 1

    # Write end signal: "011" path with offset >= 0x8FF, then bit 1
    # Use ax = 0x8FF (minimum end value)
    ax = 0x8FF - 0x100  # = 0x7FF
    byte_val = (ax >> 3) & 0xFF
    extra = [(ax >> 2) & 1, (ax >> 1) & 1, ax & 1]
    bw.write_bits([0, 1, 1])
    bw.write_byte(byte_val)
    bw.write_bits(extra)
    bw.write_bit(1)  # end signal (not segment management)

    return bw.finish()


def compress_file(input_path, output_path=None, header_size=0):
    """Compress a file. If output_path is None, returns the compressed bytes."""
    with open(input_path, 'rb') as f:
        data = f.read()
    result = compress(data, header_size)
    if output_path:
        with open(output_path, 'wb') as f:
            f.write(result)
    return result


if __name__ == '__main__':
    # Round-trip test: decompress → compress → decompress and compare
    from decompress import decompress, decompress_file
    import rominfo

    tested = 0
    passed = 0
    failed = 0
    errors = []
    size_stats = []  # (name, orig_comp, recomp, decomp)

    for bodfile in rominfo.FILES:
        comp_path = os.path.join('original', bodfile.name.decode())
        decomp_path = os.path.join('original', 'decompressed', bodfile.name.decode())

        if not os.path.exists(comp_path) or not os.path.exists(decomp_path):
            continue

        comp_size = os.path.getsize(comp_path)
        decomp_size = os.path.getsize(decomp_path)

        if comp_size >= decomp_size:
            continue

        name = bodfile.name.decode()

        # Use the decompressed file as ground truth (skip header for BSD/SMI)
        with open(decomp_path, 'rb') as f:
            original = f.read()

        # Determine if file has a pre-filled header
        ext = name.rsplit('.', 1)[-1].upper()
        header_size = 6 if ext in ('BSD', 'SMI') else 0

        tested += 1
        try:
            # Compress the original decompressed data
            compressed = compress(original, header_size)
            size_stats.append((name, comp_size, len(compressed), decomp_size))

            # Decompress our compressed data
            redecompressed = decompress(compressed)

            # Compare (skip the header bytes)
            expected = original[header_size:]
            if redecompressed == expected:
                passed += 1
            else:
                failed += 1
                for i in range(min(len(redecompressed), len(expected))):
                    if redecompressed[i] != expected[i]:
                        errors.append((name,
                            f"Round-trip mismatch at byte {i}: "
                            f"got 0x{redecompressed[i]:02x}, expected 0x{expected[i]:02x}"))
                        break
                else:
                    errors.append((name,
                        f"Length mismatch: got {len(redecompressed)}, "
                        f"expected {len(expected)}"))
        except Exception as e:
            failed += 1
            errors.append((name, f"EXCEPTION: {e}"))

        if tested % 50 == 0:
            print(f"  ...tested {tested} files ({passed} passed)")

    print(f"\nRound-trip results: {passed}/{tested} passed, {failed} failed")

    if size_stats:
        orig_total = sum(s[1] for s in size_stats)
        recomp_total = sum(s[2] for s in size_stats)
        decomp_total = sum(s[3] for s in size_stats)
        print(f"\nCompression stats:")
        print(f"  Original compressed total: {orig_total:,} bytes")
        print(f"  Re-compressed total:       {recomp_total:,} bytes")
        print(f"  Decompressed total:        {decomp_total:,} bytes")
        print(f"  Original ratio:  {100*orig_total/decomp_total:.1f}%")
        print(f"  Our ratio:       {100*recomp_total/decomp_total:.1f}%")

        # Show worst cases (files that grew the most)
        growth = [(n, rc/oc if oc > 0 else 99, rc, oc)
                  for n, oc, rc, _ in size_stats]
        growth.sort(key=lambda x: -x[1])
        print(f"\n  Worst compression ratios vs original:")
        for name, ratio, rc, oc in growth[:5]:
            print(f"    {name}: {oc} → {rc} ({ratio:.2f}x)")

    if errors:
        print(f"\nErrors:")
        for name, err in errors[:20]:
            print(f"  {name}: {err}")
