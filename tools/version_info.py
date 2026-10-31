"""Write build/version_info.txt (Windows VERSIONINFO resource) from __version__."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from project_opener import __app_name__, __company__, __version__  # noqa: E402

nums = [int(n) for n in re.findall(r"\d+", __version__)[:4]]
while len(nums) < 4:
    nums.append(0)
tuple_str = ", ".join(str(n) for n in nums)

TEMPLATE = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({tuple_str}),
    prodvers=({tuple_str}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', '{__company__}'),
        StringStruct('FileDescription', '{__app_name__}'),
        StringStruct('FileVersion', '{__version__}'),
        StringStruct('InternalName', 'ProjectOpener'),
        StringStruct('LegalCopyright', 'Copyright (c) 2026 {__company__}'),
        StringStruct('OriginalFilename', 'ProjectOpener.exe'),
        StringStruct('ProductName', '{__app_name__}'),
        StringStruct('ProductVersion', '{__version__}')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""

out = ROOT / "build" / "version_info.txt"
out.parent.mkdir(exist_ok=True)
out.write_text(TEMPLATE, encoding="utf-8")
print(f"wrote {out} for version {__version__}")
