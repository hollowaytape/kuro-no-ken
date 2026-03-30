SAVE_FILE_LENGTH = 0xdaa
FILE_0_OFFSET = 0xfe0
FILE_1_OFFSET = 0x18da

with open("patched/saves/A.FA1", 'rb') as f:
	f.seek(FILE_0_OFFSET)
	FILE_0 = f.read(SAVE_FILE_LENGTH)

	with open("patched/saves/BD_FLAG0.DAT", 'wb') as g:
		g.write(FILE_0)

with open("patched/saves/A.FA1", 'rb') as f:
	f.seek(FILE_1_OFFSET)
	FILE_1 = f.read(SAVE_FILE_LENGTH)

	with open("patched/saves/BD_FLAG1.DAT", 'wb') as g:
		g.write(FILE_1)

i = 0
while i < len(before):
	if FILE_0[i] == 0x5 and FILE_1[i] == 0x4:
		print(hex(i))
	i += 1