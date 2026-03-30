"""
    Analyzes the BD.BIN control code dispatch table to identify which codes
    contain pointer arguments.

    This is a lightweight wrapper around analyze_control_codes.py that prints
    a focused summary of pointer-related control codes.

    For the full dispatch table analysis, run: python analyze_control_codes.py
"""

from analyze_control_codes import analyze, get_zero_pointer_first_bytes, get_direct_pointer_codes

results = analyze()

# Mode-dispatched pointers: CC 00 ptr_lo ptr_hi
zpfb = get_zero_pointer_first_bytes(results)
print("=== Mode-dispatched pointer codes (CC 00 ptr_lo ptr_hi) ===")
print("These call 0x17b8 as first instruction; mode=0x00 means raw pointer.")
for code in zpfb:
    info = results[code]
    print("  0x%02x -> handler 0x%04x  [%db]" % (code, info['handler'], info.get('func_len', 0)))

# Direct pointer reads: CC ptr_lo ptr_hi
direct = get_direct_pointer_codes(results)
print()
print("=== Direct pointer codes (CC ptr_lo ptr_hi) ===")
print("These start with lodsw es: and read 2 bytes directly as a pointer.")
for code in direct:
    info = results[code]
    print("  0x%02x -> handler 0x%04x  [%db]  %s" % (code, info['handler'], info.get('func_len', 0), info['doc']))

# Conditional branch codes (calls 0x17d7) — these also read pointers
print()
print("=== Conditional pointer codes (calls 0x17d7) ===")
print("These follow a pointer conditionally based on flag state.")
for code, info in results.items():
    if info.get('first_call') == 0x17d7:
        print("  0x%02x -> handler 0x%04x  [%db]" % (code, info['handler'], info.get('func_len', 0)))

print()
print("ZERO_POINTER_FIRST_BYTES = %s" % zpfb)
