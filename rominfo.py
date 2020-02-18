"""
    Things related to the disk layout/structure of Kuro no Ken.
"""

import os
from romtools.disk import Disk, Gamefile
from romtools.dump import DumpExcel, PointerExcel


class BODFile:
    def __init__(self, source, name, location, compressed_length, decompressed_length):
        self.source = source
        self.name = name
        self.location = location
        self.compressed_length = compressed_length
        self.decompressed_length = decompressed_length

        self.name_no_ext, self.ext = name.split(b'/')[-1].split(b'.')

        self.original_filestring = self.get_filestring(b'original')

    def get_filestring(self, path=b'original'):
        #print(b'%s/%s' % (path, self.source))
        with open(b'%s/%s' % (path, self.source), 'rb') as f:
            #print("Reading at", hex(self.location))
            f.seek(self.location)
            contents = f.read(self.compressed_length)
        #print(contents)
        return contents

    def is_compressed(self):
        if self.name.decode('ascii') in FILES_TO_REINSERT:
            return False
        else:
            return self.compressed_length < self.decompressed_length

    def __repr__(self):
        return "BODFile(%s, %s, %s, %s, %s)," % (self.source, self.name, hex(self.location),
                                                 hex(self.compressed_length), hex(self.decompressed_length))


ORIGINAL_ROM_DIR = 'original'
SRC_DISK = 'original/Blade of Darkness (Kuro no Ken).hdi'
DEST_DISK = 'patched/Blade of Darkness (Kuro no Ken).hdi'
DUMP_XLS_PATH = 'KuroNoKen_dump.xlsx'
POINTER_XLS_PATH = 'KuroNoKen_pointer_dump.xlsx'

LINE_MAX_LENGTH = 48

ARCHIVES = [b'A.FA1', b'B.FA1', b'C.FA1', b'D.FA1', b'E.FA1']

NAMES = [b'Shinobu',
         b'Innes',
         b'Zerfuedel',
         b'Keiuss']

"""
FILES_TO_DUMP = [
    'BD.BIN', 
    'ITEM.SMI',
    'SHINOBU.SMI',
    'KIES.SMI',
    '00IPL.SCN',
    '01FLD.SCN',
    '02OLB.SCN', '02OLB00A.SCN', '02OLB01.SCN', '02OLB01A.SCN', '02OLB01B.SCN',
    '02OLB02.SCN', '02OLB02A.SCN', '02OLB03.SCN', '02OLB3A.SCN', '02OLB04.SCN', '02OLB05.SCN', '02OLB06.SCN',

    '03YSK.SCN', '03YSK00.SCN', '03YSK01A.SCN', '03YSK01B.SCN', '03YSK01C.SCN', '03YSK65.SCN', 
    '03YSK69.SCN', '03YSK690.SCN', '03YSK69A.SCN', '03YSK69B.SCN', '03YSK69C.SCN', 
    
    
    '05SKS.SCN', '05SKS01.SCN', '05SKS02.SCN', '05SKS03.SCN', '05SKS04.SCN', '05SKS05.SCN', '05SKS06.SCN', '05SKS07.SCN', '05SKS08.SCN',
    '06BLK.SCN', '06BLK00A.SCN', '06BLK00B.SCN', '06BLK01.SCN', '06BLK01A.SCN', '06BLK01B.SCN', '06BLK01C.SCN', '06BLK01D.SCN',
    '06BLK02.SCN', '06BLK02A.SCN', '06BLK02B.SCN', '06BLK02C.SCN', '06BLK02D.SCN', '06BLK02E.SCN', '06BLK02I.SCN', '06BLK02O.SCN',
    '06BLK03.SCN', '06BLK03A.SCN', '06BLK03I.SCN', '06BLK03O.SCN',
    '99CMN.SCN',
]
"""
# Definitely too many files, with incredibly annoying names, to do this manually.
FILES_TO_DUMP = os.listdir('original/decompressed')

FILES_TO_REINSERT = [
    'BD_FLAG0.DAT',
    'BD_FLAG1.DAT',
    'BD_FLAG2.DAT',
    'BD_FLAG3.DAT',
    'BD_FLAG4.DAT',
    'BD_FLAG5.DAT',
    'BD_FLAG6.DAT',
    'BD_FLAG7.DAT',
    'BD_FLAGH.DAT',
    'BD.BIN', 
    'ITEM.SMI', 
    'KIES.SMI', 
    'SHINOBU.SMI',
    '00IPL.SCN', 
    '02OLB.SCN', 
    '02OLB01.SCN', 
    '02OLB00A.SCN', 
    '02OLB01A.SCN', 
    '02OLB01B.SCN', 
    '02OLB02A.SCN', 
    '02OLB02.SCN', 
    '02OLB02A.SCN', 
    '02OLB03.SCN', 
    '02OLB04.SCN', 
    '02OLB05.SCN', 
    '02OLB06.SCN', 
    '03YSK.SCN', 
    '03YSK01A.SCN', 
    '03YSK01B.SCN', 
    #'D010_X10.BSD'
]

COMPRESSED_FILES_TO_EDIT = ['YSK1.MP1',]

#FILES_TO_REINSERT = ['BD_FLAG0.DAT', 'BD.BIN', 'ITEM.SMI', 'SHINOBU.SMI', '00IPL.SCN', '02OLB00A.SCN',
#                     '02OLB01A.SCN', '02OLB01B.SCN', '02OLB02A.SCN', '02OLB03.SCN', '02OLB03A.SCN',]

#FILES_TO_REINSERT = ['BD.BIN', 'BD_FLAG0.DAT', 'ITEM.SMI', 'SHINOBU.SMI', '00IPL.SCN', '02OLB00A.SCN',]
ARCHIVES_TO_REINSERT = ['A.FA1', 'B.FA1']

#FILES_TO_REINSERT = ['BD.BIN', 'BD_FLAG0.DAT', '00IPL.SCN', '02OLB00A.SCN', '02OLB01A.SCN', '02OLB01B.SCN', 
#                     'SHINOBU.SMI', 'ITEM.SMI']
#FILES_TO_REINSERT = ['02OLB01A.SCN',]

FILES_WITH_POINTERS = [
    'BD.BIN',
    'ITEM.SMI',
    'KIES.SMI',
    'SHINOBU.SMI',
    #'00IPL.SCN',
    #'02OLB00A.SCN',
    '02OLB01.SCN',
    '02OLB01A.SCN',
    '02OLB01B.SCN',
    '02OLB02.SCN',
    '02OLB02A.SCN',
    '02OLB03.SCN', 
    '02OLB03A.SCN',
    '02OLB04.SCN', 
    '02OLB05.SCN', 
    '02OLB06.SCN', 

    '03YSK.SCN',
    '03YSK01A.SCN',
    '03YSK01B.SCN',

    'D010_X10.BSD',
]

POINTER_CONSTANT = {
    'BD.BIN': 0,
    #'00IPL.SCN': 0,
    '02OLB01.SCN': -0x1800,
    '02OLB02.SCN': -0x1800,
    '02OLB03.SCN': -0x1800,
    '02OLB04.SCN': -0x1800,
    '02OLB05.SCN': -0x1800,
    '02OLB06.SCN': -0x1800,
    '02OLB00A.SCN': -0x3d00,
    '02OLB01A.SCN': -0x3d00,
    '02OLB01B.SCN': -0x3d00,   # Just a guess
    '02OLB02A.SCN': -0x3d00,   # Just a guess
    '02OLB03A.SCN': -0x3d00,   # Just a guess

    '03YSK01A.SCN': -0x1800,
    '03YSK01B.SCN': -0x1800,
}

# One SCN code is X, 00, text location. If X is certain values, it's a pointer. Otherwise it's something else.
# Adding 00 and 02 and 70 due to observations, they weren't in the original results
    # The 0x72 function seems to be a pointer-reading one. That adds a lot of things
ZERO_POINTER_FIRST_BYTES = [0x00, 0x02, 0x03, 0x08, 0x39, 0x3f, 0x40, 0x41, 0x43, 0x46, 0x49,
                        0x4c, 0x50, 0x50, 0x51, 0x52, 0x54, 0x55, 0x57,
                        0x5a, 0x5d, 0x5e, 0x5f, 0x60, 0x61, 0x64, 0x65,
                        0x66, 0x69, 0x6e, 0x6f, 0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7a, 0x7b, 0x7c, 0x7d, 0x7e, 0x7f, 0x8b, 0x90, 0x94, 0x99, 0x9f, 0xa0, 0xa1, 0xa4, 0xa5, 0xa7,
                        0xab, 0xaf, 0xb0, 0xb1, 0xb3, 0xb5, 0xb7, 0xbe, 0xc5, 0xcf, 0xff]
                        # TODO:  and then d6-ff. Wonder if those actually get used

FILE_BLOCKS = {

    'BD.BIN': [
        (0x9ddd, 0x9e64),
        (0x9ed2, 0x9ee2),
        (0x9f2c, 0x9f3b),
        (0x9f6b, 0x9f80),
        (0xb1e0, 0xb1f8),
        (0xba4a, 0xbc3e),
        (0xd240, 0xd28f),
        (0xd8bc, 0xd8f9),
        (0xe6f0, 0xe797),
    ],
    'KIES.SMI': [
        (0xdde, 0xe2b)
    ],
    'SHINOBU.SMI': [
        (0x10cb, 0x12e9)
    ],
    '00IPL.SCN': [
        (0x00, 0xb24)
    ],
    # Probably not necessary anymore
    '03YSK01A.SCN': [
        (0x0, 0x145d),
    ],

    #'02OLB01.SCN': [
    #    (0x432, 0x1168),
    #    (0x13b1, 0x164c)
    #],

    #'D010_X10.BSD': [
    #    (0x222, 0xd90)
    #]
}

# The locations of all strings. Testing on 02OLB01.SCN
FILE_STRING_LOCATIONS = {
    '02OLB1.SCN': [],
}

LENGTH_SENSITIVE_BLOCKS = {
    'BD.BIN': [
        (0x9ddd, 0x9e64),
        (0x9ed2, 0x9ee2),
        (0x9f2c, 0x9f3b),
        (0x9f6b, 0x9f80),
        (0xb1e0, 0xb1f8),
        (0xba4a, 0xbc3e),
        (0xd240, 0xd28f),
        (0xd8bc, 0xd8f9),
        (0xe6f0, 0xe797),
    ],
   '00IPL.SCN': [
        (0x00, 0xb24)
   ],
   #'02OLB00A.SCN': [
   #    (0x40, 0x660)
   #],
   '02OLB01.SCN': [
        (0x432, 0x1168),
   ]
}

FILES = [
    BODFile(b'A.FA1', b'FAD.BIN', 0xc, 0xfd3, 0xfd3),
    BODFile(b'A.FA1', b'BD_FLAG0.DAT', 0xfe0, 0xdaa, 0xdaa),
    BODFile(b'A.FA1', b'BD_FLAG1.DAT', 0x1d8a, 0xdaa, 0xdaa),
    BODFile(b'A.FA1', b'BD_FLAG2.DAT', 0x2b34, 0xdaa, 0xdaa),
    BODFile(b'A.FA1', b'BD_FLAG3.DAT', 0x38de, 0xdaa, 0xdaa),
    BODFile(b'A.FA1', b'BD_FLAG4.DAT', 0x4688, 0xdaa, 0xdaa),
    BODFile(b'A.FA1', b'BD_FLAG5.DAT', 0x5432, 0xdaa, 0xdaa),
    BODFile(b'A.FA1', b'BD_FLAG6.DAT', 0x61dc, 0xdaa, 0xdaa),
    BODFile(b'A.FA1', b'BD_FLAG7.DAT', 0x6f86, 0xdaa, 0xdaa),
    BODFile(b'A.FA1', b'BD_FLAGH.DAT', 0x7d30, 0x5b, 0x5b),
    BODFile(b'A.FA1', b'CF.BIN', 0x7d8c, 0x1, 0x1),
    BODFile(b'A.FA1', b'BAC_00.AS2', 0x7d8e, 0x1cbe, 0x1cbe),
    BODFile(b'A.FA1', b'BAC_01.AS2', 0x9a4c, 0x3d4c, 0x3d4c),
    BODFile(b'A.FA1', b'BAC_02.AS2', 0xd798, 0x154a, 0x154a),
    BODFile(b'A.FA1', b'BAC_03.AS2', 0xece2, 0x1e2a, 0x1e2a),
    BODFile(b'A.FA1', b'BAC_06.AS2', 0x10b0c, 0x320e, 0x320e),
    BODFile(b'A.FA1', b'BAC_07.AS2', 0x13d1a, 0x3474, 0x3474),
    BODFile(b'A.FA1', b'BAC_08.AS2', 0x1718e, 0x332a, 0x332a),
    BODFile(b'A.FA1', b'BAC_09.AS2', 0x1a4b8, 0x2c68, 0x2c68),
    BODFile(b'A.FA1', b'BAC_10.AS2', 0x1d120, 0x225e, 0x225e),
    BODFile(b'A.FA1', b'BAC_11.AS2', 0x1f37e, 0x324a, 0x324a),
    BODFile(b'A.FA1', b'BAC_99.AS2', 0x225c8, 0x4a, 0x2b6),
    BODFile(b'A.FA1', b'DS_O1.AS2', 0x22612, 0x82d6, 0x82d6),
    BODFile(b'A.FA1', b'DS_T1.AS2', 0x2a8e8, 0xf16, 0xf16),
    BODFile(b'A.FA1', b'DS_T2.AS2', 0x2b7fe, 0x6444, 0x6444),
    BODFile(b'A.FA1', b'ENIS_M5.AS2', 0x31c42, 0xa56, 0xa56),
    BODFile(b'A.FA1', b'GEIZ_M5.AS2', 0x32698, 0x99c, 0x99c),
    BODFile(b'A.FA1', b'GRIU_M5.AS2', 0x33034, 0x838, 0x838),
    BODFile(b'A.FA1', b'HIKO_M5.AS2', 0x3386c, 0xb1a, 0xb1a),
    BODFile(b'A.FA1', b'KIES_M5.AS2', 0x34386, 0xb5c, 0xb5c),
    BODFile(b'A.FA1', b'KIES_STS.AS2', 0x34ee2, 0x1408, 0x1408),
    BODFile(b'A.FA1', b'KING_M5.AS2', 0x362ea, 0xa94, 0xa94),
    BODFile(b'A.FA1', b'MERF_M5.AS2', 0x36d7e, 0xd16, 0xd16),
    BODFile(b'A.FA1', b'RIEL_M5.AS2', 0x37a94, 0xb1c, 0xb1c),
    BODFile(b'A.FA1', b'SAN2_M5.AS2', 0x385b0, 0xbc6, 0xbc6),
    BODFile(b'A.FA1', b'SAN3_M5.AS2', 0x39176, 0xdc2, 0xdc2),
    BODFile(b'A.FA1', b'SANA_M5.AS2', 0x39f38, 0x734, 0x734),
    BODFile(b'A.FA1', b'SINO_M5.AS2', 0x3a66c, 0x91c, 0x91c),
    BODFile(b'A.FA1', b'SINO_STS.AS2', 0x3af88, 0x10da, 0x10da),
    BODFile(b'A.FA1', b'TCHO_M5.AS2', 0x3c062, 0x9ac, 0x9ac),
    BODFile(b'A.FA1', b'WICH_M5.AS2', 0x3ca0e, 0xd42, 0xd42),
    BODFile(b'A.FA1', b'ZEFY_M5.AS2', 0x3d750, 0xcbc, 0xcbc),
    BODFile(b'A.FA1', b'_ITEM_AI.BCA', 0x3e40c, 0x4b7, 0x6b9),
    BODFile(b'A.FA1', b'_ITEM_ET.BCA', 0x3e8c4, 0x32c, 0x57b),
    BODFile(b'A.FA1', b'_ITEM_KD.BCA', 0x3ebf0, 0x1270, 0x1f29),
    BODFile(b'A.FA1', b'_KK_HA.BCA', 0x3fe60, 0xabd, 0x1cca),
    BODFile(b'A.FA1', b'_KK_JI.BCA', 0x4091e, 0x9ca, 0x17f8),
    BODFile(b'A.FA1', b'_KK_MZ.BCA', 0x412e8, 0x75c, 0x106d),
    BODFile(b'A.FA1', b'_KK_NU.BCA', 0x41a44, 0x1890, 0x290d),
    BODFile(b'A.FA1', b'_KK_OR.BCA', 0x432d4, 0x16bf, 0x27df),
    BODFile(b'A.FA1', b'_KK_SR.BCA', 0x44994, 0x28cb, 0x53c4),
    BODFile(b'A.FA1', b'_KK_SS.BCA', 0x47260, 0x204a, 0x3d8a),
    BODFile(b'A.FA1', b'_KK_SSE.BCA', 0x492aa, 0x1ff2, 0x3ca1),
    BODFile(b'A.FA1', b'_KK_TA.BCA', 0x4b29c, 0x1e96, 0x371f),
    BODFile(b'A.FA1', b'_KK_TO.BCA', 0x4d132, 0x604, 0xb6b),
    BODFile(b'A.FA1', b'_KK_TU.BCA', 0x4d736, 0x16e, 0x29d),
    BODFile(b'A.FA1', b'_MG_BS.BCA', 0x4d8a4, 0x672, 0xb99),
    BODFile(b'A.FA1', b'_MG_DM.BCA', 0x4df16, 0x294, 0x45d),
    BODFile(b'A.FA1', b'_MG_EF.BCA', 0x4e1aa, 0xa1c, 0x114e),
    BODFile(b'A.FA1', b'_MG_FC.BCA', 0x4ebc6, 0x4f9, 0x7ca),
    BODFile(b'A.FA1', b'_MG_HL.BCA', 0x4f0c0, 0xb5e, 0x15ab),
    BODFile(b'A.FA1', b'_MG_IW.BCA', 0x4fc1e, 0x92b, 0x10db),
    BODFile(b'A.FA1', b'_MG_QU.BCA', 0x5054a, 0x1fb, 0x590),
    BODFile(b'A.FA1', b'_MG_RF.BCA', 0x50746, 0x4aa, 0xd8c),
    BODFile(b'A.FA1', b'_MG_RS.BCA', 0x50bf0, 0x372, 0x951),
    BODFile(b'A.FA1', b'_MG_SB.BCA', 0x50f62, 0x219, 0x3a5),
    BODFile(b'A.FA1', b'_MG_SF.BCA', 0x5117c, 0x80a, 0xbde),
    BODFile(b'A.FA1', b'_MG_SL.BCA', 0x51986, 0x1f1, 0x59c),
    BODFile(b'A.FA1', b'_MG_SR.BCA', 0x51b78, 0x620, 0xff3),
    BODFile(b'A.FA1', b'_MG_SS.BCA', 0x52198, 0x410, 0x6b4),
    BODFile(b'A.FA1', b'_MG_SW.BCA', 0x525a8, 0x1eb, 0x36f),
    BODFile(b'A.FA1', b'_MG_TP.BCA', 0x52794, 0x81b, 0xea0),
    BODFile(b'A.FA1', b'_MGE_BL.BCA', 0x52fb0, 0x66a, 0xf45),
    BODFile(b'A.FA1', b'_MGE_CF.BCA', 0x5361a, 0x737, 0xce4),
    BODFile(b'A.FA1', b'_MGE_DC.BCA', 0x53d52, 0x3d3, 0x645),
    BODFile(b'A.FA1', b'_MGE_DS.BCA', 0x54126, 0x5ee, 0xfce),
    BODFile(b'A.FA1', b'_MGE_HL.BCA', 0x54714, 0x2a5, 0x677),
    BODFile(b'A.FA1', b'_MGE_MP.BCA', 0x549ba, 0x7d2, 0xb4b),
    BODFile(b'A.FA1', b'_MGE_MS.BCA', 0x5518c, 0x9e0, 0x1438),
    BODFile(b'A.FA1', b'_MGE_NM.BCA', 0x55b6c, 0x296, 0x463),
    BODFile(b'A.FA1', b'_MGE_RF.BCA', 0x55e02, 0x464, 0xcae),
    BODFile(b'A.FA1', b'_MGE_RM.BCA', 0x56266, 0x81c, 0xfb8),
    BODFile(b'A.FA1', b'_MGE_SC.BCA', 0x56a82, 0x376, 0x952),
    BODFile(b'A.FA1', b'_MGE_SF.BCA', 0x56df8, 0xfb, 0x17d),
    BODFile(b'A.FA1', b'_MGE_SW.BCA', 0x56ef4, 0x1e8, 0x370),
    BODFile(b'A.FA1', b'_S_OFUDA.BCA', 0x570dc, 0x318, 0x486),
    BODFile(b'A.FA1', b'_SHO_BE.BCA', 0x573f4, 0x20ac, 0x3532),
    BODFile(b'A.FA1', b'_SHO_FD.BCA', 0x594a0, 0x385d, 0x6d49),
    BODFile(b'A.FA1', b'_SHO_FJ.BCA', 0x5ccfe, 0x26a3, 0x5b2a),
    BODFile(b'A.FA1', b'_SHO_KJ.BCA', 0x5f3a2, 0x207b, 0x4b08),
    BODFile(b'A.FA1', b'_SHO_RJ.BCA', 0x6141e, 0x2c2f, 0x6816),
    BODFile(b'A.FA1', b'_SHO_VA.BCA', 0x6404e, 0x2777, 0x4f2f),
    BODFile(b'A.FA1', b'_SHOE_DA.BCA', 0x667c6, 0x25ed, 0x4b2e),
    BODFile(b'A.FA1', b'_SHOE_DD.BCA', 0x68db4, 0x268a, 0x56f4),
    BODFile(b'A.FA1', b'_SHOE_KD.BCA', 0x6b43e, 0x127f, 0x1f32),
    BODFile(b'A.FA1', b'_SHOE_TH.BCA', 0x6c6be, 0x2cf7, 0x6816),
    BODFile(b'A.FA1', b'_ZK_GA.BCA', 0x6f3b6, 0x2a16, 0x5912),
    BODFile(b'A.FA1', b'_ZK_GF.BCA', 0x71dcc, 0x1ec1, 0x4c16),
    BODFile(b'A.FA1', b'_ZK_HG.BCA', 0x73c8e, 0x914, 0x1890),
    BODFile(b'A.FA1', b'_ZK_MZ.BCA', 0x745a2, 0xb55, 0x1cc9),
    BODFile(b'A.FA1', b'_ZK_OR.BCA', 0x750f8, 0x2a75, 0x4b8d),
    BODFile(b'A.FA1', b'_ZK_SS.BCA', 0x77b6e, 0x1c07, 0x3d3f),
    BODFile(b'A.FA1', b'_ZK_ZB.BCA', 0x79776, 0x2fff, 0x56d6),
    BODFile(b'A.FA1', b'BAT2.BCA', 0x7c776, 0x673, 0xde1),
    BODFile(b'A.FA1', b'COMMON.BCA', 0x7cdea, 0x15da, 0x2f64),
    BODFile(b'A.FA1', b'DOLUID.BCA', 0x7e3c4, 0x19e6, 0x2be3),
    BODFile(b'A.FA1', b'FKIES.BCA', 0x7fdaa, 0xc7b, 0x1116),
    BODFile(b'A.FA1', b'FRUTIA.BCA', 0x80a26, 0xcb3, 0x10b6),
    BODFile(b'A.FA1', b'FSHINOBU.BCA', 0x816da, 0xa24, 0xf26),
    BODFile(b'A.FA1', b'GOBLIN2.BCA', 0x820fe, 0x1589, 0x23a0),
    BODFile(b'A.FA1', b'HARPY2.BCA', 0x83688, 0x2d28, 0x4c84),
    BODFile(b'A.FA1', b'KIES.BCA', 0x863b0, 0xc1f2, 0x13e6b),
    BODFile(b'A.FA1', b'SHINOBU.BCA', 0x925a2, 0x7c81, 0xe7d4),
    BODFile(b'A.FA1', b'SKELET1.BCA', 0x9a224, 0x416e, 0x69c7),
    BODFile(b'A.FA1', b'SLIME1.BCA', 0x9e392, 0x1842, 0x2d03),
    BODFile(b'A.FA1', b'SLIME2.BCA', 0x9fbd4, 0x17d9, 0x2d03),
    BODFile(b'A.FA1', b'SLIME3.BCA', 0xa13ae, 0x158b, 0x2d03),
    BODFile(b'A.FA1', b'SLIME4.BCA', 0xa293a, 0x13ee, 0x2d03),
    BODFile(b'A.FA1', b'SPIRIT2.BCA', 0xa3d28, 0x16ce, 0x331e),
    BODFile(b'A.FA1', b'WOLF.BCA', 0xa53f6, 0x1ed6, 0x31bc),
    BODFile(b'A.FA1', b'WYARM.BCA', 0xa72cc, 0x1f3a, 0x3a36),
    BODFile(b'A.FA1', b'WYARM_I.BCA', 0xa9206, 0x1f37, 0x3a3f),
    BODFile(b'A.FA1', b'_CK.BIN', 0xab13e, 0x28, 0xe6),
    BODFile(b'A.FA1', b'_CS.BIN', 0xab166, 0x28, 0xe6),
    BODFile(b'A.FA1', b'_PK.BIN', 0xab18e, 0x15, 0xf5),
    BODFile(b'A.FA1', b'_PS.BIN', 0xab1a4, 0x16, 0xf5),
    BODFile(b'A.FA1', b'AYUMI.BIN', 0xab1ba, 0x715, 0xe8a),
    BODFile(b'A.FA1', b'BD.BIN', 0xab8d0, 0x8c52, 0xfd70),
    BODFile(b'A.FA1', b'GAIJI.BIN', 0xb4522, 0x20e, 0x3dc),
    BODFile(b'A.FA1', b'IPL.BIN', 0xb4730, 0x1a8, 0x368),
    BODFile(b'A.FA1', b'LOGO.BIN', 0xb48d8, 0x289, 0x812),
    BODFile(b'A.FA1', b'MB3N.BIN', 0xb4b62, 0x13e5, 0x3f49),
    BODFile(b'A.FA1', b'S20S_2.BIN', 0xb5f48, 0x1505, 0x2163),
    BODFile(b'A.FA1', b'D091_S10.BSD', 0xb744e, 0x2e6, 0x567),
    BODFile(b'A.FA1', b'F011_I01.BSD', 0xb7734, 0x11e, 0x21b),
    BODFile(b'A.FA1', b'F013_A32.BSD', 0xb7852, 0x118, 0x221),
    BODFile(b'A.FA1', b'F013_B12.BSD', 0xb796a, 0x173, 0x351),
    BODFile(b'A.FA1', b'F013_C10.BSD', 0xb7ade, 0x11c, 0x21d),
    BODFile(b'A.FA1', b'F014_B22.BSD', 0xb7bfa, 0x178, 0x351),
    BODFile(b'A.FA1', b'F014_K11.BSD', 0xb7d72, 0x171, 0x351),
    BODFile(b'A.FA1', b'F014_K21.BSD', 0xb7ee4, 0x172, 0x351),
    BODFile(b'A.FA1', b'F015_B32.BSD', 0xb8056, 0x171, 0x351),
    BODFile(b'A.FA1', b'F015_C12.BSD', 0xb81c8, 0x11c, 0x21d),
    BODFile(b'A.FA1', b'F015_K32.BSD', 0xb82e4, 0x174, 0x351),
    BODFile(b'A.FA1', b'F024_A22.BSD', 0xb8458, 0x139, 0x34f),
    BODFile(b'A.FA1', b'F024_D20.BSD', 0xb8592, 0x113, 0x223),
    BODFile(b'A.FA1', b'F024_K22.BSD', 0xb86a6, 0x193, 0x353),
    BODFile(b'A.FA1', b'F025_A12.BSD', 0xb883a, 0x139, 0x34f),
    BODFile(b'A.FA1', b'F025_A20.BSD', 0xb8974, 0x139, 0x34f),
    BODFile(b'A.FA1', b'F025_B02.BSD', 0xb8aae, 0x192, 0x353),
    BODFile(b'A.FA1', b'F025_C02.BSD', 0xb8c40, 0x180, 0x355),
    BODFile(b'A.FA1', b'F025_D10.BSD', 0xb8dc0, 0x114, 0x223),
    BODFile(b'A.FA1', b'F025_K12.BSD', 0xb8ed4, 0x192, 0x353),
    BODFile(b'A.FA1', b'F031_K22.BSD', 0xb9066, 0x199, 0x351),
    BODFile(b'A.FA1', b'F032_D02.BSD', 0xb9200, 0x199, 0x351),
    BODFile(b'A.FA1', b'F033_B22.BSD', 0xb939a, 0x127, 0x21f),
    BODFile(b'A.FA1', b'F033_C12.BSD', 0xb94c2, 0x11f, 0x21f),
    BODFile(b'A.FA1', b'F036_A22.BSD', 0xb95e2, 0x12f, 0x223),
    BODFile(b'A.FA1', b'F036_C20.BSD', 0xb9712, 0x11f, 0x21f),
    BODFile(b'A.FA1', b'F03D_K32.BSD', 0xb9832, 0x198, 0x351),
    BODFile(b'A.FA1', b'F03E_D12.BSD', 0xb99ca, 0x130, 0x221),
    BODFile(b'A.FA1', b'AKAGE.MCA', 0xb9afa, 0xdb6, 0x1754),
    BODFile(b'A.FA1', b'BABA.MCA', 0xba8b0, 0x8a2, 0x1004),
    BODFile(b'A.FA1', b'BOTCHAN.MCA', 0xbb152, 0x9be, 0x11d4),
    BODFile(b'A.FA1', b'CHRBAKU2.MCA', 0xbbb10, 0x10bb, 0x2d56),
    BODFile(b'A.FA1', b'DEAD.MCA', 0xbcbcc, 0x1c89, 0x2db4),
    BODFile(b'A.FA1', b'DEAD2.MCA', 0xbe856, 0xacd, 0x1188),
    BODFile(b'A.FA1', b'DOG.MCA', 0xbf324, 0x669, 0xb94),
    BODFile(b'A.FA1', b'ENIS.MCA', 0xbf98e, 0xd0c, 0x15d4),
    BODFile(b'A.FA1', b'GAGOIL.MCA', 0xc069a, 0x2a6, 0x3da),
    BODFile(b'A.FA1', b'GAKUSHA1.MCA', 0xc0940, 0xbec, 0x17b4),
    BODFile(b'A.FA1', b'GAKUSHA2.MCA', 0xc152c, 0xb4a, 0x1694),
    BODFile(b'A.FA1', b'GEIZ.MCA', 0xc2076, 0xdc4, 0x1834),
    BODFile(b'A.FA1', b'GOBLIN.MCA', 0xc2e3a, 0xac5, 0x131e),
    BODFile(b'A.FA1', b'GOFU.MCA', 0xc3900, 0x16f, 0x262),
    BODFile(b'A.FA1', b'GOREM.MCA', 0xc3a70, 0x46e, 0x562),
    BODFile(b'A.FA1', b'GRINURDO.MCA', 0xc3ede, 0xddb, 0x1a60),
    BODFile(b'A.FA1', b'HAKA.MCA', 0xc4cba, 0x1e9, 0x35e),
    BODFile(b'A.FA1', b'HARPY.MCA', 0xc4ea4, 0xb85, 0x1484),
    BODFile(b'A.FA1', b'HEISI.MCA', 0xc5a2a, 0xc68, 0x16b4),
    BODFile(b'A.FA1', b'HIGE.MCA', 0xc6692, 0xede, 0x196c),
    BODFile(b'A.FA1', b'HIKO.MCA', 0xc7570, 0xd27, 0x18f4),
    BODFile(b'A.FA1', b'HONE.MCA', 0xc8298, 0x27f, 0x3f2),
    BODFile(b'A.FA1', b'IWA.MCA', 0xc8518, 0x2bd, 0x3fe),
    BODFile(b'A.FA1', b'JIJI.MCA', 0xc87d6, 0xbf2, 0x1594),
    BODFile(b'A.FA1', b'JOCHAN.MCA', 0xc93c8, 0xb17, 0x1454),
    BODFile(b'A.FA1', b'KIES.MCA', 0xc9ee0, 0x1908, 0x26bc),
    BODFile(b'A.FA1', b'KIZOKU_F.MCA', 0xcb7e8, 0xd13, 0x1634),
    BODFile(b'A.FA1', b'KIZOKU_M.MCA', 0xcc4fc, 0xcb6, 0x1614),
    BODFile(b'A.FA1', b'KYUPI.MCA', 0xcd1b2, 0xbec, 0x1634),
    BODFile(b'A.FA1', b'LIVING_M.MCA', 0xcdd9e, 0x267, 0x408),
    BODFile(b'A.FA1', b'MADOSI1.MCA', 0xce006, 0xb68, 0x1794),
    BODFile(b'A.FA1', b'MADOSI2.MCA', 0xceb6e, 0xdaf, 0x1814),
    BODFile(b'A.FA1', b'MADOSI3.MCA', 0xcf91e, 0xd7d, 0x1834),
    BODFile(b'A.FA1', b'MADOSI4.MCA', 0xd069c, 0xd19, 0x1794),
    BODFile(b'A.FA1', b'MERFINA.MCA', 0xd13b6, 0xa91, 0x12d4),
    BODFile(b'A.FA1', b'MIMIC.MCA', 0xd1e48, 0x365, 0x5b0),
    BODFile(b'A.FA1', b'OBASAN.MCA', 0xd21ae, 0xdd5, 0x1694),
    BODFile(b'A.FA1', b'OSAMA.MCA', 0xd2f84, 0xcf1, 0x17b4),
    BODFile(b'A.FA1', b'OYAJI.MCA', 0xd3c76, 0xbdd, 0x15b4),
    BODFile(b'A.FA1', b'PONYTAIL.MCA', 0xd4854, 0xe76, 0x1a4c),
    BODFile(b'A.FA1', b'REEL.MCA', 0xd56ca, 0xdfd, 0x1794),
    BODFile(b'A.FA1', b'SANSITO2.MCA', 0xd64c8, 0xd4e, 0x192c),
    BODFile(b'A.FA1', b'SANSITO3.MCA', 0xd7216, 0x1061, 0x1994),
    BODFile(b'A.FA1', b'SHINOBU.MCA', 0xd8278, 0x165c, 0x26c8),
    BODFile(b'A.FA1', b'SKELETON.MCA', 0xd98d4, 0x24f, 0x400),
    BODFile(b'A.FA1', b'SOKKIN.MCA', 0xd9b24, 0x8fe, 0x1234),
    BODFile(b'A.FA1', b'TAICHO.MCA', 0xda422, 0xf6f, 0x1984),
    BODFile(b'A.FA1', b'TAICHO_O.MCA', 0xdb392, 0xcdf, 0x17ac),
    BODFile(b'A.FA1', b'TOROL.MCA', 0xdc072, 0x115a, 0x1b2c),
    BODFile(b'A.FA1', b'WAKAMONO.MCA', 0xdd1cc, 0xd93, 0x16b4),
    BODFile(b'A.FA1', b'WARP.MCA', 0xddf60, 0x3ba, 0xc1a),
    BODFile(b'A.FA1', b'WICH.MCA', 0xde31a, 0x1285, 0x1f9c),
    BODFile(b'A.FA1', b'WYBERN.MCA', 0xdf5a0, 0x362, 0x638),
    BODFile(b'A.FA1', b'YOROI.MCA', 0xdf902, 0xcd0, 0x18e4),
    BODFile(b'A.FA1', b'ZEFYUDOL.MCA', 0xe05d2, 0xef5, 0x18d4),
    BODFile(b'A.FA1', b'FLD1.MP1', 0xe14c8, 0x2573, 0x901a),
    BODFile(b'A.FA1', b'FLD2.MP1', 0xe3a3c, 0x25d3, 0x901a),
    BODFile(b'A.FA1', b'FLD1.MPC', 0xe6010, 0x4726, 0x9d08),
    BODFile(b'A.FA1', b'FLD2.MPC', 0xea736, 0x4726, 0x9d08),
    BODFile(b'A.FA1', b'MK01.PAI', 0xeee5c, 0x865, 0x1639),
    BODFile(b'A.FA1', b'MK02.PAI', 0xef6c2, 0x8f5, 0x11e5),
    BODFile(b'A.FA1', b'MK03.PAI', 0xeffb8, 0xa90, 0x1718),
    BODFile(b'A.FA1', b'MK04.PAI', 0xf0a48, 0x684, 0xe87),
    BODFile(b'A.FA1', b'MK05.PAI', 0xf10cc, 0xa83, 0x1ded),
    BODFile(b'A.FA1', b'MK06.PAI', 0xf1b50, 0x5dc, 0x1106),
    BODFile(b'A.FA1', b'MK07.PAI', 0xf212c, 0x11c, 0x1ab),
    BODFile(b'A.FA1', b'MK08.PAI', 0xf2248, 0x361, 0x933),
    BODFile(b'A.FA1', b'MK09.PAI', 0xf25aa, 0xa0a, 0x17df),
    BODFile(b'A.FA1', b'MK10.PAI', 0xf2fb4, 0xa77, 0x1fc8),
    BODFile(b'A.FA1', b'MK11.PAI', 0xf3a2c, 0x370, 0x1230),
    BODFile(b'A.FA1', b'MK12.PAI', 0xf3d9c, 0x811, 0x1246),
    BODFile(b'A.FA1', b'MK13.PAI', 0xf45ae, 0x6d1, 0x1543),
    BODFile(b'A.FA1', b'MK14.PAI', 0xf4c80, 0xabb, 0x1731),
    BODFile(b'A.FA1', b'MK15.PAI', 0xf573c, 0x5bf, 0xb56),
    BODFile(b'A.FA1', b'MK16.PAI', 0xf5cfc, 0xa66, 0x12e9),
    BODFile(b'A.FA1', b'MK17.PAI', 0xf6762, 0x9f9, 0x16ed),
    BODFile(b'A.FA1', b'MK18.PAI', 0xf715c, 0x244, 0x3da),
    BODFile(b'A.FA1', b'MK19.PAI', 0xf73a0, 0x242, 0x809),
    BODFile(b'A.FA1', b'MK20.PAI', 0xf75e2, 0x31a, 0x80e),
    BODFile(b'A.FA1', b'MK21.PAI', 0xf78fc, 0x45e, 0x901),
    BODFile(b'A.FA1', b'MK22.PAI', 0xf7d5a, 0x85c, 0x16af),
    BODFile(b'A.FA1', b'MK23.PAI', 0xf85b6, 0x695, 0xd7e),
    BODFile(b'A.FA1', b'MK24.PAI', 0xf8c4c, 0x5f2, 0x11be),
    BODFile(b'A.FA1', b'MK25.PAI', 0xf923e, 0x5cc, 0x1215),
    BODFile(b'A.FA1', b'MK26.PAI', 0xf980a, 0x6a6, 0xdf7),
    BODFile(b'A.FA1', b'MK27.PAI', 0xf9eb0, 0x5fe, 0xc2b),
    BODFile(b'A.FA1', b'MK28.PAI', 0xfa4ae, 0x4e4, 0xab1),
    BODFile(b'A.FA1', b'MK29.PAI', 0xfa992, 0x5a3, 0xb9e),
    BODFile(b'A.FA1', b'MK30.PAI', 0xfaf36, 0x422, 0xad1),
    BODFile(b'A.FA1', b'MK31.PAI', 0xfb358, 0x56e, 0xbfa),
    BODFile(b'A.FA1', b'MK32.PAI', 0xfb8c6, 0x823, 0x1538),
    BODFile(b'A.FA1', b'MK33.PAI', 0xfc0ea, 0x2a8, 0x65a),
    BODFile(b'A.FA1', b'MK34.PAI', 0xfc392, 0xa5, 0xd2),
    BODFile(b'A.FA1', b'MK35.PAI', 0xfc438, 0x908, 0x1a6c),
    BODFile(b'A.FA1', b'MK36.PAI', 0xfcd40, 0x98, 0xc0),
    BODFile(b'A.FA1', b'MK37.PAI', 0xfcdd8, 0x396, 0x1146),
    BODFile(b'A.FA1', b'MK38.PAI', 0xfd16e, 0x342, 0x603),
    BODFile(b'A.FA1', b'MK39.PAI', 0xfd4b0, 0x9e, 0xdc),
    BODFile(b'A.FA1', b'MK40.PAI', 0xfd54e, 0x13c, 0x202),
    BODFile(b'A.FA1', b'MK99.PAI', 0xfd68a, 0x96, 0xba),
    BODFile(b'A.FA1', b'EK.PIP', 0xfd720, 0x80c, 0x10e5),
    BODFile(b'A.FA1', b'00IPL.SCN', 0xfdf2c, 0xaa2, 0x147d),  #
    BODFile(b'A.FA1', b'01FLD.SCN', 0xfe9ce, 0x674, 0x11b8),  #
    BODFile(b'A.FA1', b'99CMN.SCN', 0xff042, 0x830, 0xcc1),  #
    BODFile(b'A.FA1', b'BAT.SMI', 0xff872, 0x114, 0x265),
    BODFile(b'A.FA1', b'DOLUID.SMI', 0xff986, 0x2fa, 0x756),
    BODFile(b'A.FA1', b'GOBLIN2.SMI', 0xffc80, 0xe9, 0x255),
    BODFile(b'A.FA1', b'HARPY.SMI', 0xffd6a, 0x116, 0x241),
    BODFile(b'A.FA1', b'ITEM.SMI', 0xffe80, 0x1858, 0x4092),  # 2e8a0-32932, dumped
    BODFile(b'A.FA1', b'KIES.SMI', 0x1016d8, 0x645, 0xe3a),  # dumped
    BODFile(b'A.FA1', b'SHINOBU.SMI', 0x101d1e, 0x7dd, 0x12e9),  # 34850-ish
    BODFile(b'A.FA1', b'SKELET1.SMI', 0x1024fc, 0x10d, 0x270),
    BODFile(b'A.FA1', b'SLIME1.SMI', 0x10260a, 0x224, 0x69a),
    BODFile(b'A.FA1', b'SLIME2.SMI', 0x10282e, 0x24e, 0x6e8),
    BODFile(b'A.FA1', b'SLIME3.SMI', 0x102a7c, 0x2fb, 0x738),
    BODFile(b'A.FA1', b'SPIRIT2.SMI', 0x102d78, 0x2bf, 0x69c),
    BODFile(b'A.FA1', b'UNITY.SMI', 0x103038, 0x15fe, 0x2a1e),
    BODFile(b'A.FA1', b'WOLF.SMI', 0x104636, 0x128, 0x2c8),
    BODFile(b'A.FA1', b'WYARM.SMI', 0x10475e, 0x11a, 0x265),

    BODFile(b'B.FA1', b'BAC_15.AS2', 0xc, 0x2f6e, 0x2f6e),
    BODFile(b'B.FA1', b'DS_01A.AS2', 0x2f7a, 0x61de, 0x61de),
    BODFile(b'B.FA1', b'DS_01B.AS2', 0x9158, 0x29d2, 0x29d2),
    BODFile(b'B.FA1', b'DS_03.AS2', 0xbb2a, 0x5a08, 0x5a08),
    BODFile(b'B.FA1', b'DS_16.AS2', 0x11532, 0x47ce, 0x47ce),
    BODFile(b'B.FA1', b'DS_17.AS2', 0x15d00, 0x58e0, 0x58e0),
    BODFile(b'B.FA1', b'DS_20.AS2', 0x1b5e0, 0x614c, 0x614c),
    BODFile(b'B.FA1', b'MAJI_M5.AS2', 0x2172c, 0x7a6, 0x7a6),
    BODFile(b'B.FA1', b'ADON.BCA', 0x21ed2, 0xd82, 0x15a9),
    BODFile(b'B.FA1', b'BAT1.BCA', 0x22c54, 0x625, 0xda1),
    BODFile(b'B.FA1', b'CAPTAIN.BCA', 0x2327a, 0x9229, 0xf581),
    BODFile(b'B.FA1', b'DANGO1.BCA', 0x2c4a4, 0xff7, 0x1f8c),
    BODFile(b'B.FA1', b'DVL_EYE3.BCA', 0x2d49c, 0xfea, 0x1cde),
    BODFile(b'B.FA1', b'DVL_EYE5.BCA', 0x2e486, 0xf9e, 0x1cde),
    BODFile(b'B.FA1', b'FSINI.BCA', 0x2f424, 0x9b7, 0x1096),
    BODFile(b'B.FA1', b'FWICH.BCA', 0x2fddc, 0xd00, 0x1096),
    BODFile(b'B.FA1', b'FZEFYUDO.BCA', 0x30adc, 0xb84, 0x1056),
    BODFile(b'B.FA1', b'G_STONE.BCA', 0x31660, 0x724, 0xdf7),
    BODFile(b'B.FA1', b'GOBLIN1.BCA', 0x31d84, 0x1570, 0x2320),
    BODFile(b'B.FA1', b'GOLEM2.BCA', 0x332f4, 0x4597, 0x72f3),
    BODFile(b'B.FA1', b'J_FISH2.BCA', 0x3788c, 0x25e3, 0x37ec),
    BODFile(b'B.FA1', b'KNIGHT3.BCA', 0x39e70, 0x2ce5, 0x5348),
    BODFile(b'B.FA1', b'KNIGHT4S.BCA', 0x3cb56, 0xdac, 0x3276),
    BODFile(b'B.FA1', b'L_MAIL1.BCA', 0x3d902, 0x22aa, 0x49c4),
    BODFile(b'B.FA1', b'LOBSTER3.BCA', 0x3fbac, 0x19b9, 0x2b58),
    BODFile(b'B.FA1', b'MD_ROCK1.BCA', 0x41566, 0x118b, 0x22ab),
    BODFile(b'B.FA1', b'MIMIC1.BCA', 0x426f2, 0x1d58, 0x32aa),
    BODFile(b'B.FA1', b'MIMIC2.BCA', 0x4444a, 0x1e61, 0x32aa),
    BODFile(b'B.FA1', b'NUE3.BCA', 0x462ac, 0x3442, 0x5f56),
    BODFile(b'B.FA1', b'SAMSON.BCA', 0x496ee, 0x3888, 0x5a32),
    BODFile(b'B.FA1', b'SKELET1S.BCA', 0x4cf76, 0x1838, 0x57c7),
    BODFile(b'B.FA1', b'SOLDIE1.BCA', 0x4e7ae, 0x358d, 0x5d03),
    BODFile(b'B.FA1', b'SOLDIE2.BCA', 0x51d3c, 0x3522, 0x5cc3),
    BODFile(b'B.FA1', b'SPIDER1.BCA', 0x5525e, 0x2e1d, 0x4926),
    BODFile(b'B.FA1', b'SPIRIT1.BCA', 0x5807c, 0x1ac8, 0x331e),
    BODFile(b'B.FA1', b'TOROL1.BCA', 0x59b44, 0x7b23, 0xb53a),
    BODFile(b'B.FA1', b'TOROL2.BCA', 0x61668, 0x7778, 0xb53a),
    BODFile(b'B.FA1', b'TURTLE1.BCA', 0x68de0, 0x23ac, 0x461e),
    BODFile(b'B.FA1', b'VII.BCA', 0x6b18c, 0x430e, 0x936d),
    BODFile(b'B.FA1', b'WICH.BCA', 0x6f49a, 0x36ca, 0x6910),
    BODFile(b'B.FA1', b'WIZARD2S.BCA', 0x72b64, 0xcc4, 0x2adb),
    BODFile(b'B.FA1', b'WIZARD3.BCA', 0x73828, 0x214d, 0x45db),
    BODFile(b'B.FA1', b'YUMIHEI2.BCA', 0x75976, 0x16eb, 0x26a5),
    BODFile(b'B.FA1', b'ZEFYUDOR.BCA', 0x77062, 0xa1dd, 0x12a94),
    BODFile(b'B.FA1', b'D010_S20.BSD', 0x81240, 0x1be, 0x351), # ($) two soldiers
    BODFile(b'B.FA1', b'D010_X10.BSD', 0x813fe, 0x5e1, 0xd91), # (*) Zerfuedel battle
    BODFile(b'B.FA1', b'D011_A20.BSD', 0x819e0, 0x183, 0x35b),     # two knights
    BODFile(b'B.FA1', b'D011_B02.BSD', 0x81b64, 0x183, 0x35b),     # two guys with arrow guns
    BODFile(b'B.FA1', b'D011_I10.BSD', 0x81ce8, 0x114, 0x21f),     # mimic
    BODFile(b'B.FA1', b'D011_K12.BSD', 0x81dfc, 0x183, 0x35b),     # knight, two arrow gun guys
    BODFile(b'B.FA1', b'D011_K22.BSD', 0x81f80, 0x183, 0x35b),     # 2 knights 2 arrow guns
    BODFile(b'B.FA1', b'D011_S20.BSD', 0x82104, 0x1cf, 0x357),     # two soldiers
    BODFile(b'B.FA1', b'D011_T20.BSD', 0x822d4, 0x1d4, 0x357),     # two soldiers
    BODFile(b'B.FA1', b'D011_U20.BSD', 0x824a8, 0x1e0, 0x35b),     # two knights
    BODFile(b'B.FA1', b'D011_X10.BSD', 0x82688, 0x1eb, 0x35d),     # captain who likes to kick
    BODFile(b'B.FA1', b'D020_A12.BSD', 0x82874, 0x11f, 0x21b),     # bat
    BODFile(b'B.FA1', b'D020_A22.BSD', 0x82994, 0x11e, 0x21b),     # 2 bats
    BODFile(b'B.FA1', b'D020_A32.BSD', 0x82ab2, 0x120, 0x21b), # 2 more bats
    BODFile(b'B.FA1', b'D020_B02.BSD', 0x82bd2, 0x126, 0x223), # 2 fire guys
    BODFile(b'B.FA1', b'D020_B12.BSD', 0x82cf8, 0x123, 0x223), # 1 fire guy
    BODFile(b'B.FA1', b'D020_S10.BSD', 0x82e1c, 0x122, 0x223), # pill bug
    BODFile(b'B.FA1', b'D030_B10.BSD', 0x82f3e, 0x119, 0x223), # turtle
    BODFile(b'B.FA1', b'D030_B20.BSD', 0x83058, 0x117, 0x223), # 2 turtles
    BODFile(b'B.FA1', b'D030_S10.BSD', 0x83170, 0x11b, 0x223), # lobster
    BODFile(b'B.FA1', b'D031_S10.BSD', 0x8328c, 0x114, 0x221), # 2 soldiers
    BODFile(b'B.FA1', b'D070_A12.BSD', 0x833a0, 0x11b, 0x225), # 3 shadow skeletons
    BODFile(b'B.FA1', b'D070_A22.BSD', 0x834bc, 0x11c, 0x225), # 4 shadow skeletons
    BODFile(b'B.FA1', b'D070_B02.BSD', 0x835d8, 0x163, 0x355), # 2 shadow cloak guys
    BODFile(b'B.FA1', b'D070_C10.BSD', 0x8373c, 0x11e, 0x21d), # manticore
    BODFile(b'B.FA1', b'D070_C20.BSD', 0x8385a, 0x11e, 0x21d), # 2 manticores
    BODFile(b'B.FA1', b'D070_K22.BSD', 0x83978, 0x163, 0x355), # 2 skeletons 2 cloak guys
    BODFile(b'B.FA1', b'D070_S10.BSD', 0x83adc, 0x11d, 0x223), # shield halberd guy
    BODFile(b'B.FA1', b'D070_T10.BSD', 0x83bfa, 0x11d, 0x223), # shield halberd guy
    BODFile(b'B.FA1', b'D100_A10.BSD', 0x83d18, 0x11b, 0x221), # golem
    BODFile(b'B.FA1', b'D100_A20.BSD', 0x83e34, 0x11b, 0x221), # 2 golems
    BODFile(b'B.FA1', b'D100_B02.BSD', 0x83f50, 0x19d, 0x357), # moon mage
    BODFile(b'B.FA1', b'D100_C12.BSD', 0x840ee, 0x139, 0x357), # blue and red eyes
    BODFile(b'B.FA1', b'D100_C22.BSD', 0x84228, 0x139, 0x357), # 2 red eyes
    BODFile(b'B.FA1', b'D100_I10.BSD', 0x84362, 0x112, 0x21f), # red mimic
    BODFile(b'B.FA1', b'D100_J10.BSD', 0x84474, 0x115, 0x21f), # brown mimic
    BODFile(b'B.FA1', b'D100_K12.BSD', 0x8458a, 0x19e, 0x357), # 2 moon mages
    BODFile(b'B.FA1', b'D100_K22.BSD', 0x84728, 0x19d, 0x357), # moon mage, 2 golem
    BODFile(b'B.FA1', b'D100_Q10.BSD', 0x848c6, 0x125, 0x227), # armored gnome
    BODFile(b'B.FA1', b'D100_R10.BSD', 0x849ec, 0x124, 0x225), # jelly rock
    BODFile(b'B.FA1', b'D100_S10.BSD', 0x84b10, 0x122, 0x223), # giant spider
    BODFile(b'B.FA1', b'D100_U10.BSD', 0x84c32, 0x11d, 0x221), # ghost armor
    BODFile(b'B.FA1', b'D100_W10.BSD', 0x84d50, 0x117, 0x223), # tombstone
    BODFile(b'B.FA1', b'D100_X01.BSD', 0x84e68, 0x241, 0x48d), # (*) magician girl summons Cho Aniki
    BODFile(b'B.FA1', b'D100_X02.BSD', 0x850aa, 0x41c, 0x869), # (*) " " bigger Cho Aniki
    BODFile(b'B.FA1', b'D100_ZA1.BSD', 0x854c6, 0x1d6, 0x34f), # small dragon
    BODFile(b'B.FA1', b'D100_ZA2.BSD', 0x8569c, 0x1dd, 0x353), # jellyfish
    BODFile(b'B.FA1', b'D100_ZA3.BSD', 0x8587a, 0x1d8, 0x34f), # harpy
    BODFile(b'B.FA1', b'D100_ZA4.BSD', 0x85a52, 0x1d3, 0x351), # caveman
    BODFile(b'B.FA1', b'D100_ZA5.BSD', 0x85c26, 0x1d2, 0x34d), # manticore
    BODFile(b'B.FA1', b'D100_ZA6.BSD', 0x85df8, 0x1cd, 0x353), # skeleton knight
    BODFile(b'B.FA1', b'D100_ZA7.BSD', 0x85fc6, 0x283, 0x491), # slime
    BODFile(b'B.FA1', b'DL21_X10.BSD', 0x8624a, 0x381, 0x63f), # (*) grim reaper
    BODFile(b'B.FA1', b'F011_A10.BSD', 0x865cc, 0x116, 0x221), # slime
    BODFile(b'B.FA1', b'F011_A20.BSD', 0x866e2, 0x114, 0x221), # 2 slime
    BODFile(b'B.FA1', b'F011_B10.BSD', 0x867f6, 0x177, 0x355), # gnome
    BODFile(b'B.FA1', b'F012_A12.BSD', 0x8696e, 0x117, 0x221), # 2 slime
    BODFile(b'B.FA1', b'F012_A30.BSD', 0x86a86, 0x117, 0x221), # 3 slime
    BODFile(b'B.FA1', b'F012_B20.BSD', 0x86b9e, 0x17a, 0x355), # gnome
    BODFile(b'B.FA1', b'F022_D12.BSD', 0x86d18, 0x112, 0x223), # 3 skeleton knights
    BODFile(b'B.FA1', b'F023_A32.BSD', 0x86e2a, 0x138, 0x34f), # 2 red slime
    BODFile(b'B.FA1', b'F023_L12.BSD', 0x86f62, 0x17f, 0x355), # 2 skeleton knights, something really dumb looking
    BODFile(b'B.FA1', b'F023_L22.BSD', 0x870e2, 0x17f, 0x355), # "" but spread out more
    BODFile(b'B.FA1', b'F033_D10.BSD', 0x87262, 0x19f, 0x351), # black slime
    BODFile(b'B.FA1', b'F036_B12.BSD', 0x87402, 0x126, 0x21f), # 3 harpies
    BODFile(b'B.FA1', b'BAKUHATU.MCA', 0x87528, 0x925, 0x1474),
    BODFile(b'B.FA1', b'EBI.MCA', 0x87e4e, 0x3c0, 0x520),
    BODFile(b'B.FA1', b'KIZOKU_T.MCA', 0x8820e, 0x242, 0x44a),
    BODFile(b'B.FA1', b'MADOSI5.MCA', 0x88450, 0xc26, 0x1794),
    BODFile(b'B.FA1', b'MRS.MP1', 0x89076, 0xc7e, 0x8f3e),
    BODFile(b'B.FA1', b'OLB2.MP1', 0x89cf4, 0x1773, 0x9010),
    BODFile(b'B.FA1', b'OLD.MP1', 0x8b468, 0x144a, 0x8f8e),
    BODFile(b'B.FA1', b'SLP.MP1', 0x8c8b2, 0x12af, 0x9006),
    BODFile(b'B.FA1', b'STG.MP1', 0x8db62, 0x11d7, 0x8f84),
    BODFile(b'B.FA1', b'TNI1.MP1', 0x8ed3a, 0x1624, 0x8f3e),
    BODFile(b'B.FA1', b'TNI2.MP1', 0x9035e, 0x138b, 0x8f48),
    BODFile(b'B.FA1', b'TOU1A.MP1', 0x916ea, 0x1561, 0x8f98),
    BODFile(b'B.FA1', b'TOU1B.MP1', 0x92c4c, 0x12b0, 0x8fa2),
    BODFile(b'B.FA1', b'TOU2A.MP1', 0x93efc, 0x1c55, 0x9196),
    BODFile(b'B.FA1', b'TOU2B.MP1', 0x95b52, 0x1bd2, 0x9196),
    BODFile(b'B.FA1', b'TOU3A.MP1', 0x97724, 0x1d98, 0x931c),
    BODFile(b'B.FA1', b'TOU3B.MP1', 0x994bc, 0x1d1d, 0x931c),
    BODFile(b'B.FA1', b'TOU4A.MP1', 0x9b1da, 0x174c, 0x90c4),
    BODFile(b'B.FA1', b'TOU4B.MP1', 0x9c926, 0x16aa, 0x90c4),
    BODFile(b'B.FA1', b'TOU5.MP1', 0x9dfd0, 0xb50, 0x9100),
    BODFile(b'B.FA1', b'TOU6.MP1', 0x9eb20, 0xd22, 0x8f48),
    BODFile(b'B.FA1', b'YSK1.MP1', 0x9f842, 0x163f, 0x8f3e),
    BODFile(b'B.FA1', b'YSK2.MP1', 0xa0e82, 0x1f02, 0x9092),
    BODFile(b'B.FA1', b'OLB1.MP2', 0xa2d84, 0x21dd, 0x90ec),
    BODFile(b'B.FA1', b'MRS.MPC', 0xa4f62, 0x33ab, 0x5780),
    BODFile(b'B.FA1', b'OLB1.MPC', 0xa830e, 0x515d, 0x9268),
    BODFile(b'B.FA1', b'OLB2.MPC', 0xad46c, 0x4a3b, 0x8818),
    BODFile(b'B.FA1', b'OLD.MPC', 0xb1ea8, 0x446f, 0x8ef8),
    BODFile(b'B.FA1', b'SLP.MPC', 0xb6318, 0x3c44, 0x7f30),
    BODFile(b'B.FA1', b'STG.MPC', 0xb9f5c, 0x37e1, 0x7260),
    BODFile(b'B.FA1', b'TNI1.MPC', 0xbd73e, 0x506d, 0x9ba0),
    BODFile(b'B.FA1', b'TNI2.MPC', 0xc27ac, 0x2a0f, 0x6568),
    BODFile(b'B.FA1', b'TOU1A.MPC', 0xc51bc, 0x2ba8, 0x9830),
    BODFile(b'B.FA1', b'TOU1B.MPC', 0xc7d64, 0x46bc, 0x7fd0),
    BODFile(b'B.FA1', b'TOU2A.MPC', 0xcc420, 0x4f8b, 0x9510),
    BODFile(b'B.FA1', b'TOU2B.MPC', 0xd13ac, 0x4eee, 0x9510),
    BODFile(b'B.FA1', b'TOU3A.MPC', 0xd629a, 0x4f8b, 0x9510),
    BODFile(b'B.FA1', b'TOU3B.MPC', 0xdb226, 0x4eee, 0x9510),
    BODFile(b'B.FA1', b'TOU4A.MPC', 0xe0114, 0x4f8b, 0x9510),
    BODFile(b'B.FA1', b'TOU4B.MPC', 0xe50a0, 0x4eee, 0x9510),
    BODFile(b'B.FA1', b'TOU5.MPC', 0xe9f8e, 0x1332, 0x3e08),
    BODFile(b'B.FA1', b'TOU6.MPC', 0xeb2c0, 0x3c44, 0x7f30),
    BODFile(b'B.FA1', b'YSK1.MPC', 0xeef04, 0x58a2, 0x9da8),
    BODFile(b'B.FA1', b'YSK2.MPC', 0xf47a6, 0x53a7, 0x9f38),
    BODFile(b'B.FA1', b'02OLB.SCN', 0xf9b4e, 0x555, 0x9c8),  #
    BODFile(b'B.FA1', b'02OLB00A.SCN', 0xfa0a4, 0x4e0, 0x89f),  # dumped
    BODFile(b'B.FA1', b'02OLB01.SCN', 0xfa584, 0xb7a, 0x1653),  # redumped
    BODFile(b'B.FA1', b'02OLB01A.SCN', 0xfb0fe, 0x944, 0x1083),  # dumped
    BODFile(b'B.FA1', b'02OLB01B.SCN', 0xfba42, 0x886, 0xe6c),  # dumped
    BODFile(b'B.FA1', b'02OLB02.SCN', 0xfc2c8, 0x57e, 0x869),   # redumped
    BODFile(b'B.FA1', b'02OLB02A.SCN', 0xfc846, 0x9a0, 0x1131),  #
    BODFile(b'B.FA1', b'02OLB03.SCN', 0xfd1e6, 0x6c1, 0xa4e),  # redumped
    BODFile(b'B.FA1', b'02OLB03A.SCN', 0xfd8a8, 0xa16, 0x1263),  #
    BODFile(b'B.FA1', b'02OLB04.SCN', 0xfe2be, 0x3c2, 0x5cf),  # redumped
    BODFile(b'B.FA1', b'02OLB05.SCN', 0xfe680, 0x3ba, 0x5b9),  # redumped
    BODFile(b'B.FA1', b'02OLB06.SCN', 0xfea3a, 0x310, 0x4c1),  # redumped
    BODFile(b'B.FA1', b'03YSK.SCN', 0xfed4a, 0x709, 0xcf4),  #
    BODFile(b'B.FA1', b'03YSK00.SCN', 0xff454, 0xaa, 0xf8),  # R
    BODFile(b'B.FA1', b'03YSK01A.SCN', 0xff4fe, 0xb83, 0x145e),  #
    BODFile(b'B.FA1', b'03YSK01B.SCN', 0x100082, 0x9db, 0x1091),  #
    BODFile(b'B.FA1', b'03YSK01C.SCN', 0x100a5e, 0x172, 0x204),  #
    BODFile(b'B.FA1', b'03YSK65.SCN', 0x100bd0, 0xf1, 0x12c),  # Redumped
    BODFile(b'B.FA1', b'03YSK69.SCN', 0x100cc2, 0xcc9, 0x169c),  # R
    BODFile(b'B.FA1', b'03YSK690.SCN', 0x10198c, 0x1fc, 0x31f),  #
    BODFile(b'B.FA1', b'03YSK69A.SCN', 0x101b88, 0x856, 0xe45),  #
    BODFile(b'B.FA1', b'03YSK69B.SCN', 0x1023de, 0x52b, 0x839),  #
    BODFile(b'B.FA1', b'03YSK69C.SCN', 0x10290a, 0x416, 0x69e),  #
    BODFile(b'B.FA1', b'03YSK69D.SCN', 0x102d20, 0x673, 0xbb3),  #
    BODFile(b'B.FA1', b'03YSK70.SCN', 0x103394, 0x74b, 0xc2f),  # R
    BODFile(b'B.FA1', b'04OLD.SCN', 0x103ae0, 0x1d0, 0x2e1),  #
    BODFile(b'B.FA1', b'04OLD01A.SCN', 0x103cb0, 0x71b, 0xb13),  #
    BODFile(b'B.FA1', b'04OLD01B.SCN', 0x1043cc, 0x1ea, 0x259),  #
    BODFile(b'B.FA1', b'04OLD01C.SCN', 0x1045b6, 0x206, 0x289),  #
    BODFile(b'B.FA1', b'04OLD01D.SCN', 0x1047bc, 0x10f, 0x142),  #
    BODFile(b'B.FA1', b'10TNI.SCN', 0x1048cc, 0x317, 0x547),  #
    BODFile(b'B.FA1', b'10TNI01.SCN', 0x104be4, 0x1dc, 0x29e),  #
    BODFile(b'B.FA1', b'10TNI01A.SCN', 0x104dc0, 0x1cf, 0x2fc),  #
    BODFile(b'B.FA1', b'10TNI02.SCN', 0x104f90, 0x285, 0x3b8),  #
    BODFile(b'B.FA1', b'10TNI02A.SCN', 0x105216, 0xff, 0x154),  #
    BODFile(b'B.FA1', b'10TNI03.SCN', 0x105316, 0x280, 0x3ac),  #
    BODFile(b'B.FA1', b'10TNI03A.SCN', 0x105596, 0x5a5, 0xb03),  #
    BODFile(b'B.FA1', b'10TNI04.SCN', 0x105b3c, 0x1d2, 0x258),  #
    BODFile(b'B.FA1', b'10TNI04A.SCN', 0x105d0e, 0x3f8, 0x627),  #
    BODFile(b'B.FA1', b'10TNII00.SCN', 0x106106, 0x247, 0x405),  #
    BODFile(b'B.FA1', b'10TNII01.SCN', 0x10634e, 0x395, 0x64f),  #
    BODFile(b'B.FA1', b'10TNII02.SCN', 0x1066e4, 0x217, 0x395),  #
    BODFile(b'B.FA1', b'11STG.SCN', 0x1068fc, 0x220, 0x361),  #
    BODFile(b'B.FA1', b'11STG01.SCN', 0x106b1c, 0x2af, 0x3cc),  #
    BODFile(b'B.FA1', b'12MRS.SCN', 0x106dcc, 0x5e1, 0x91f),  #
    BODFile(b'B.FA1', b'13SLP.SCN', 0x1073ae, 0x597, 0x96c),  #
    BODFile(b'B.FA1', b'25TOU.SCN', 0x107946, 0x1b27, 0x2d7c),  #
    BODFile(b'B.FA1', b'25TOU00A.SCN', 0x10946e, 0x3cf, 0x797),  #
    BODFile(b'B.FA1', b'25TOU00B.SCN', 0x10983e, 0x723, 0xcc1),  #
    BODFile(b'B.FA1', b'25TOU00C.SCN', 0x109f62, 0x75b, 0xe87),  #
    BODFile(b'B.FA1', b'25TOU00D.SCN', 0x10a6be, 0x79f, 0xf50),  #
    BODFile(b'B.FA1', b'25TOU00E.SCN', 0x10ae5e, 0x41c, 0x7fa),  #
    BODFile(b'B.FA1', b'ADON.SMI', 0x10b27a, 0x137, 0x2bf),
    BODFile(b'B.FA1', b'CAPTAIN2.SMI', 0x10b3b2, 0x2a4, 0x5d9),
    BODFile(b'B.FA1', b'DANGO1_G.SMI', 0x10b656, 0x118, 0x273),
    BODFile(b'B.FA1', b'DVL_EYE2.SMI', 0x10b76e, 0x15b, 0x3a8),
    BODFile(b'B.FA1', b'DVL_EYE3.SMI', 0x10b8ca, 0x15b, 0x3a8),
    BODFile(b'B.FA1', b'G_STONE1.SMI', 0x10ba26, 0x15e, 0x3de),
    BODFile(b'B.FA1', b'GOBLIN1.SMI', 0x10bb84, 0xe9, 0x255),
    BODFile(b'B.FA1', b'GOBLIN3.SMI', 0x10bc6e, 0xea, 0x255),
    BODFile(b'B.FA1', b'GOLEM2.SMI', 0x10bd58, 0x13b, 0x28f),
    BODFile(b'B.FA1', b'J_FISH2.SMI', 0x10be94, 0x192, 0x361),
    BODFile(b'B.FA1', b'KNIGHT3.SMI', 0x10c026, 0x10a, 0x26a),
    BODFile(b'B.FA1', b'KNIGHT4.SMI', 0x10c130, 0x10a, 0x26a),
    BODFile(b'B.FA1', b'L_MAIL.SMI', 0x10c23a, 0x102, 0x25b),
    BODFile(b'B.FA1', b'LOBSTERG.SMI', 0x10c33c, 0xe0, 0x20b),
    BODFile(b'B.FA1', b'MD_ROCK3.SMI', 0x10c41c, 0x143, 0x297),
    BODFile(b'B.FA1', b'MIMIC.SMI', 0x10c560, 0x10f, 0x23d),
    BODFile(b'B.FA1', b'NUE3.SMI', 0x10c670, 0x177, 0x353),
    BODFile(b'B.FA1', b'SAMSON.SMI', 0x10c7e8, 0x1c6, 0x3f0),
    BODFile(b'B.FA1', b'SKELET1S.SMI', 0x10c9ae, 0x113, 0x270),
    BODFile(b'B.FA1', b'SOLDIE1.SMI', 0x10cac2, 0x112, 0x270),
    BODFile(b'B.FA1', b'SOLDIE2.SMI', 0x10cbd4, 0x113, 0x270),
    BODFile(b'B.FA1', b'SPIDER1.SMI', 0x10cce8, 0x16b, 0x30b),
    BODFile(b'B.FA1', b'SPIRIT1.SMI', 0x10ce54, 0x2bc, 0x69c),
    BODFile(b'B.FA1', b'TOROL1.SMI', 0x10d110, 0x146, 0x295),
    BODFile(b'B.FA1', b'TOROL2.SMI', 0x10d256, 0x149, 0x295),
    BODFile(b'B.FA1', b'TURTLE1.SMI', 0x10d3a0, 0x151, 0x2ad),
    BODFile(b'B.FA1', b'VII.SMI', 0x10d4f2, 0x392, 0x88e),
    BODFile(b'B.FA1', b'WICH1__G.SMI', 0x10d884, 0x362, 0x86f),
    BODFile(b'B.FA1', b'WIZARD2.SMI', 0x10dbe6, 0x4bd, 0xcd4),
    BODFile(b'B.FA1', b'WIZARD3.SMI', 0x10e0a4, 0x4bd, 0xcd4),
    BODFile(b'B.FA1', b'YUMIHEI.SMI', 0x10e562, 0xd3, 0x201),
    BODFile(b'B.FA1', b'ZEFYU1.SMI', 0x10e636, 0x4a1, 0xb85),

    BODFile(b'C.FA1', b'BAC_16.AS2', 0xc, 0x2e88, 0x2e88),
    BODFile(b'C.FA1', b'DS_02.AS2', 0x2e94, 0x49c0, 0x49c0),
    BODFile(b'C.FA1', b'DS_02A0.AS2', 0x7854, 0x25cc, 0x25cc),
    BODFile(b'C.FA1', b'DS_02A1.AS2', 0x9e20, 0x2c8, 0x2c8),
    BODFile(b'C.FA1', b'DS_04.AS2', 0xa0e8, 0x6a00, 0x6a00),
    BODFile(b'C.FA1', b'DS_05.AS2', 0x10ae8, 0x4b5c, 0x4b5c),
    BODFile(b'C.FA1', b'DS_06.AS2', 0x15644, 0x4a1c, 0x4a1c),
    BODFile(b'C.FA1', b'DS_06A.AS2', 0x1a060, 0x21d4, 0x21d4),
    BODFile(b'C.FA1', b'DS_07.AS2', 0x1c234, 0x300c, 0x300c),
    BODFile(b'C.FA1', b'DS_08.AS2', 0x1f240, 0x2bfe, 0x2bfe),
    BODFile(b'C.FA1', b'DS_08A.AS2', 0x21e3e, 0x3cda, 0x3cda),
    BODFile(b'C.FA1', b'DS_12.AS2', 0x25b18, 0x2704, 0x2704),
    BODFile(b'C.FA1', b'DS_14.AS2', 0x2821c, 0x4644, 0x4644),
    BODFile(b'C.FA1', b'DS_14A.AS2', 0x2c860, 0x3372, 0x3372),
    BODFile(b'C.FA1', b'DS_15.AS2', 0x2fbd2, 0x3f4c, 0x3f4c),
    BODFile(b'C.FA1', b'DS_15A.AS2', 0x33b1e, 0x3812, 0x3812),
    BODFile(b'C.FA1', b'DS_15M.AS2', 0x37330, 0x1f9, 0x2fc),
    BODFile(b'C.FA1', b'DS_21.AS2', 0x3752a, 0x5648, 0x5648),
    BODFile(b'C.FA1', b'SA_1_M5.AS2', 0x3cb72, 0xd88, 0xd88),
    BODFile(b'C.FA1', b'SAN1_M5.AS2', 0x3d8fa, 0xcb0, 0xcb0),
    BODFile(b'C.FA1', b'BAT1.BCA', 0x3e5aa, 0x625, 0xda1),
    BODFile(b'C.FA1', b'CAPTAIN.BCA', 0x3ebd0, 0x9229, 0xf581),
    BODFile(b'C.FA1', b'DVL_EYE1.BCA', 0x47dfa, 0xfa4, 0x1cde),
    BODFile(b'C.FA1', b'DVL_EYE2.BCA', 0x48d9e, 0xf60, 0x1cde),
    BODFile(b'C.FA1', b'FNUE.BCA', 0x49cfe, 0xa71, 0xf06),
    BODFile(b'C.FA1', b'FZEFYUDO.BCA', 0x4a770, 0xb84, 0x1056),
    BODFile(b'C.FA1', b'GOBLIN1.BCA', 0x4b2f4, 0x1570, 0x2320),
    BODFile(b'C.FA1', b'GOLEM3.BCA', 0x4c864, 0x4c56, 0x72f3),
    BODFile(b'C.FA1', b'KNIGHT1.BCA', 0x514ba, 0x2e33, 0x4da6),
    BODFile(b'C.FA1', b'KNIGHT2.BCA', 0x542ee, 0x3217, 0x4f96),
    BODFile(b'C.FA1', b'KNIGHT3.BCA', 0x57506, 0x2ce5, 0x5348),
    BODFile(b'C.FA1', b'KNIGHT4.BCA', 0x5a1ec, 0x28c7, 0x4f76),
    BODFile(b'C.FA1', b'L_MAIL1.BCA', 0x5cab4, 0x22aa, 0x49c4),
    BODFile(b'C.FA1', b'MD_ROCK2.BCA', 0x5ed5e, 0x126e, 0x22ab),
    BODFile(b'C.FA1', b'MD_ROCK3.BCA', 0x5ffcc, 0x1289, 0x22ab),
    BODFile(b'C.FA1', b'NUE1.BCA', 0x61256, 0x3c5b, 0x6016),
    BODFile(b'C.FA1', b'NUE2.BCA', 0x64eb2, 0x3d51, 0x6027),
    BODFile(b'C.FA1', b'S_WARM1.BCA', 0x68c04, 0x78d8, 0xb8bb),
    BODFile(b'C.FA1', b'S_WARM2.BCA', 0x704dc, 0x7aa8, 0xb89b),
    BODFile(b'C.FA1', b'SOLDIE1.BCA', 0x77f84, 0x358d, 0x5d03),
    BODFile(b'C.FA1', b'SOLDIE2.BCA', 0x7b512, 0x3522, 0x5cc3),
    BODFile(b'C.FA1', b'SOLDIE2S.BCA', 0x7ea34, 0x12fb, 0x45d3),
    BODFile(b'C.FA1', b'SPIRIT1.BCA', 0x7fd30, 0x1ac8, 0x331e),
    BODFile(b'C.FA1', b'TOROL3.BCA', 0x817f8, 0x7a92, 0xb5da),
    BODFile(b'C.FA1', b'WIZARD1.BCA', 0x8928a, 0x22ac, 0x457b),
    BODFile(b'C.FA1', b'WIZARD2.BCA', 0x8b536, 0x26e8, 0x46eb),
    BODFile(b'C.FA1', b'YUMIHEI1.BCA', 0x8dc1e, 0x16d0, 0x2685),
    BODFile(b'C.FA1', b'ZEFYUDOR.BCA', 0x8f2ee, 0xa1dd, 0x12a94),
    BODFile(b'C.FA1', b'ZOMBIE1.BCA', 0x994cc, 0x2178, 0x3274),
    BODFile(b'C.FA1', b'C020_A01.BSD', 0x9b644, 0x196, 0x355), # blue mage
    BODFile(b'C.FA1', b'C020_X10.BSD', 0x9b7da, 0x1da, 0x357), # captain guy who likes to kick
    BODFile(b'C.FA1', b'C021_A10.BSD', 0x9b9b4, 0x132, 0x231), # stone armor guy
    BODFile(b'C.FA1', b'C021_X10.BSD', 0x9bae6, 0x7f0, 0x11fb), # (*) Zerfeudel again
    BODFile(b'C.FA1', b'C022_S10.BSD', 0x9c2d6, 0x1e5, 0x35b), # pitchfork guy
    BODFile(b'C.FA1', b'C022_S20.BSD', 0x9c4bc, 0x1e4, 0x35b), # 2 pitchfork guys
    BODFile(b'C.FA1', b'C022_T10.BSD', 0x9c6a0, 0x1ce, 0x351), # caveman
    BODFile(b'C.FA1', b'D040_A12.BSD', 0x9c86e, 0x11e, 0x21b), # 2 bats
    BODFile(b'C.FA1', b'D040_A22.BSD', 0x9c98c, 0x11f, 0x21b), # 3 bats
    BODFile(b'C.FA1', b'D040_A32.BSD', 0x9caac, 0x11f, 0x21b), # 4 bats
    BODFile(b'C.FA1', b'D040_B02.BSD', 0x9cbcc, 0x126, 0x223), # skittish fire
    BODFile(b'C.FA1', b'D040_B12.BSD', 0x9ccf2, 0x123, 0x223), # skittish fire
    BODFile(b'C.FA1', b'D040_S10.BSD', 0x9ce16, 0x1d2, 0x355), # jelly rock
    BODFile(b'C.FA1', b'D050_A20.BSD', 0x9cfe8, 0x185, 0x357), # soldier
    BODFile(b'C.FA1', b'D050_A30.BSD', 0x9d16e, 0x183, 0x357), # 2 soldiers
    BODFile(b'C.FA1', b'D050_B01.BSD', 0x9d2f2, 0x184, 0x357), # blue mage
    BODFile(b'C.FA1', b'D050_B02.BSD', 0x9d476, 0x181, 0x357), # another blue mage
    BODFile(b'C.FA1', b'D050_K12.BSD', 0x9d5f8, 0x182, 0x357), # blue mage + soldier
    BODFile(b'C.FA1', b'D050_K22.BSD', 0x9d77a, 0x181, 0x357), # blue  mage + 2 soldiers
    BODFile(b'C.FA1', b'D050_K32.BSD', 0x9d8fc, 0x182, 0x357), # 2 blue mage + soldier
    BODFile(b'C.FA1', b'D050_S10.BSD', 0x9da7e, 0x1ce, 0x34d), # manticore
    BODFile(b'C.FA1', b'D050_T01.BSD', 0x9dc4c, 0x1cd, 0x353), # soldier
    BODFile(b'C.FA1', b'D050_T02.BSD', 0x9de1a, 0x1d2, 0x353), # soldier
    BODFile(b'C.FA1', b'D051_A10.BSD', 0x9dfec, 0x18f, 0x361), # arrow guy + soldier
    BODFile(b'C.FA1', b'D051_B20.BSD', 0x9e17c, 0x19b, 0x35b), # 2 red mage
    BODFile(b'C.FA1', b'D051_C02.BSD', 0x9e318, 0x18f, 0x361), # stone armor
    BODFile(b'C.FA1', b'D051_D02.BSD', 0x9e4a8, 0x19c, 0x35b), # stone amor
    BODFile(b'C.FA1', b'D051_K21.BSD', 0x9e644, 0x190, 0x361), # two arrow guys
    BODFile(b'C.FA1', b'D051_L21.BSD', 0x9e7d4, 0x19d, 0x35b), # red mage and stone armor
    BODFile(b'C.FA1', b'D051_S01.BSD', 0x9e972, 0x132, 0x22d), # grey armor
    BODFile(b'C.FA1', b'D051_W32.BSD', 0x9eaa4, 0x134, 0x233), # 4 stone armor
    BODFile(b'C.FA1', b'D051_X10.BSD', 0x9ebd8, 0x499, 0x8b9), # (*) green manticore boss
    BODFile(b'C.FA1', b'D052_A12.BSD', 0x9f072, 0x12c, 0x225), # 2 grey eyes
    BODFile(b'C.FA1', b'D052_A22.BSD', 0x9f19e, 0x12e, 0x225), # 4 grey eyes
    BODFile(b'C.FA1', b'D052_B01.BSD', 0x9f2cc, 0x12f, 0x22b), # grey armor
    BODFile(b'C.FA1', b'D052_B02.BSD', 0x9f3fc, 0x17e, 0x359), # 2 gold golems
    BODFile(b'C.FA1', b'D052_B12.BSD', 0x9f57a, 0x12f, 0x22b), # 3 grey armors
    BODFile(b'C.FA1', b'D052_C10.BSD', 0x9f6aa, 0x116, 0x221), # gold golem
    BODFile(b'C.FA1', b'D052_C20.BSD', 0x9f7c0, 0x116, 0x221), # gold golem
    BODFile(b'C.FA1', b'D052_K12.BSD', 0x9f8d6, 0x183, 0x359), # gold golem, 2 grey armor
    BODFile(b'C.FA1', b'D052_S10.BSD', 0x9fa5a, 0x1d0, 0x351), # 2 ghost armor
    BODFile(b'C.FA1', b'D060_S21.BSD', 0x9fc2a, 0x45a, 0xa37), # (*) blue mage + 2 shadow soldiers
    BODFile(b'C.FA1', b'D060_T21.BSD', 0xa0084, 0x115, 0x225), # 3 shadow soldiers
    BODFile(b'C.FA1', b'D061_X10.BSD', 0xa019a, 0x1d4, 0x355), # (*) big dumb snake
    BODFile(b'C.FA1', b'D080_A12.BSD', 0xa036e, 0x11c, 0x223), # 3 zombies
    BODFile(b'C.FA1', b'D080_A22.BSD', 0xa048a, 0x11d, 0x223), # 5 zombies
    BODFile(b'C.FA1', b'D080_A30.BSD', 0xa05a8, 0x11d, 0x223), # 5 zombies
    BODFile(b'C.FA1', b'D080_B10.BSD', 0xa06c6, 0x124, 0x225), # jelly rock
    BODFile(b'C.FA1', b'D080_B12.BSD', 0xa07ea, 0x126, 0x225), # 3 jelly rocks
    BODFile(b'C.FA1', b'D080_B20.BSD', 0xa0910, 0x124, 0x225), # 3 jelly rocks
    BODFile(b'C.FA1', b'D080_C12.BSD', 0xa0a34, 0x122, 0x225), # brown eye
    BODFile(b'C.FA1', b'D080_C21.BSD', 0xa0b56, 0x122, 0x225), # brown eye
    BODFile(b'C.FA1', b'D080_S10.BSD', 0xa0c78, 0x125, 0x227), # armor goblin
    BODFile(b'C.FA1', b'D080_T10.BSD', 0xa0d9e, 0x1d6, 0x353), # grey big dumb snake
    BODFile(b'C.FA1', b'F012_B20.BSD', 0xa0f74, 0x17a, 0x355), # goblin
    BODFile(b'C.FA1', b'F013_B30.BSD', 0xa10ee, 0x173, 0x351), # armor goblin and wolf
    BODFile(b'C.FA1', b'F023_A32.BSD', 0xa1262, 0x138, 0x34f), # 2 red slimes
    BODFile(b'C.FA1', b'F023_L12.BSD', 0xa139a, 0x17f, 0x355), # 
    BODFile(b'C.FA1', b'F023_L22.BSD', 0xa151a, 0x17f, 0x355), #
    BODFile(b'C.FA1', b'F023_S20.BSD', 0xa169a, 0x12f, 0x22d), # 2 grey armors
    BODFile(b'C.FA1', b'F033_D10.BSD', 0xa17ca, 0x19f, 0x351), # black slime
    BODFile(b'C.FA1', b'F036_A12.BSD', 0xa196a, 0x12e, 0x223), # black ghosts
    BODFile(b'C.FA1', b'F036_B12.BSD', 0xa1a98, 0x126, 0x21f), #
    BODFile(b'C.FA1', b'ENIS_BRK.MCA', 0xa1bbe, 0xade, 0x142e),
    BODFile(b'C.FA1', b'NUE.MCA', 0xa269c, 0x147, 0x440),
    BODFile(b'C.FA1', b'SANSITO1.MCA', 0xa27e4, 0xebd, 0x1ab4),
    BODFile(b'C.FA1', b'SISISINK.MCA', 0xa36a2, 0xe0, 0x16e),
    BODFile(b'C.FA1', b'BLK2.MP1', 0xa3782, 0x218c, 0x9196),
    BODFile(b'C.FA1', b'BLK3.MP1', 0xa590e, 0xbe8, 0x8f84),
    BODFile(b'C.FA1', b'CKD.MP1', 0xa64f6, 0x10f8, 0x9056),
    BODFile(b'C.FA1', b'CSL2.MP1', 0xa75ee, 0x21d3, 0x9196),
    BODFile(b'C.FA1', b'CSL3.MP1', 0xa97c2, 0x1157, 0x90a6),
    BODFile(b'C.FA1', b'CSL4.MP1', 0xaa91a, 0x1023, 0x8f2a),
    BODFile(b'C.FA1', b'HIK.MP1', 0xab93e, 0x1d9d, 0x9038),
    BODFile(b'C.FA1', b'SKS2.MP1', 0xad6dc, 0x1190, 0x8f34),
    BODFile(b'C.FA1', b'BLK1.MP2', 0xae86c, 0x273e, 0x91be),
    BODFile(b'C.FA1', b'CSL1.MP2', 0xb0faa, 0x1b83, 0x9092),
    BODFile(b'C.FA1', b'SKS1.MP2', 0xb2b2e, 0x195b, 0x9060),
    BODFile(b'C.FA1', b'BLK1.MPC', 0xb448a, 0x5bb6, 0x9dd0),
    BODFile(b'C.FA1', b'BLK2.MPC', 0xba040, 0x4bc2, 0x8b10),
    BODFile(b'C.FA1', b'BLK3.MPC', 0xbec02, 0x259e, 0x4b50),
    BODFile(b'C.FA1', b'CKD.MPC', 0xc11a0, 0x259e, 0x4b50),
    BODFile(b'C.FA1', b'CSL1.MPC', 0xc373e, 0x535a, 0x94c0),
    BODFile(b'C.FA1', b'CSL2.MPC', 0xc8a98, 0x5204, 0x9fd8),
    BODFile(b'C.FA1', b'CSL3.MPC', 0xcdc9c, 0x538f, 0x9ec0),
    BODFile(b'C.FA1', b'CSL4.MPC', 0xd302c, 0x25b8, 0x8cc8),
    BODFile(b'C.FA1', b'HIK.MPC', 0xd55e4, 0x3dc8, 0x91a0),
    BODFile(b'C.FA1', b'SKS1.MPC', 0xd93ac, 0x5d90, 0x9c90),
    BODFile(b'C.FA1', b'SKS2.MPC', 0xdf13c, 0x4a3b, 0x8818),
    BODFile(b'C.FA1', b'05SKS.SCN', 0xe3b78, 0x1fe, 0x30e),  #
    BODFile(b'C.FA1', b'05SKS01.SCN', 0xe3d76, 0x3c2, 0x5d1),  # R
    BODFile(b'C.FA1', b'05SKS02.SCN', 0xe4138, 0x65d, 0xa76),  # R
    BODFile(b'C.FA1', b'05SKS03.SCN', 0xe4796, 0x5b5, 0x944),  # R
    BODFile(b'C.FA1', b'05SKS04.SCN', 0xe4d4c, 0x95b, 0x1119),  # R
    BODFile(b'C.FA1', b'05SKS05.SCN', 0xe56a8, 0x2b8, 0x432),  # R
    BODFile(b'C.FA1', b'05SKS06.SCN', 0xe5960, 0x5c8, 0x8f1),  # R
    BODFile(b'C.FA1', b'05SKS07.SCN', 0xe5f28, 0x428, 0x668),  # R
    BODFile(b'C.FA1', b'05SKS08.SCN', 0xe6350, 0x5f4, 0x947),  # R
    BODFile(b'C.FA1', b'06BLK.SCN', 0xe6944, 0xa5c, 0x141b),  #
    BODFile(b'C.FA1', b'06BLK00A.SCN', 0xe73a0, 0x96d, 0x10ce),  #
    BODFile(b'C.FA1', b'06BLK00B.SCN', 0xe7d0e, 0x3ba, 0x5f4),  #
    BODFile(b'C.FA1', b'06BLK01.SCN', 0xe80c8, 0xa1c, 0x10cf),  #
    BODFile(b'C.FA1', b'06BLK01A.SCN', 0xe8ae4, 0x22f, 0x393), #
    BODFile(b'C.FA1', b'06BLK01B.SCN', 0xe8d14, 0x8d2, 0xf93),  #
    BODFile(b'C.FA1', b'06BLK01C.SCN', 0xe95e6, 0xa31, 0x1335),  #
    BODFile(b'C.FA1', b'06BLK01D.SCN', 0xea018, 0x831, 0xdd9),  #
    BODFile(b'C.FA1', b'06BLK02.SCN', 0xea84a, 0xa98, 0x13b5),  #
    BODFile(b'C.FA1', b'06BLK02A.SCN', 0xeb2e2, 0x374, 0x577),  #
    BODFile(b'C.FA1', b'06BLK02B.SCN', 0xeb656, 0x372, 0x5f8),  #
    BODFile(b'C.FA1', b'06BLK02C.SCN', 0xeb9c8, 0x89a, 0xf2c),  #
    BODFile(b'C.FA1', b'06BLK02D.SCN', 0xec262, 0x638, 0xb34),  #
    BODFile(b'C.FA1', b'06BLK02E.SCN', 0xec89a, 0x4e8, 0x906),  #
    BODFile(b'C.FA1', b'06BLK02I.SCN', 0xecd82, 0x8ef, 0x1003),  #
    BODFile(b'C.FA1', b'06BLK02O.SCN', 0xed672, 0x2bd, 0x463),  #
    BODFile(b'C.FA1', b'06BLK03.SCN', 0xed930, 0x608, 0x992),  #
    BODFile(b'C.FA1', b'06BLK03A.SCN', 0xedf38, 0x444, 0x818),  #
    BODFile(b'C.FA1', b'06BLK03I.SCN', 0xee37c, 0x7bb, 0xd6c),  #
    BODFile(b'C.FA1', b'06BLK03O.SCN', 0xeeb38, 0x369, 0x599),  #
    BODFile(b'C.FA1', b'06BLK04.SCN', 0xeeea2, 0x96d, 0x10c6),  #
    BODFile(b'C.FA1', b'06BLK04A.SCN', 0xef810, 0x63e, 0xbfa),  #
    BODFile(b'C.FA1', b'06BLK04B.SCN', 0xefe4e, 0x467, 0x74e),  #
    BODFile(b'C.FA1', b'06BLK04I.SCN', 0xf02b6, 0x9c8, 0x128d),  #
    BODFile(b'C.FA1', b'06BLK04J.SCN', 0xf0c7e, 0x7b9, 0xe8f),  #
    BODFile(b'C.FA1', b'06BLK04K.SCN', 0xf1438, 0x613, 0xa1b),  #
    BODFile(b'C.FA1', b'06BLK04O.SCN', 0xf1a4c, 0x263, 0x406),  #
    BODFile(b'C.FA1', b'06BLK05.SCN', 0xf1cb0, 0x817, 0xdcc),  #
    BODFile(b'C.FA1', b'06BLK05I.SCN', 0xf24c8, 0x620, 0xaf1),  #
    BODFile(b'C.FA1', b'06BLK05J.SCN', 0xf2ae8, 0x6cc, 0xba0),  #
    BODFile(b'C.FA1', b'06BLK05K.SCN', 0xf31b4, 0x348, 0x543),  #
    BODFile(b'C.FA1', b'06BLK05O.SCN', 0xf34fc, 0x162, 0x240),  #
    BODFile(b'C.FA1', b'06BLK06K.SCN', 0xf365e, 0x39e, 0x5db),  #
    BODFile(b'C.FA1', b'06BLK07.SCN', 0xf39fc, 0xed2, 0x17f6),  #
    BODFile(b'C.FA1', b'06BLK07I.SCN', 0xf48ce, 0x95e, 0x106a),  #
    BODFile(b'C.FA1', b'06BLK07J.SCN', 0xf522c, 0x7f3, 0xdcc),  #
    BODFile(b'C.FA1', b'06BLK07K.SCN', 0xf5a20, 0x9a6, 0x1101),  #
    BODFile(b'C.FA1', b'06BLK07L.SCN', 0xf63c6, 0xac7, 0x13e2),  #
    BODFile(b'C.FA1', b'06BLK07O.SCN', 0xf6e8e, 0x8a7, 0xdd5),  #
    BODFile(b'C.FA1', b'06BLK08I.SCN', 0xf7736, 0x41e, 0x752),  #
    BODFile(b'C.FA1', b'06BLK09I.SCN', 0xf7b54, 0x143, 0x1c5),  #
    BODFile(b'C.FA1', b'06BLK10I.SCN', 0xf7c98, 0x488, 0x76e),  #
    BODFile(b'C.FA1', b'06BLK11I.SCN', 0xf8120, 0x2b6, 0x458),  #
    BODFile(b'C.FA1', b'06BLK12E.SCN', 0xf83d6, 0x3fe, 0x5bf),  #
    BODFile(b'C.FA1', b'06BLK12I.SCN', 0xf87d4, 0x996, 0x10c9),  #
    BODFile(b'C.FA1', b'07CSL.SCN', 0xf916a, 0xbd8, 0x17fa),  #
    BODFile(b'C.FA1', b'07CSL01.SCN', 0xf9d42, 0x857, 0xfb0),  #
    BODFile(b'C.FA1', b'07CSL01A.SCN', 0xfa59a, 0x911, 0x101b),  #
    BODFile(b'C.FA1', b'07CSL01B.SCN', 0xfaeac, 0x4e0, 0x7a2),  #
    BODFile(b'C.FA1', b'07CSL02.SCN', 0xfb38c, 0xab0, 0x16c3),  #
    BODFile(b'C.FA1', b'07CSL02A.SCN', 0xfbe3c, 0x4a8, 0x9e1),  #
    BODFile(b'C.FA1', b'07CSL02B.SCN', 0xfc2e4, 0x6cb, 0xe73),  #
    BODFile(b'C.FA1', b'07CSL03.SCN', 0xfc9b0, 0x2be, 0x504),  #
    BODFile(b'C.FA1', b'07CSL04.SCN', 0xfcc6e, 0x9d8, 0x13ef),  #
    BODFile(b'C.FA1', b'07CSL04A.SCN', 0xfd646, 0x771, 0xfd9),  #
    BODFile(b'C.FA1', b'07CSL04B.SCN', 0xfddb8, 0x5f6, 0xc43),  #
    BODFile(b'C.FA1', b'07CSL05.SCN', 0xfe3ae, 0x8cc, 0x1048),  #
    BODFile(b'C.FA1', b'07CSL05A.SCN', 0xfec7a, 0x9bb, 0x11f2),  #
    BODFile(b'C.FA1', b'07CSL05B.SCN', 0xff636, 0x7f2, 0xda8),  #
    BODFile(b'C.FA1', b'07CSL05C.SCN', 0xffe28, 0x5c8, 0xaa3),  #
    BODFile(b'C.FA1', b'07CSL05D.SCN', 0x1003f0, 0x53a, 0x84f),  #
    BODFile(b'C.FA1', b'07CSL05E.SCN', 0x10092a, 0x16b, 0x1f0),  #
    BODFile(b'C.FA1', b'07CSL06.SCN', 0x100a96, 0x97c, 0x12ec),  #
    BODFile(b'C.FA1', b'07CSL06E.SCN', 0x101412, 0x78c, 0xe8c),  #
    BODFile(b'C.FA1', b'07CSL07.SCN', 0x101b9e, 0x38d, 0x719),  #
    BODFile(b'C.FA1', b'07CSL07A.SCN', 0x101f2c, 0x1d2, 0x325),  #
    BODFile(b'C.FA1', b'07CSL08.SCN', 0x1020fe, 0x805, 0xfe0),  #
    BODFile(b'C.FA1', b'07CSL08A.SCN', 0x102904, 0x721, 0xdef),  #
    BODFile(b'C.FA1', b'07CSLI00.SCN', 0x103026, 0x242, 0x398),  #
    BODFile(b'C.FA1', b'07CSLI01.SCN', 0x103268, 0x32a, 0x65d),  #
    BODFile(b'C.FA1', b'07CSLI02.SCN', 0x103592, 0x10f, 0x172),  #
    BODFile(b'C.FA1', b'07CSLI03.SCN', 0x1036a2, 0xbd, 0x106),  #
    BODFile(b'C.FA1', b'07CSLI04.SCN', 0x103760, 0x4eb, 0x957),  #
    BODFile(b'C.FA1', b'08CKD.SCN', 0x103c4c, 0x4e2, 0x963),  #
    BODFile(b'C.FA1', b'08CKD01.SCN', 0x10412e, 0x370, 0x6c9),  #
    BODFile(b'C.FA1', b'08CKD01A.SCN', 0x10449e, 0x890, 0xfcf),  #
    BODFile(b'C.FA1', b'08CKD02.SCN', 0x104d2e, 0x1ed, 0x2fd),  #
    BODFile(b'C.FA1', b'08CKD02A.SCN', 0x104f1c, 0x278, 0x3d7),  #
    BODFile(b'C.FA1', b'09HIK.SCN', 0x105194, 0x340, 0x62e),  #
    BODFile(b'C.FA1', b'09HIK01.SCN', 0x1054d4, 0x547, 0xb20),  #
    BODFile(b'C.FA1', b'09HIK01A.SCN', 0x105a1c, 0x816, 0x107c),  #
    BODFile(b'C.FA1', b'09HIKI01.SCN', 0x106232, 0x613, 0xb3d),  #
    BODFile(b'C.FA1', b'CAPTAIN1.SMI', 0x106846, 0x2a4, 0x5d9),
    BODFile(b'C.FA1', b'DVL_EYE1.SMI', 0x106aea, 0x15b, 0x3a8),
    BODFile(b'C.FA1', b'DVL_EYE4.SMI', 0x106c46, 0x15b, 0x3a8),
    BODFile(b'C.FA1', b'GOBLIN1.SMI', 0x106da2, 0xe9, 0x255),
    BODFile(b'C.FA1', b'GOBLIN3.SMI', 0x106e8c, 0xea, 0x255),
    BODFile(b'C.FA1', b'GOLEM3.SMI', 0x106f76, 0x13b, 0x28f),
    BODFile(b'C.FA1', b'KNIGHT1.SMI', 0x1070b2, 0x10b, 0x26a),
    BODFile(b'C.FA1', b'KNIGHT2.SMI', 0x1071be, 0x10b, 0x26a),
    BODFile(b'C.FA1', b'KNIGHT3.SMI', 0x1072ca, 0x10a, 0x26a),
    BODFile(b'C.FA1', b'KNIGHT4.SMI', 0x1073d4, 0x10a, 0x26a),
    BODFile(b'C.FA1', b'L_MAIL.SMI', 0x1074de, 0x102, 0x25b),
    BODFile(b'C.FA1', b'MD_ROCK1.SMI', 0x1075e0, 0x143, 0x297),
    BODFile(b'C.FA1', b'MD_ROCK2.SMI', 0x107724, 0x144, 0x297),
    BODFile(b'C.FA1', b'NUE1.SMI', 0x107868, 0x175, 0x353),
    BODFile(b'C.FA1', b'NUE2.SMI', 0x1079de, 0x178, 0x353),
    BODFile(b'C.FA1', b'S_WARM1.SMI', 0x107b56, 0x158, 0x2b1),
    BODFile(b'C.FA1', b'S_WARM2.SMI', 0x107cae, 0x159, 0x2b1),
    BODFile(b'C.FA1', b'SOLDIE1.SMI', 0x107e08, 0x112, 0x270),
    BODFile(b'C.FA1', b'SOLDIE2.SMI', 0x107f1a, 0x113, 0x270),
    BODFile(b'C.FA1', b'SPIRIT1.SMI', 0x10802e, 0x2bc, 0x69c),
    BODFile(b'C.FA1', b'TOROL3.SMI', 0x1082ea, 0x149, 0x295),
    BODFile(b'C.FA1', b'WIZARD1.SMI', 0x108434, 0x4bb, 0xcd4),
    BODFile(b'C.FA1', b'WIZARD2.SMI', 0x1088f0, 0x4bd, 0xcd4),
    BODFile(b'C.FA1', b'YUMIHEI.SMI', 0x108dae, 0xd3, 0x201),
    BODFile(b'C.FA1', b'ZEFYU2.SMI', 0x108e82, 0x4af, 0xb85),
    BODFile(b'C.FA1', b'ZOMBIE1.SMI', 0x109332, 0x209, 0x4c2),

    BODFile(b'D.FA1', b'BAC_05.AS2', 0xc, 0x2882, 0x2882),
    BODFile(b'D.FA1', b'CHRO_M5.AS2', 0x288e, 0x89e, 0x89e),
    BODFile(b'D.FA1', b'DS_09.AS2', 0x312c, 0x47b0, 0x47b0),
    BODFile(b'D.FA1', b'DS_09A.AS2', 0x78dc, 0x4674, 0x4674),
    BODFile(b'D.FA1', b'DS_10.AS2', 0xbf50, 0x46d0, 0x46d0),
    BODFile(b'D.FA1', b'DS_11.AS2', 0x10620, 0x56ee, 0x56ee),
    BODFile(b'D.FA1', b'DS_22.AS2', 0x15d0e, 0x5b30, 0x5b30),
    BODFile(b'D.FA1', b'PRMN_M5.AS2', 0x1b83e, 0x7c8, 0x7c8),
    BODFile(b'D.FA1', b'RUTI_M5.AS2', 0x1c006, 0xc6a, 0xc6a),
    BODFile(b'D.FA1', b'TCH2_M5.AS2', 0x1cc70, 0x998, 0x998),
    BODFile(b'D.FA1', b'CAPTAIN.BCA', 0x1d608, 0x9229, 0xf581),
    BODFile(b'D.FA1', b'DANGO2.BCA', 0x26832, 0x10dc, 0x1f8c),
    BODFile(b'D.FA1', b'DEADMAN1.BCA', 0x2790e, 0x982, 0x108c),
    BODFile(b'D.FA1', b'DEADMAN2.BCA', 0x28290, 0xc11, 0x1535),
    BODFile(b'D.FA1', b'DEADMAN3.BCA', 0x28ea2, 0x2120, 0x4144),
    BODFile(b'D.FA1', b'FCAPTAIN.BCA', 0x2afc2, 0xac7, 0x1076),
    BODFile(b'D.FA1', b'FSENIOR.BCA', 0x2ba8a, 0x87d, 0xdb6),
    BODFile(b'D.FA1', b'FZEFYUDO.BCA', 0x2c308, 0xb84, 0x1056),
    BODFile(b'D.FA1', b'GARGOYLE.BCA', 0x2ce8c, 0x2eaf, 0x4dcd),
    BODFile(b'D.FA1', b'GOBLIN2S.BCA', 0x2fd3c, 0x861, 0x1cc0),
    BODFile(b'D.FA1', b'GOLEM1.BCA', 0x3059e, 0x4a03, 0x7313),
    BODFile(b'D.FA1', b'HARPY1.BCA', 0x34fa2, 0x2f2f, 0x4c84),
    BODFile(b'D.FA1', b'J_FISH2.BCA', 0x37ed2, 0x25e3, 0x37ec),
    BODFile(b'D.FA1', b'LOBSTER2.BCA', 0x3a4b6, 0x1858, 0x2b58),
    BODFile(b'D.FA1', b'MANTIS1.BCA', 0x3bd0e, 0x3b53, 0x62ef),
    BODFile(b'D.FA1', b'MD_ROCK1.BCA', 0x3f862, 0x118b, 0x22ab),
    BODFile(b'D.FA1', b'MD_ROCK2.BCA', 0x409ee, 0x126e, 0x22ab),
    BODFile(b'D.FA1', b'MD_ROCK4.BCA', 0x41c5c, 0x1267, 0x22ab),
    BODFile(b'D.FA1', b'MIMIC1.BCA', 0x42ec4, 0x1d58, 0x32aa),
    BODFile(b'D.FA1', b'SKELET2.BCA', 0x44c1c, 0x4659, 0x6c97),
    BODFile(b'D.FA1', b'SPIDER2.BCA', 0x49276, 0x2a6b, 0x4926),
    BODFile(b'D.FA1', b'TOROL1.BCA', 0x4bce2, 0x7b23, 0xb53a),
    BODFile(b'D.FA1', b'TOROL2.BCA', 0x53806, 0x7778, 0xb53a),
    BODFile(b'D.FA1', b'TOROL3.BCA', 0x5af7e, 0x7a92, 0xb5da),
    BODFile(b'D.FA1', b'TURTLE2.BCA', 0x62a10, 0x22c7, 0x465e),
    BODFile(b'D.FA1', b'WIZARD3S.BCA', 0x64cd8, 0xd6b, 0x2d3b),
    BODFile(b'D.FA1', b'WYVERN1.BCA', 0x65a44, 0x3644, 0x74a2),
    BODFile(b'D.FA1', b'ZEFYUDOR.BCA', 0x69088, 0xa1dd, 0x12a94),
    BODFile(b'D.FA1', b'ZOMBIE1.BCA', 0x73266, 0x2178, 0x3274),
    BODFile(b'D.FA1', b'ZOMBIE2.BCA', 0x753de, 0x210f, 0x3234),
    BODFile(b'D.FA1', b'C030_S10.BSD', 0x774ee, 0x110, 0x221), # brown golem
    BODFile(b'D.FA1', b'C031_I10.BSD', 0x775fe, 0x110, 0x21f), # red mimic
    BODFile(b'D.FA1', b'C031_S10.BSD', 0x7770e, 0x11d, 0x223), # zombie
    BODFile(b'D.FA1', b'C031_T10.BSD', 0x7782c, 0x11a, 0x223), # skeleton knight
    BODFile(b'D.FA1', b'C031_U10.BSD', 0x77946, 0x115, 0x221), # caveman
    BODFile(b'D.FA1', b'C041_X11.BSD', 0x77a5c, 0x122, 0x355), # possessed people
    BODFile(b'D.FA1', b'C042_X10.BSD', 0x77b7e, 0x4a9, 0x913), # (*) Zerfeudel
    BODFile(b'D.FA1', b'C051_B10.BSD', 0x78028, 0x123, 0x21f), # 2 harpies
    BODFile(b'D.FA1', b'C051_C10.BSD', 0x7814c, 0x11c, 0x223), # 3 zombies
    BODFile(b'D.FA1', b'C051_D21.BSD', 0x78268, 0x127, 0x227), # 3 armor goblins
    BODFile(b'D.FA1', b'C051_E10.BSD', 0x78390, 0x117, 0x21d), # wolf
    BODFile(b'D.FA1', b'C051_S10.BSD', 0x784a8, 0x47e, 0xb2f), # possessed monk
    BODFile(b'D.FA1', b'C051_X10.BSD', 0x78926, 0x1ce, 0x351), # giant dragon
    BODFile(b'D.FA1', b'D080_B12.BSD', 0x78af4, 0x126, 0x225), #
    BODFile(b'D.FA1', b'D090_A10.BSD', 0x78c1a, 0x11f, 0x221), # caveman
    BODFile(b'D.FA1', b'D090_A20.BSD', 0x78d3a, 0x11f, 0x221), # 2 cavemen
    BODFile(b'D.FA1', b'D090_B22.BSD', 0x78e5a, 0x123, 0x225), # 2 jelly rocks
    BODFile(b'D.FA1', b'D090_C12.BSD', 0x78f7e, 0x124, 0x225), # 2 jelly rocks
    BODFile(b'D.FA1', b'D090_C22.BSD', 0x790a2, 0x126, 0x225), # 3 jelly rocks
    BODFile(b'D.FA1', b'D090_K12.BSD', 0x791c8, 0x13a, 0x357), # 2 jelly rocks
    BODFile(b'D.FA1', b'D090_K22.BSD', 0x79302, 0x13c, 0x357), # 2 jelly rocks
    BODFile(b'D.FA1', b'D090_X32.BSD', 0x7943e, 0x1d6, 0x34f), # 5 harpies
    BODFile(b'D.FA1', b'D091_B32.BSD', 0x79614, 0x123, 0x225), # 3 jelly rocks
    BODFile(b'D.FA1', b'D091_C32.BSD', 0x79738, 0x126, 0x225), # 4 jelly rocks
    BODFile(b'D.FA1', b'D091_D12.BSD', 0x7985e, 0x127, 0x21f), # 2 harpies
    BODFile(b'D.FA1', b'D091_D22.BSD', 0x79986, 0x125, 0x21f), # 3 harpies
    BODFile(b'D.FA1', b'D091_K32.BSD', 0x79aac, 0x13b, 0x357), # 5 jelly rocks
    BODFile(b'D.FA1', b'D110_A12.BSD', 0x79be8, 0x124, 0x225), # 2 blue lobsters
    BODFile(b'D.FA1', b'D110_A30.BSD', 0x79d0c, 0x125, 0x225), # 2 blue lobsters
    BODFile(b'D.FA1', b'D110_B10.BSD', 0x79e32, 0x11d, 0x221), # caveman
    BODFile(b'D.FA1', b'D110_B20.BSD', 0x79f50, 0x11c, 0x221), # 2 cavemen
    BODFile(b'D.FA1', b'D110_C10.BSD', 0x7a06c, 0x17c, 0x355), # jellyfish
    BODFile(b'D.FA1', b'D110_D10.BSD', 0x7a1e8, 0x123, 0x225), # muscular small dragon
    BODFile(b'D.FA1', b'D110_K21.BSD', 0x7a30c, 0x170, 0x355), # jellyfish + blue lobster
    BODFile(b'D.FA1', b'D110_S10.BSD', 0x7a47c, 0x1d6, 0x355), # 2 muscle dragons
    BODFile(b'D.FA1', b'D120_A12.BSD', 0x7a652, 0x128, 0x225), # 3 jelly rocks
    BODFile(b'D.FA1', b'D120_A30.BSD', 0x7a77a, 0x127, 0x225), # 3 jelly rocks
    BODFile(b'D.FA1', b'D120_B10.BSD', 0x7a8a2, 0x11d, 0x223), # 3 zombies with red pants
    BODFile(b'D.FA1', b'D120_B20.BSD', 0x7a9c0, 0x11f, 0x223), # 4 zombies with red pants
    BODFile(b'D.FA1', b'D120_C02.BSD', 0x7aae0, 0x195, 0x353), # shadow moon mage
    BODFile(b'D.FA1', b'D120_K12.BSD', 0x7ac76, 0x194, 0x353), # shadow moon mage + 2 red pants zombies
    BODFile(b'D.FA1', b'D120_K22.BSD', 0x7ae0a, 0x196, 0x353), # 2 SMM + 2 RPZ
    BODFile(b'D.FA1', b'D120_S10.BSD', 0x7afa0, 0x124, 0x221), # mantis
    BODFile(b'D.FA1', b'D120_V10.BSD', 0x7b0c4, 0x122, 0x225), # shadow armor goblin
    BODFile(b'D.FA1', b'D130_A22.BSD', 0x7b1e6, 0x11e, 0x221), # 3 green pill bugs
    BODFile(b'D.FA1', b'D130_B12.BSD', 0x7b304, 0x11b, 0x223), # 3 2-headed skeleton knights
    BODFile(b'D.FA1', b'D130_B22.BSD', 0x7b420, 0x11d, 0x223), # 4 2-headed skeleton knights
    BODFile(b'D.FA1', b'D130_C12.BSD', 0x7b53e, 0x11b, 0x223), # 2 turtles
    BODFile(b'D.FA1', b'D130_D10.BSD', 0x7b65a, 0x12c, 0x223), # giant spider
    BODFile(b'D.FA1', b'D130_K21.BSD', 0x7b786, 0x179, 0x351), # giant spider + 2 pill bugs
    BODFile(b'D.FA1', b'D130_S10.BSD', 0x7b900, 0x114, 0x221), # caveman
    BODFile(b'D.FA1', b'D130_T32.BSD', 0x7ba14, 0x1d2, 0x353), # 5 RPZ
    BODFile(b'D.FA1', b'D130_X10.BSD', 0x7bbe6, 0x39b, 0x739), # (*) Gordon
    BODFile(b'D.FA1', b'F022_D12.BSD', 0x7bf82, 0x112, 0x223), # 3 skeleton knights
    BODFile(b'D.FA1', b'F023_A32.BSD', 0x7c094, 0x138, 0x34f), # 2 red slime
    BODFile(b'D.FA1', b'F023_L12.BSD', 0x7c1cc, 0x17f, 0x355), #
    BODFile(b'D.FA1', b'F023_L22.BSD', 0x7c34c, 0x17f, 0x355), #
    BODFile(b'D.FA1', b'F026_B32.BSD', 0x7c4cc, 0x11c, 0x223), #
    BODFile(b'D.FA1', b'F026_D22.BSD', 0x7c5e8, 0x119, 0x223), # goblin
    BODFile(b'D.FA1', b'F033_D10.BSD', 0x7c702, 0x19f, 0x351), #
    BODFile(b'D.FA1', b'F036_A12.BSD', 0x7c8a2, 0x12e, 0x223), #
    BODFile(b'D.FA1', b'F036_B02.BSD', 0x7c9d0, 0x126, 0x21f), # 2 harpies
    BODFile(b'D.FA1', b'F036_B12.BSD', 0x7caf6, 0x126, 0x21f), #
    BODFile(b'D.FA1', b'F036_C10.BSD', 0x7cc1c, 0x120, 0x21f), # small dragon
    BODFile(b'D.FA1', b'CHRBAKU3.MCA', 0x7cd3c, 0x155, 0x580),
    BODFile(b'D.FA1', b'GOBLIN_S.MCA', 0x7ce92, 0x303, 0xc3e),
    BODFile(b'D.FA1', b'PALMAN.MCA', 0x7d196, 0x9c6, 0x11f4),
    BODFile(b'D.FA1', b'STORM_BR.MCA', 0x7db5c, 0xea, 0x1da),
    BODFile(b'D.FA1', b'YUGE.MCA', 0x7dc46, 0x1ed, 0x510),
    BODFile(b'D.FA1', b'DRL2.MP1', 0x7de34, 0x1635, 0x8fc0),
    BODFile(b'D.FA1', b'DRL3.MP1', 0x7f46a, 0x902, 0x8f48),
    BODFile(b'D.FA1', b'DRL4.MP1', 0x7fd6c, 0xc73, 0x8f3e),
    BODFile(b'D.FA1', b'IRE2.MP1', 0x809e0, 0x1406, 0x8f70),
    BODFile(b'D.FA1', b'ISK1.MP1', 0x81de6, 0x1653, 0x8f70),
    BODFile(b'D.FA1', b'ISK2.MP1', 0x8343a, 0x1460, 0x904c),
    BODFile(b'D.FA1', b'KSK.MP1', 0x8489a, 0x15dd, 0x8fc0),
    BODFile(b'D.FA1', b'KTI.MP1', 0x85e78, 0x127a, 0x8fa2),
    BODFile(b'D.FA1', b'MKR2.MP1', 0x870f2, 0x18be, 0x9056),
    BODFile(b'D.FA1', b'NNP.MP1', 0x889b0, 0x11c0, 0x911e),
    BODFile(b'D.FA1', b'SOH2.MP1', 0x89b70, 0x183e, 0x8fb6),
    BODFile(b'D.FA1', b'UMB2.MP1', 0x8b3ae, 0x14d6, 0x8f8e),
    BODFile(b'D.FA1', b'YMM1.MP1', 0x8c884, 0x3254, 0x8fc0),
    BODFile(b'D.FA1', b'YMM2.MP1', 0x8fad8, 0x16fe, 0x8f84),
    BODFile(b'D.FA1', b'YMM3.MP1', 0x911d6, 0x12e2, 0x8f48),
    BODFile(b'D.FA1', b'YMM4.MP1', 0x924b8, 0x118c, 0x8f2a),
    BODFile(b'D.FA1', b'DRL1.MP2', 0x93644, 0x1d4a, 0x90ce),
    BODFile(b'D.FA1', b'IRE1.MP2', 0x9538e, 0x1c53, 0x9088),
    BODFile(b'D.FA1', b'MKR1.MP2', 0x96fe2, 0x1e47, 0x90d8),
    BODFile(b'D.FA1', b'SOH1.MP2', 0x98e2a, 0x1cd9, 0x90e2),
    BODFile(b'D.FA1', b'UMB1.MP2', 0x9ab04, 0x19a3, 0x9074),
    BODFile(b'D.FA1', b'DRL1.MPC', 0x9c4a8, 0x5668, 0x99e8),
    BODFile(b'D.FA1', b'DRL2.MPC', 0xa1b10, 0x4a3b, 0x8818),
    BODFile(b'D.FA1', b'DRL3.MPC', 0xa654c, 0xbd1, 0x1a90),
    BODFile(b'D.FA1', b'DRL4.MPC', 0xa711e, 0x3504, 0x6fe0),
    BODFile(b'D.FA1', b'IRE1.MPC', 0xaa622, 0x595b, 0x9e20),
    BODFile(b'D.FA1', b'IRE2.MPC', 0xaff7e, 0x4a3b, 0x8818),
    BODFile(b'D.FA1', b'ISK1.MPC', 0xb49ba, 0x506d, 0x9ba0),
    BODFile(b'D.FA1', b'ISK2.MPC', 0xb9a28, 0x2a0f, 0x6568),
    BODFile(b'D.FA1', b'KSK.MPC', 0xbc438, 0x3c44, 0x7f30),
    BODFile(b'D.FA1', b'KTI.MPC', 0xc007c, 0x34bc, 0x6d38),
    BODFile(b'D.FA1', b'MKR1.MPC', 0xc3538, 0x4fdb, 0x9588),
    BODFile(b'D.FA1', b'MKR2.MPC', 0xc8514, 0x4bf2, 0x8ae8),
    BODFile(b'D.FA1', b'NNP.MPC', 0xcd106, 0x3c64, 0x7e68),
    BODFile(b'D.FA1', b'SOH1.MPC', 0xd0d6a, 0x5668, 0x99e8),
    BODFile(b'D.FA1', b'SOH2.MPC', 0xd63d2, 0x4a3b, 0x8818),
    BODFile(b'D.FA1', b'UMB1.MPC', 0xdae0e, 0x5544, 0x9df8),
    BODFile(b'D.FA1', b'UMB2.MPC', 0xe0352, 0x4a3b, 0x8818),
    BODFile(b'D.FA1', b'YMM1.MPC', 0xe4d8e, 0x521c, 0x9fb0),
    BODFile(b'D.FA1', b'YMM2.MPC', 0xe9faa, 0x39f4, 0x7288),
    BODFile(b'D.FA1', b'YMM3.MPC', 0xed99e, 0x4c41, 0x9218),
    BODFile(b'D.FA1', b'YMM4.MPC', 0xf25e0, 0x4a3b, 0x8818),
    BODFile(b'D.FA1', b'14YMM.SCN', 0xf701c, 0x567, 0x91d),  #
    BODFile(b'D.FA1', b'14YMM53.SCN', 0xf7584, 0x6f1, 0xd06),  #
    BODFile(b'D.FA1', b'15MKR.SCN', 0xf7c76, 0x5d3, 0xa38),  #
    BODFile(b'D.FA1', b'15MKR01A.SCN', 0xf824a, 0xe1, 0x115),  #
    BODFile(b'D.FA1', b'15MKR01B.SCN', 0xf832c, 0xcd2, 0x1624),  #
    BODFile(b'D.FA1', b'15MKR01C.SCN', 0xf8ffe, 0x885, 0xe2c),  #
    BODFile(b'D.FA1', b'15MKR01D.SCN', 0xf9884, 0x94b, 0x1160),  #
    BODFile(b'D.FA1', b'15MKR01E.SCN', 0xfa1d0, 0x44b, 0x649),  #
    BODFile(b'D.FA1', b'15MKR02A.SCN', 0xfa61c, 0x702, 0xc39),  #
    BODFile(b'D.FA1', b'15MKR02B.SCN', 0xfad1e, 0x39b, 0x5da),  #
    BODFile(b'D.FA1', b'15MKR02C.SCN', 0xfb0ba, 0x326, 0x5a1),  #
    BODFile(b'D.FA1', b'15MKR02D.SCN', 0xfb3e0, 0x29c, 0x419),  #
    BODFile(b'D.FA1', b'15MKR02E.SCN', 0xfb67c, 0x804, 0x1068),  #
    BODFile(b'D.FA1', b'15MKR02F.SCN', 0xfbe80, 0x651, 0xa6b),  #
    BODFile(b'D.FA1', b'15MKR02G.SCN', 0xfc4d2, 0x663, 0xb70),  #
    BODFile(b'D.FA1', b'15MKR02H.SCN', 0xfcb36, 0x517, 0x82e),  #
    BODFile(b'D.FA1', b'15MKR61.SCN', 0xfd04e, 0x13b, 0x1ad),  #
    BODFile(b'D.FA1', b'16MKI.SCN', 0xfd18a, 0x543, 0x811),  #
    BODFile(b'D.FA1', b'16MKI00.SCN', 0xfd6ce, 0xa2, 0xe5),  #
    BODFile(b'D.FA1', b'16MKI01A.SCN', 0xfd770, 0x21b, 0x31d),  #
    BODFile(b'D.FA1', b'16MKI01B.SCN', 0xfd98c, 0x3be, 0x5c3),  #
    BODFile(b'D.FA1', b'16MKI01C.SCN', 0xfdd4a, 0x188, 0x1d8),  #
    BODFile(b'D.FA1', b'16MKI01D.SCN', 0xfded2, 0xc5, 0xd9),  #
    BODFile(b'D.FA1', b'16MKI61.SCN', 0xfdf98, 0x860, 0xfb3),  #
    BODFile(b'D.FA1', b'17DRL.SCN', 0xfe7f8, 0x5b2, 0xa1f),  #
    BODFile(b'D.FA1', b'17DRL01.SCN', 0xfedaa, 0x658, 0x9c0),  #
    BODFile(b'D.FA1', b'17DRL01A.SCN', 0xff402, 0x739, 0xc76),  #
    BODFile(b'D.FA1', b'17DRL01B.SCN', 0xffb3c, 0x7e9, 0x11fc),  #
    BODFile(b'D.FA1', b'17DRL02A.SCN', 0x100326, 0x462, 0x7d3),  #
    BODFile(b'D.FA1', b'17DRL03.SCN', 0x100788, 0x55d, 0x8da),  #
    BODFile(b'D.FA1', b'17DRL03A.SCN', 0x100ce6, 0x511, 0xabe),  #
    BODFile(b'D.FA1', b'17DRL04.SCN', 0x1011f8, 0x7a6, 0xc11),  #
    BODFile(b'D.FA1', b'17DRL04A.SCN', 0x10199e, 0x74f, 0xf32),  #
    BODFile(b'D.FA1', b'17DRL08A.SCN', 0x1020ee, 0x5bf, 0xc89),  #
    BODFile(b'D.FA1', b'18KSK.SCN', 0x1026ae, 0x571, 0x85b),  #
    BODFile(b'D.FA1', b'19IRE.SCN', 0x102c20, 0x2ca, 0x477),  #
    BODFile(b'D.FA1', b'19IRE27.SCN', 0x102eea, 0x6c1, 0xb6f),  #
    BODFile(b'D.FA1', b'19IRE36.SCN', 0x1035ac, 0x939, 0x1125),  #
    BODFile(b'D.FA1', b'19IRE92.SCN', 0x103ee6, 0x302, 0x4b4),  #
    BODFile(b'D.FA1', b'19IRE94.SCN', 0x1041e8, 0x7dc, 0xfcf),  #
    BODFile(b'D.FA1', b'20NNP.SCN', 0x1049c4, 0x336, 0x539),  #
    BODFile(b'D.FA1', b'20NNP93.SCN', 0x104cfa, 0xa9a, 0x12f3),  #
    BODFile(b'D.FA1', b'21KTI.SCN', 0x105794, 0x3ca, 0x630),  #
    BODFile(b'D.FA1', b'22MZI.SCN', 0x105b5e, 0x5f0, 0xa96),  #
    BODFile(b'D.FA1', b'23SOH.SCN', 0x10614e, 0x400, 0x704),  #
    BODFile(b'D.FA1', b'23SOH01.SCN', 0x10654e, 0x54a, 0x853),  #
    BODFile(b'D.FA1', b'23SOH01A.SCN', 0x106a98, 0x55b, 0x952),  #
    BODFile(b'D.FA1', b'23SOH01B.SCN', 0x106ff4, 0x7a5, 0xdf2),  #
    BODFile(b'D.FA1', b'23SOH01I.SCN', 0x10779a, 0x1bd, 0x2a7),  #
    BODFile(b'D.FA1', b'23SOH02.SCN', 0x107958, 0x89f, 0x10cf),  #
    BODFile(b'D.FA1', b'23SOH02A.SCN', 0x1081f8, 0x6db, 0xdf6),  #
    BODFile(b'D.FA1', b'23SOH02B.SCN', 0x1088d4, 0x96b, 0x12dd),  #
    BODFile(b'D.FA1', b'24UMB.SCN', 0x109240, 0x3b9, 0x5f1),  #
    BODFile(b'D.FA1', b'24UMB00.SCN', 0x1095fa, 0x41, 0x60),  #
    BODFile(b'D.FA1', b'24UMB54.SCN', 0x10963c, 0x779, 0xd2f),  #
    BODFile(b'D.FA1', b'24UMB56.SCN', 0x109db6, 0x8ee, 0xf5e),  #
    BODFile(b'D.FA1', b'24UMB57.SCN', 0x10a6a4, 0x9c7, 0x110e),  #
    BODFile(b'D.FA1', b'CAPTAINZ.SMI', 0x10b06c, 0x2a2, 0x5d9),
    BODFile(b'D.FA1', b'DANGO2.SMI', 0x10b30e, 0x119, 0x273),
    BODFile(b'D.FA1', b'DEADMAN.SMI', 0x10b428, 0xe2, 0x20f),
    BODFile(b'D.FA1', b'GARGOYLE.SMI', 0x10b50a, 0xdb, 0x207),
    BODFile(b'D.FA1', b'GOBLIN_S.SMI', 0x10b5e6, 0xea, 0x255),
    BODFile(b'D.FA1', b'GOLEM1.SMI', 0x10b6d0, 0x13b, 0x28f),
    BODFile(b'D.FA1', b'J_FISH2.SMI', 0x10b80c, 0x192, 0x361),
    BODFile(b'D.FA1', b'LOBSTER2.SMI', 0x10b99e, 0xe2, 0x20b),
    BODFile(b'D.FA1', b'MANTIS.SMI', 0x10ba80, 0x190, 0x404),
    BODFile(b'D.FA1', b'MD_ROCK2.SMI', 0x10bc10, 0x144, 0x297),
    BODFile(b'D.FA1', b'MD_ROCK3.SMI', 0x10bd54, 0x143, 0x297),
    BODFile(b'D.FA1', b'MD_ROCK4.SMI', 0x10be98, 0x143, 0x297),
    BODFile(b'D.FA1', b'MIMIC.SMI', 0x10bfdc, 0x10f, 0x23d),
    BODFile(b'D.FA1', b'SKELET2.SMI', 0x10c0ec, 0x10e, 0x270),
    BODFile(b'D.FA1', b'SPIDER2.SMI', 0x10c1fa, 0x16c, 0x30b),
    BODFile(b'D.FA1', b'TOROL1.SMI', 0x10c366, 0x146, 0x295),
    BODFile(b'D.FA1', b'TOROL2.SMI', 0x10c4ac, 0x149, 0x295),
    BODFile(b'D.FA1', b'TOROL3.SMI', 0x10c5f6, 0x149, 0x295),
    BODFile(b'D.FA1', b'TURTLE2.SMI', 0x10c740, 0x153, 0x2ad),
    BODFile(b'D.FA1', b'WIZARD3.SMI', 0x10c894, 0x4bd, 0xcd4),
    BODFile(b'D.FA1', b'WYVERN.SMI', 0x10cd52, 0x13a, 0x2bf),
    BODFile(b'D.FA1', b'ZEFYU3.SMI', 0x10ce8c, 0x4a8, 0xb85),
    BODFile(b'D.FA1', b'ZOMBIE1.SMI', 0x10d334, 0x209, 0x4c2),
    BODFile(b'D.FA1', b'ZOMBIE2.SMI', 0x10d53e, 0x206, 0x4c2),

    BODFile(b'E.FA1', b'BAC_12.AS2', 0xc, 0x1e3c, 0x1e3c),
    BODFile(b'E.FA1', b'BAC_13.AS2', 0x1e48, 0x4112, 0x4112),
    BODFile(b'E.FA1', b'BAC_14.AS2', 0x5f5a, 0x2bf4, 0x2bf4),
    BODFile(b'E.FA1', b'DS_22A.AS2', 0x8b4e, 0x4836, 0x4836),
    BODFile(b'E.FA1', b'DS_23.AS2', 0xd384, 0x6a66, 0x6a66),
    BODFile(b'E.FA1', b'DS_25.AS2', 0x13dea, 0x75f4, 0x75f4),
    BODFile(b'E.FA1', b'DS_26A.AS2', 0x1b3de, 0x7df0, 0x7df0),
    BODFile(b'E.FA1', b'DS_26B.AS2', 0x231ce, 0x69ce, 0x69ce),
    BODFile(b'E.FA1', b'DS_26C.AS2', 0x29b9c, 0x8a8, 0x8a8),
    BODFile(b'E.FA1', b'DS_E1A.AS2', 0x2a444, 0x6688, 0x6688),
    BODFile(b'E.FA1', b'DS_E1B.AS2', 0x30acc, 0x263e, 0x263e),
    BODFile(b'E.FA1', b'DS_END.AS2', 0x3310a, 0xee, 0xee),
    BODFile(b'E.FA1', b'SIN__M5.AS2', 0x331f8, 0xa3e, 0xa3e),
    BODFile(b'E.FA1', b'STF01.AS2', 0x33c36, 0x3ba, 0x3ba),
    BODFile(b'E.FA1', b'STF02.AS2', 0x33ff0, 0x2ac, 0x2ac),
    BODFile(b'E.FA1', b'STF03.AS2', 0x3429c, 0x23c, 0x23c),
    BODFile(b'E.FA1', b'STF04.AS2', 0x344d8, 0x462, 0x462),
    BODFile(b'E.FA1', b'STF05.AS2', 0x3493a, 0x4f8, 0x4f8),
    BODFile(b'E.FA1', b'STF06.AS2', 0x34e32, 0x332, 0x332),
    BODFile(b'E.FA1', b'STF07.AS2', 0x35164, 0x382, 0x382),
    BODFile(b'E.FA1', b'STF08.AS2', 0x354e6, 0x2b2, 0x2b2),
    BODFile(b'E.FA1', b'STF09.AS2', 0x35798, 0x15e, 0x15e),
    BODFile(b'E.FA1', b'STF10.AS2', 0x358f6, 0x206, 0x206),
    BODFile(b'E.FA1', b'STF11.AS2', 0x35afc, 0x3a6, 0x3a6),
    BODFile(b'E.FA1', b'STF12.AS2', 0x35ea2, 0x532, 0x532),
    BODFile(b'E.FA1', b'STF13.AS2', 0x363d4, 0x374, 0x374),
    BODFile(b'E.FA1', b'STF14.AS2', 0x36748, 0x2d4, 0x2d4),
    BODFile(b'E.FA1', b'_H_HADO.BCA', 0x36a1c, 0x926, 0x1225),
    BODFile(b'E.FA1', b'_H_OFUDA.BCA', 0x37342, 0x305, 0x406),
    BODFile(b'E.FA1', b'_KK_MZE.BCA', 0x37648, 0x72b, 0x100e),
    BODFile(b'E.FA1', b'_KK_ORE.BCA', 0x37d74, 0x166d, 0x26ed),
    BODFile(b'E.FA1', b'_KK_SRE.BCA', 0x393e2, 0x287b, 0x5347),
    BODFile(b'E.FA1', b'_KK_TAE.BCA', 0x3bc5e, 0x1df7, 0x362c),
    BODFile(b'E.FA1', b'_KR_BTL.BCA', 0x3da56, 0x2de7, 0x69a6),
    BODFile(b'E.FA1', b'_KR_BTLE.BCA', 0x4083e, 0x2ded, 0x69d3),
    BODFile(b'E.FA1', b'_KR_BTS.BCA', 0x4362c, 0xce2, 0x18e6),
    BODFile(b'E.FA1', b'_KR_COB.BCA', 0x4430e, 0x2b2, 0x56e),
    BODFile(b'E.FA1', b'_KR_EVB.BCA', 0x445c0, 0x1a8d, 0x2f4b),
    BODFile(b'E.FA1', b'_KR_THB.BCA', 0x4604e, 0x1c3b, 0x443b),
    BODFile(b'E.FA1', b'_KR_THBE.BCA', 0x47c8a, 0x1c1b, 0x441f),
    BODFile(b'E.FA1', b'_MG_HLE.BCA', 0x498a6, 0xb47, 0x1579),
    BODFile(b'E.FA1', b'_MG_IWE.BCA', 0x4a3ee, 0x8d7, 0x1092),
    BODFile(b'E.FA1', b'_MGE_BLE.BCA', 0x4acc6, 0x661, 0xf3e),
    BODFile(b'E.FA1', b'_MGE_CFE.BCA', 0x4b328, 0x6fa, 0xc85),
    BODFile(b'E.FA1', b'_MGE_DSE.BCA', 0x4ba22, 0x5ec, 0x11a6),
    BODFile(b'E.FA1', b'_MGE_HLE.BCA', 0x4c00e, 0x2a2, 0x651),
    BODFile(b'E.FA1', b'_SHO_BEE.BCA', 0x4c2b0, 0x2033, 0x3531),
    BODFile(b'E.FA1', b'_SHO_FJE.BCA', 0x4e2e4, 0x263f, 0x599d),
    BODFile(b'E.FA1', b'_SHO_KDE.BCA', 0x50924, 0x123e, 0x1ed6),
    BODFile(b'E.FA1', b'_ZK_GAE.BCA', 0x51b62, 0x2a0a, 0x58fb),
    BODFile(b'E.FA1', b'_ZK_MZE.BCA', 0x5456c, 0xb3f, 0x1c88),
    BODFile(b'E.FA1', b'CAPT_E.BCA', 0x550ac, 0x8d55, 0xe9a7),
    BODFile(b'E.FA1', b'DANGO1.BCA', 0x5de02, 0xff7, 0x1f8c),
    BODFile(b'E.FA1', b'DEADMAN1.BCA', 0x5edfa, 0x982, 0x108c),
    BODFile(b'E.FA1', b'DEADMAN2.BCA', 0x5f77c, 0xc11, 0x1535),
    BODFile(b'E.FA1', b'DEADMAN3.BCA', 0x6038e, 0x2120, 0x4144),
    BODFile(b'E.FA1', b'DEADMAN4.BCA', 0x624ae, 0x106b, 0x19a5),
    BODFile(b'E.FA1', b'DEADMAN5.BCA', 0x6351a, 0xe59, 0x18a5),
    BODFile(b'E.FA1', b'DEADMAN6.BCA', 0x64374, 0xa1b, 0x1115),
    BODFile(b'E.FA1', b'DVL_EYE1.BCA', 0x64d90, 0xfa4, 0x1cde),
    BODFile(b'E.FA1', b'DVL_EYE4.BCA', 0x65d34, 0xf9b, 0x1cde),
    BODFile(b'E.FA1', b'E_DRAGON.BCA', 0x66cd0, 0x23b2, 0x4604),
    BODFile(b'E.FA1', b'FHIKO.BCA', 0x69082, 0xbc7, 0x1116),
    BODFile(b'E.FA1', b'G_STONE.BCA', 0x69c4a, 0x724, 0xdf7),
    BODFile(b'E.FA1', b'GARGOYL2.BCA', 0x6a36e, 0x2eac, 0x4dcd),
    BODFile(b'E.FA1', b'GOLEM4.BCA', 0x6d21a, 0x51be, 0x7313),
    BODFile(b'E.FA1', b'GOLEM5.BCA', 0x723d8, 0x49e8, 0x72f3),
    BODFile(b'E.FA1', b'HIKO.BCA', 0x76dc0, 0x543b, 0x9e53),
    BODFile(b'E.FA1', b'HIKO_E.BCA', 0x7c1fc, 0x4ff9, 0x9333),
    BODFile(b'E.FA1', b'J_FISH1.BCA', 0x811f6, 0x25d3, 0x37ec),
    BODFile(b'E.FA1', b'KIES_E.BCA', 0x837ca, 0xbfb8, 0x13818),
    BODFile(b'E.FA1', b'KOKU_E.BCA', 0x8f782, 0x5c95, 0xb8d2),
    BODFile(b'E.FA1', b'KOKURYU1.BCA', 0x95418, 0x5feb, 0xc3f5),
    BODFile(b'E.FA1', b'KOKURYU2.BCA', 0x9b404, 0x616f, 0xc865),
    BODFile(b'E.FA1', b'KUROKEN.BCA', 0xa1574, 0x183, 0x31f),
    BODFile(b'E.FA1', b'L_MAIL2.BCA', 0xa16f8, 0x262c, 0x49c4),
    BODFile(b'E.FA1', b'L_MAIL3.BCA', 0xa3d24, 0x2636, 0x49c4),
    BODFile(b'E.FA1', b'LOBSTER1.BCA', 0xa635a, 0x1877, 0x2b58),
    BODFile(b'E.FA1', b'MANTIS2.BCA', 0xa7bd2, 0x3b61, 0x62ef),
    BODFile(b'E.FA1', b'MIMIC2.BCA', 0xab734, 0x1e61, 0x32aa),
    BODFile(b'E.FA1', b'NUE3.BCA', 0xad596, 0x3442, 0x5f56),
    BODFile(b'E.FA1', b'NUE_E.BCA', 0xb09d8, 0x3a4c, 0x594a),
    BODFile(b'E.FA1', b'S_WARM2.BCA', 0xb4424, 0x7aa8, 0xb89b),
    BODFile(b'E.FA1', b'SAMSON.BCA', 0xbbecc, 0x3888, 0x5a32),
    BODFile(b'E.FA1', b'SHINOB_E.BCA', 0xbf754, 0x749b, 0xd152),
    BODFile(b'E.FA1', b'SOLDIE2S.BCA', 0xc6bf0, 0x12fb, 0x45d3),
    BODFile(b'E.FA1', b'VII_E.BCA', 0xc7eec, 0x3eb6, 0x88d8),
    BODFile(b'E.FA1', b'WICH.BCA', 0xcbda2, 0x36ca, 0x6910),
    BODFile(b'E.FA1', b'WIZARD2.BCA', 0xcf46c, 0x26e8, 0x46eb),
    BODFile(b'E.FA1', b'WIZARD4.BCA', 0xd1b54, 0x2682, 0x45eb),
    BODFile(b'E.FA1', b'WYVERN2.BCA', 0xd41d6, 0x3ddf, 0x7502),
    BODFile(b'E.FA1', b'WYVN_E.BCA', 0xd7fb6, 0x338f, 0x6d09),
    BODFile(b'E.FA1', b'ZEFY_E.BCA', 0xdb346, 0x9cd9, 0x11e90),
    BODFile(b'E.FA1', b'DL10_A22.BSD', 0xe5020, 0x127, 0x227), # 3 armor goblins
    BODFile(b'E.FA1', b'DL10_B22.BSD', 0xe5148, 0x122, 0x221), # grey pill bug
    BODFile(b'E.FA1', b'DL10_C12.BSD', 0xe526a, 0x11e, 0x225), # grey lobster
    BODFile(b'E.FA1', b'DL10_K32.BSD', 0xe5388, 0x17c, 0x355), # 2 armor goblins
    BODFile(b'E.FA1', b'DL10_L22.BSD', 0xe5504, 0x17d, 0x359), # armor goblin
    BODFile(b'E.FA1', b'DL10_S10.BSD', 0xe5682, 0x125, 0x223), # jellyfish
    BODFile(b'E.FA1', b'DL10_T10.BSD', 0xe57a8, 0x117, 0x223), # gravestone
    BODFile(b'E.FA1', b'DL10_U10.BSD', 0xe58c0, 0x197, 0x359), # 2 red wizards
    BODFile(b'E.FA1', b'DL11_A22.BSD', 0xe5a58, 0x129, 0x225), # 2 eyes
    BODFile(b'E.FA1', b'DL11_A30.BSD', 0xe5b82, 0x128, 0x225), # 3 eyes
    BODFile(b'E.FA1', b'DL11_B12.BSD', 0xe5caa, 0x125, 0x221), # grey mantis
    BODFile(b'E.FA1', b'DL11_B20.BSD', 0xe5dd0, 0x124, 0x221), # 2 grey mantis
    BODFile(b'E.FA1', b'DL11_C10.BSD', 0xe5ef4, 0x119, 0x221), # golem
    BODFile(b'E.FA1', b'DL11_D02.BSD', 0xe600e, 0x1a5, 0x359), # 2 smiley mages
    BODFile(b'E.FA1', b'DL11_K12.BSD', 0xe61b4, 0x1a6, 0x359), # 2 smiley mages + golem
    BODFile(b'E.FA1', b'DL11_X10.BSD', 0xe635a, 0x195, 0x357), # magician girl + head
    BODFile(b'E.FA1', b'DL20_T12.BSD', 0xe64f0, 0x333, 0x619), # (*) 3 eyes with dialogue
    BODFile(b'E.FA1', b'DL21_K22.BSD', 0xe6824, 0x1a4, 0x359), # 2 golem 1 smiley mage
    BODFile(b'E.FA1', b'DL21_O10.BSD', 0xe69c8, 0x1c4, 0x351), # ghost armor
    BODFile(b'E.FA1', b'DL21_P10.BSD', 0xe6b8c, 0x1c8, 0x355), # muscle dragon
    BODFile(b'E.FA1', b'DL21_Q10.BSD', 0xe6d54, 0x1c8, 0x351), # diamond golem
    BODFile(b'E.FA1', b'DL21_R10.BSD', 0xe6f1c, 0x1c4, 0x353), # tombstone
    BODFile(b'E.FA1', b'DL21_S12.BSD', 0xe70e0, 0x1f7, 0x35b), # smiley mage
    BODFile(b'E.FA1', b'DL21_T10.BSD', 0xe72d8, 0x112, 0x21f), # mimic
    BODFile(b'E.FA1', b'DL30_000.BSD', 0xe73ea, 0x21b, 0x4d1), # 3 blue manticores
    BODFile(b'E.FA1', b'DL30_E22.BSD', 0xe7606, 0x11a, 0x221), # gold ghost armors
    BODFile(b'E.FA1', b'DL30_S0F.BSD', 0xe7720, 0x118, 0x223), # possessed girl
    BODFile(b'E.FA1', b'DL30_S0M.BSD', 0xe7838, 0x118, 0x223), # possessed guy
    BODFile(b'E.FA1', b'DL30_S1F.BSD', 0xe7950, 0x118, 0x223), # possessed little girl
    BODFile(b'E.FA1', b'DL30_S1M.BSD', 0xe7a68, 0x118, 0x223), # possessed little boy
    BODFile(b'E.FA1', b'DL30_S2F.BSD', 0xe7b80, 0x118, 0x223), # possessed old woman
    BODFile(b'E.FA1', b'DL30_S2M.BSD', 0xe7c98, 0x118, 0x223), # possessed old coot
    BODFile(b'E.FA1', b'DL30_X10.BSD', 0xe7db0, 0x4ab, 0xa1b), # (*) shrine maiden
    BODFile(b'E.FA1', b'DL30_Y10.BSD', 0xe825c, 0x2d4, 0x53d), # (*) dragon
    BODFile(b'E.FA1', b'DL30_Z10.BSD', 0xe8530, 0x3bb, 0x677), # (*) dragon red
    BODFile(b'E.FA1', b'DL31_C12.BSD', 0xe88ec, 0x119, 0x221), # 3 golems
    BODFile(b'E.FA1', b'DL31_E12.BSD', 0xe8a06, 0x119, 0x221), # 3 gold ghost armors
    BODFile(b'E.FA1', b'DL31_E20.BSD', 0xe8b20, 0x11a, 0x221), # 2 gold ghost armors
    BODFile(b'E.FA1', b'DL31_F10.BSD', 0xe8c3a, 0x123, 0x223), # big dumb snake
    BODFile(b'E.FA1', b'DL31_G10.BSD', 0xe8d5e, 0x11c, 0x221), # big dragon
    BODFile(b'E.FA1', b'DL31_H10.BSD', 0xe8e7a, 0x128, 0x225), # huge turtle
    BODFile(b'E.FA1', b'DL31_K32.BSD', 0xe8fa2, 0x1a6, 0x359), # 3 golems 3 smiley mages
    BODFile(b'E.FA1', b'DS00_E10.BSD', 0xe9148, 0x367, 0x717), # (*) sword
    BODFile(b'E.FA1', b'ED_01.BSD', 0xe94b0, 0x107, 0x213), # can't load these files
    BODFile(b'E.FA1', b'ED_02.BSD', 0xe95b8, 0x107, 0x213),
    BODFile(b'E.FA1', b'ED_03.BSD', 0xe96c0, 0x106, 0x213),
    BODFile(b'E.FA1', b'ED_04.BSD', 0xe97c6, 0x106, 0x213),
    BODFile(b'E.FA1', b'ED_05.BSD', 0xe98cc, 0x107, 0x213),
    BODFile(b'E.FA1', b'ED_06.BSD', 0xe99d4, 0x107, 0x213),
    BODFile(b'E.FA1', b'ED_07.BSD', 0xe9adc, 0x105, 0x213),
    BODFile(b'E.FA1', b'BONFIRE.MCA', 0xe9be2, 0xaa6, 0x11d0),
    BODFile(b'E.FA1', b'C_FOREST.MCA', 0xea688, 0xa1, 0x20a),
    BODFile(b'E.FA1', b'CHRBAKU1.MCA', 0xea72a, 0x67f, 0x1ca4),
    BODFile(b'E.FA1', b'HOTARU.MCA', 0xeadaa, 0x56, 0xa4),
    BODFile(b'E.FA1', b'RAPIS.MCA', 0xeae00, 0x9b5, 0x1b9c),
    BODFile(b'E.FA1', b'SHINOB_D.MCA', 0xeb7b6, 0x24d, 0x366),
    BODFile(b'E.FA1', b'KDI.MP1', 0xeba04, 0x172c, 0x90ec),
    BODFile(b'E.FA1', b'KKI.MP1', 0xed130, 0x1413, 0x9006),
    BODFile(b'E.FA1', b'KKR.MP1', 0xee544, 0x2679, 0x9150),
    BODFile(b'E.FA1', b'KNT.MP1', 0xf0bbe, 0x1d30, 0x9010),
    BODFile(b'E.FA1', b'KOK1.MP1', 0xf28ee, 0x10bc, 0x8f2a),
    BODFile(b'E.FA1', b'KOK2.MP1', 0xf39aa, 0xd0f, 0x8f20),
    BODFile(b'E.FA1', b'KDI.MPC', 0xf46ba, 0x36b5, 0x7ee0),
    BODFile(b'E.FA1', b'KKI.MPC', 0xf7d70, 0x2a0f, 0x6568),
    BODFile(b'E.FA1', b'KKR.MPC', 0xfa780, 0x3c8c, 0x8020),
    BODFile(b'E.FA1', b'KNT.MPC', 0xfe40c, 0x4516, 0x9e98),
    BODFile(b'E.FA1', b'KOK1.MPC', 0x102922, 0x47d7, 0x9ec0),
    BODFile(b'E.FA1', b'KOK2.MPC', 0x1070fa, 0x375c, 0x9920),
    BODFile(b'E.FA1', b'26KKR.SCN', 0x10a856, 0x526, 0xa6d),  #
    BODFile(b'E.FA1', b'26KKR01.SCN', 0x10ad7c, 0x167, 0x233),  #
    BODFile(b'E.FA1', b'26KKR01A.SCN', 0x10aee4, 0xb8, 0xde),  #
    BODFile(b'E.FA1', b'26KKR02.SCN', 0x10af9c, 0x382, 0x599),  #
    BODFile(b'E.FA1', b'26KKR02A.SCN', 0x10b31e, 0x776, 0xf2f),  #
    BODFile(b'E.FA1', b'26KKR03.SCN', 0x10ba94, 0x1d2, 0x2d6),  #
    BODFile(b'E.FA1', b'26KKR04.SCN', 0x10bc66, 0x1cc, 0x2b2),  #
    BODFile(b'E.FA1', b'26KKR04A.SCN', 0x10be32, 0xf5, 0x15d),  #
    BODFile(b'E.FA1', b'26KKR05.SCN', 0x10bf28, 0x1cc, 0x2b2),  #
    BODFile(b'E.FA1', b'26KKR05A.SCN', 0x10c0f4, 0x138, 0x1ab),  #
    BODFile(b'E.FA1', b'26KKR06.SCN', 0x10c22c, 0x329, 0x4f0),  #
    BODFile(b'E.FA1', b'26KKR06A.SCN', 0x10c556, 0x32c, 0x673),  #
    BODFile(b'E.FA1', b'26KKRI00.SCN', 0x10c882, 0x1cd, 0x2d8),  #
    BODFile(b'E.FA1', b'27KKI.SCN', 0x10ca50, 0x384, 0x610),  #
    BODFile(b'E.FA1', b'27KKI01.SCN', 0x10cdd4, 0x670, 0xfe3),  #
    BODFile(b'E.FA1', b'27KKI01A.SCN', 0x10d444, 0x7c1, 0xfd9),  #
    BODFile(b'E.FA1', b'27KKI02.SCN', 0x10dc06, 0x26a, 0x486),  #
    BODFile(b'E.FA1', b'27KKI02A.SCN', 0x10de70, 0x23e, 0x39a),  #
    BODFile(b'E.FA1', b'27KKI03.SCN', 0x10e0ae, 0x316, 0x680),  #
    BODFile(b'E.FA1', b'27KKI03A.SCN', 0x10e3c4, 0x4f0, 0xa6c),  #
    BODFile(b'E.FA1', b'27KKI04.SCN', 0x10e8b4, 0x5d1, 0x1062),  #
    BODFile(b'E.FA1', b'27KKI04A.SCN', 0x10ee86, 0x120, 0x19f),  #
    BODFile(b'E.FA1', b'27KKII00.SCN', 0x10efa6, 0x209, 0x4ea),  #
    BODFile(b'E.FA1', b'27KKII01.SCN', 0x10f1b0, 0xf8, 0x13d),  #
    BODFile(b'E.FA1', b'28KDI.SCN', 0x10f2a8, 0x1226, 0x20ca),  #
    BODFile(b'E.FA1', b'29KNT.SCN', 0x1104ce, 0x15f1, 0x29ad),  #
    BODFile(b'E.FA1', b'29KNT99B.SCN', 0x111ac0, 0x3c9, 0x932),  #
    BODFile(b'E.FA1', b'30IZM.SCN', 0x111e8a, 0x968, 0x1050),  #
    BODFile(b'E.FA1', b'31END.SCN', 0x1127f2, 0x602, 0x98e),  #
    BODFile(b'E.FA1', b'DANGO1.SMI', 0x112df4, 0x116, 0x273),
    BODFile(b'E.FA1', b'DEADMAN.SMI', 0x112f0a, 0xe2, 0x20f),
    BODFile(b'E.FA1', b'DVL_EYE5.SMI', 0x112fec, 0x159, 0x3a8),
    BODFile(b'E.FA1', b'DVL_EYEG.SMI', 0x113146, 0x15a, 0x3a8),
    BODFile(b'E.FA1', b'E_DRAGON.SMI', 0x1132a0, 0x113, 0x263),
    BODFile(b'E.FA1', b'G_STONE1.SMI', 0x1133b4, 0x15e, 0x3de),
    BODFile(b'E.FA1', b'G_STONEL.SMI', 0x113512, 0x15d, 0x3de),
    BODFile(b'E.FA1', b'GARGOYLE.SMI', 0x113670, 0xdb, 0x207),
    BODFile(b'E.FA1', b'GOLEM4.SMI', 0x11374c, 0x13a, 0x28f),
    BODFile(b'E.FA1', b'HIKO.SMI', 0x113886, 0x57d, 0xd68),
    BODFile(b'E.FA1', b'J_FISH1.SMI', 0x113e04, 0x18e, 0x361),
    BODFile(b'E.FA1', b'KOKURYU.SMI', 0x113f92, 0x2eb, 0x637),
    BODFile(b'E.FA1', b'L_MAIL.SMI', 0x11427e, 0x102, 0x25b),
    BODFile(b'E.FA1', b'LOBSTER1.SMI', 0x114380, 0xe2, 0x20b),
    BODFile(b'E.FA1', b'MANTIS.SMI', 0x114462, 0x190, 0x404),
    BODFile(b'E.FA1', b'MIMIC.SMI', 0x1145f2, 0x10f, 0x23d),
    BODFile(b'E.FA1', b'NUE3.SMI', 0x114702, 0x177, 0x353),
    BODFile(b'E.FA1', b'S_WARM2.SMI', 0x11487a, 0x159, 0x2b1),
    BODFile(b'E.FA1', b'SAMSON.SMI', 0x1149d4, 0x1c6, 0x3f0),
    BODFile(b'E.FA1', b'SOLDIE2.SMI', 0x114b9a, 0x113, 0x270),
    BODFile(b'E.FA1', b'WICH2__G.SMI', 0x114cae, 0x366, 0x86f),
    BODFile(b'E.FA1', b'WIZARD2.SMI', 0x115014, 0x4bd, 0xcd4),
    BODFile(b'E.FA1', b'WIZARD4.SMI', 0x1154d2, 0x4bd, 0xcd4),
    BODFile(b'E.FA1', b'WYVERN.SMI', 0x115990, 0x13a, 0x2bf),
]

POINTERS_TO_REASSIGN = {
    'BD.BIN': [
            (0xd8bc, 0xd8db),   # Attack
            (0xd8c1, 0xd8e0),   # Tech
            (0xd8c6, 0xd8e5),   # Defend
            (0xd8cb, 0xd8ea),   # Item
            (0xd8d0, 0xd8ef),   # Equip
            (0xd8d5, 0xd8f4),   # Run
            #(0xbad2, 0xba9e),   # Save
            #(0xbaba, 0xba9e),   # Save
            #(0xbad9, 0xbac1),   # Load
        ]
}

POINTERS_TO_SKIP = [
    ('BD.BIN', 0xb696, 'pointer_location'), # This pointer breaks the "HP" display in pause menu
    ('BD.BIN', 0xe49f, 'pointer_location'), # This pointer breaks the "HP" display in battle
    ('ITEM.SMI', 0x2c00),
    ('02OLB00A.SCN', 0x150),  # Causes soft lock after some line in the intro
    ('02OLB00A.SCN', 0x33b),
    ('02OLB01A.SCN', 0x33b),
    ('02OLB01B.SCN', 0x33b),
    ('02OLB02A.SCN', 0x33b),
    ('02OLB03A.SCN', 0x33b),
    ('03YSK01A.SCN', 0x33b),
    ('03YSK01A.SCN', 0xe09),  # 01 09 26 23 gets mistaken for an "01 09 26" pointer instead of "09 26 23"
    ('03YSK01A.SCN', 0x1204),
    ('03YSK01A.SCN', 0x1289),
]

# Some pointers are just values in tables at particular locations... let's try just doing this
POINTERS_TO_ADD = [
    # file,     location,  text_location
    ('BD.BIN', 0xcbb4, 0xbb96),
    ('BD.BIN', 0xcbb6, 0xbb9b),
    ('BD.BIN', 0xcbb8, 0xbba0),
    ('BD.BIN', 0xcbba, 0xbbac),
]

# Put some default values in there
for bodfile in FILES:
    safe_name = bodfile.name.decode('ascii')
    #if bodfile.name.endswith(b'SCN'):
    #    #print(str(bodfile.name))
    #    if safe_name not in FILE_BLOCKS:
    #        FILE_BLOCKS[safe_name] = [(0, bodfile.decompressed_length)]
    if safe_name not in POINTER_CONSTANT:
        POINTER_CONSTANT[safe_name] = 0

CONTROL_CODES = {
    b'[BLANK]': b'',
    b'[SPLIT]': b'\\f\x00;@\x02',
    b'[New]': b'\x04\x06\x30\x40\x02',
    b'[00]': b'\x00',
}

# Auto-generate file blocks when they are not manually defined
Dump = DumpExcel(DUMP_XLS_PATH)
PtrDump = PointerExcel(POINTER_XLS_PATH)
OriginalBOD = Disk(SRC_DISK, dump_excel=Dump, pointer_excel=PtrDump)
TargetBOD = Disk(DEST_DISK)
for file in FILES_TO_DUMP:
    #print(file)
    if any([t in file for t in ('.DAT', '.MP1')]):
        continue
    if (file not in FILE_BLOCKS) and (file in FILES_TO_REINSERT or file in FILES_WITH_POINTERS):
        print(file, "not in FILE_BLOCKS")
        gf = Gamefile('original/decompressed/%s' % file, disk=OriginalBOD, dest_disk=TargetBOD, pointer_constant=0)

        blocks = []
        string_locations = []

        start = None
        last_string_end = None
        if file.endswith('SCN'):
            translations = Dump.get_translations(file, include_blank=True, sheet_name="SCNs")
        elif file.endswith("BSD"):
            translations = Dump.get_translations(file, include_blank=True, sheet_name="BSDs")
        else:
            translations = Dump.get_translations(file, include_blank=True)
        for t in translations:

            if not start:
                start = t.location
            else:
                distance = t.location - last_string_end
                # 17 seemed good, but I'm finding dialogue with lots of control codes now. Let's try 32 (0x20)
                if distance > 0x25:
                    blocks.append((start, last_string_end))
                    start = t.location
            last_string_end = t.location + len(t.jp_bytestring)
        #blocks.append((start, last_string_end))
        blocks.append((start, len(gf.original_filestring)))

        FILE_BLOCKS[file] = blocks


        # EXPERIMENTAL: Trying to get all segments that are pure text, to get pointer-dumper to ignore "pointers" it finds there
        if file in FILE_STRING_LOCATIONS:
            if FILE_STIRNG_LOCATIONS == []:
                start = None
                last_string_end = None

                for t in translations:
                    string_locations.append((t.location, t.location + len(t.jp_bytestring)))

                FILE_STRING_LOCATIONS[file] = string_locations
                print(string_locations)

    if file in LENGTH_SENSITIVE_BLOCKS and file in FILE_BLOCKS:
        for ls_block in LENGTH_SENSITIVE_BLOCKS[file]:
            print(FILE_BLOCKS[file])
            assert ls_block in FILE_BLOCKS[file], ls_block