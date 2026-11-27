# -*- coding: utf-8 -*-
"""Temiz kurulum kurucu ve paket artefaktlarını doğrular."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "Talep_Kontrol.exe"
ONCE = ROOT / "ONCE_OKU.txt"
KURULUM = ROOT / "talep_work" / "Talep Kontrol" / "KURULUM.ps1"


class CleanInstallArtifactsTests(unittest.TestCase):
    def test_exe_mentions_full_purge(self):
        data = EXE.read_bytes()
        # UTF-16LE ASCII substrings appear as b'X\x00'
        def has(text: str) -> bool:
            needle = "".join(ch + "\x00" for ch in text).encode("latin-1")
            return needle in data or text.encode("utf-8") in data

        self.assertTrue(EXE.is_file())
        self.assertTrue(has("--clean-install"))
        self.assertTrue(has("Temiz kurulum"))
        self.assertTrue(has("WebView2") or has("Index"))
        # 6.2.1 bug: taskkill Talep Kontrol* killed installer titled "Talep Kontrol Kurulum"
        self.assertFalse(has("WINDOWTITLE eq Talep Kontrol*"))
        self.assertTrue(has("WINDOWTITLE eq Talep Kontrol"))
        self.assertTrue(has("IMAGENAME ne Talep_Kontrol.exe"))

    def test_docs_and_ps1_clean_switch(self):
        once = ONCE.read_text(encoding="utf-8")
        self.assertIn("Temiz kurulum", once)
        self.assertIn("%LOCALAPPDATA%\\TalepKontrol", once)
        self.assertIn("--clean-install", once)
        ps1 = KURULUM.read_text(encoding="utf-8")
        self.assertIn("CleanInstall", ps1)
        self.assertIn("Stop-TalepServices", ps1)


if __name__ == "__main__":
    unittest.main()
