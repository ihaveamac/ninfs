mount_types = {
    'cci': 'CTR Cart Image (".3ds", ".cci")',
    'cdn': 'CDN contents ("cetk", "tmd", and contents)',
    'cia': 'CTR Importable Archive (".cia")',
    'exefs': 'Executable Filesystem (".exefs", "exefs.bin")',
    'nandctr': 'Nintendo 3DS NAND backup ("nand.bin")',
    'nandhac': 'Nintendo Switch NAND backup ("rawnand.bin")',
    'nandtwl': 'Nintendo DSi NAND backup ("nand_dsi.bin")',
    'ncch': 'NCCH (".cxi", ".cfa", ".ncch", ".app")',
    'romfs': 'Read-only Filesystem (".romfs", "romfs.bin")',
    'sd': 'SD Card Contents ("Nintendo 3DS" from SD)',
    'srl': 'Nintendo DS ROM image (".nds", ".srl")',
    'threedsx': '3DSX Homebrew (".3dsx")',
}

ctr_types = ('cci', 'cdn', 'cia', 'exefs', 'nandctr', 'ncch', 'romfs', 'sd', 'threedsx')
twl_types = ('nandtwl', 'srl')
hac_types = ('nandhac',)

uses_directory = ('cdn', 'sd')