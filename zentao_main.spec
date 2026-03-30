# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['zentao_main.py'],
    pathex=['/app'],
    binaries=[],
    datas=[
        ('zentao.ini', '.'),
        ('task_state.json', '.'),
    ],
    hiddenimports=[
        'requests',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='zentao_main',
    debug=False,
    strip=False,
    upx=True,
    console=True,   # ✅ 青龙 / CLI 程序一定要开
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='zentao_main',
)
