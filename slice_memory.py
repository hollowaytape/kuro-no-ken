with open('memory_2b31f', 'rb') as f:
	f.seek(0x2aa80)
	with open('original/decompressed/02OLB00A.SCN', 'wb+') as g:
		g.write(f.read(0x89f))
