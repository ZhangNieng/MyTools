"""
打包配置文件
使用方法：pyinstaller yitihua.spec

如果 Playwright 版本升级，修改下面 CHROMIUM_REVISION 即可。
查看当前版本：ve\Scripts\python.exe -c "import re,pathlib,os; p=pathlib.Path(os.environ['LOCALAPPDATA'])/'ms-playwright'; print([d.name for d in p.glob('chromium-*')])"
"""
import os, sys
from pathlib import Path

# ── 唯一需要关注的配置：chromium 版本号 ──────────────────
# 通过上方注释里的命令查到的版本填这里，当前环境是 1140
CHROMIUM_REVISION = "1140"

# ── 路径计算（无需修改） ──────────────────────────────────
ms_playwright = Path(os.environ["LOCALAPPDATA"]) / "ms-playwright"
_ver_dir = ms_playwright / f"chromium-{CHROMIUM_REVISION}"

# 自动识别子目录名
_subdir = next(
    (s for s in ("chrome-win", "chrome-win64", "chromium-win64")
     if (_ver_dir / s).exists()),
    None
)
if not _subdir:
    raise RuntimeError(
        f"未找到 Chromium 子目录，路径：{_ver_dir}\n"
        f"请先运行：ve\\Scripts\\playwright install chromium"
    )

chromium_src  = str(_ver_dir / _subdir)
chromium_dest = f"playwright/driver/package/.local-browsers/chromium-{CHROMIUM_REVISION}/{_subdir}"

import playwright as _pw
driver_src  = str(Path(_pw.__file__).parent / "driver")
driver_dest = "playwright/driver"

print(f"[spec] chromium src  : {chromium_src}")
print(f"[spec] chromium dest : {chromium_dest}")
print(f"[spec] driver   src  : {driver_src}")

# ── PyInstaller 配置 ──────────────────────────────────────
block_cipher = None

a = Analysis(
    ["yitihua.py"],
    pathex=[],
    binaries=[],
    datas=[
        (driver_src,   driver_dest),
        (chromium_src, chromium_dest),
    ],
    hiddenimports=[
        "playwright",
        "playwright.async_api",
        "playwright._impl._driver",
        "playwright._impl._browser_type",
        "playwright._impl._connection",
        "tkinter",
        "tkinter.ttk",
        "tkinter.scrolledtext",
        "tkinter.messagebox",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="yitihua",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,       # 确认正常后改为 False 隐藏控制台
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)