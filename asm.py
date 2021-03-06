"""
	Not just cheats, but also necessary ASM edits
"""

FILE_0_OFFSET = 0xfe0

BYTE_EDITS = {
	"BD.BIN": [
		# Item 1/2 names are misaligned. The original text was halfwidth kana,
		# so the code adds 0xd to EDI to compensate for the cursor being too short.
		# 16d8:c8de      83c70d     add di, +0d    ; change to +08

		(0xc8e0, b'\x08'),  # Align Item 1 name properly
		(0xc8fe, b'\x08'),  # Align Item 2 name properly
	],

	# Commenting these out for now, as scripted battles are acting kind of strange.
	"BD_FLAG0.DAT": [
		# Shinobu
		#(0x56e, b'\xff\xff\xff'), # Set next-level EXP to something really high
		#(0x572, b'\xff\x80'), # Set current HP to something high
		#(0x576, b'\xff\x80'), # Set total HP to something high
		#(0x57a, b'\xff\x80'), # Set current MP to something high
		#(0x57e, b'\xff\x80'), # Set total MP to something high
		#(0x580, b'\xff\x10\xff\x10'), # Set Attack to 4351
		#(0x584, b'\xff\x10\xff\x10'), # Set Defense to 4351
		#(0x58c, b'\xff\x10\xff\x10'), # Set MAtk to 4351
		#(0x58a, b'\xff\x10\xff\x10'), # Set MDef to 4351
		#(0x590, b'\xff\x10\xff\x10'), # Set Accuracy to 4351
		#(0x594, b'\xff\x10\xff\x10'), # Set Evasion to 4351
		#(0x598, b'\xff\x10\xff\x10'), # Set Speed to 4351

		# Keiuss
		#(0x458, b'\xff\xff\xff'), # Set next-level EXP to something really high
		#(0x45c, b'\xff\x80'), # Set current HP to something high
		#(0x460, b'\xff\x80'), # Set total HP to something high
		#(0x464, b'\xff\x80'), # Set current MP to something high
		#(0x468, b'\xff\x80'), # Set total MP to something high
		#(0x46c, b'\xff\x10\xff\x10'), # Set Attack to 4351
		#(0x470, b'\xff\x10\xff\x10'), # Set Defense to 4351
		#(0x474, b'\xff\x10\xff\x10'), # Set MAtk to 4351
		#(0x478, b'\xff\x10\xff\x10'), # Set MDef to 4351
		#(0x47c, b'\xff\x10\xff\x10'), # Set Accuracy to 4351
		#(0x480, b'\xff\x10\xff\x10'), # Set Evasion to 4351
		#(0x484, b'\xff\x10\xff\x10'), # Set Speed to 4351
	],

	"YSK1.MP1": [
		(0x1320, b'\xf2\x15')  # Increase the max length of 03YSK01A.SCN from 0x1562 -> 0x1800
	],

	# EXPERIMENTAL
	"OLB2.MPC": [
		(0x3431, b'\xf2\x15'),
		(0x3e94, b'\xf2\x15'),
	]
}

inventory = b''

# All items (messes up some plot flags)
#for i in range(1, 118):
#	inventory += i.to_bytes(1, 'little') + b'\x63'

# Trying something else: Powerful equipment only
for i in [1, 2, 3, 4, 40, 71, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 88, 89]:
	inventory += i.to_bytes(1, 'little') + b'\x63'

BYTE_EDITS["BD_FLAG0.DAT"].append((0x267, inventory))

shinobu_skills = b''
for i in range(1, 28):
	shinobu_skills += i.to_bytes(1, 'little') + b'\x00'

BYTE_EDITS["BD_FLAG0.DAT"].append((0x5bc, shinobu_skills))
#print(BYTE_EDITS)