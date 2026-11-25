# -*- coding: utf-8 -*-
"""Talep Kontrol - prelaunch-only, verified update client.

Never starts another program, never writes to the central share. It copies an
admin-published immutable ZIP, checks SHA-256, stages it, preserves local data,
and swaps the local application while no Talep Kontrol GUI is running.

Security boundary: manifest hashes verify integrity, not publisher identity.
Production requires administrator-only SMB/NTFS write ACLs and BT approval.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shutil
import socket
import sys
import time
import uuid
import zipfile

PRODUCT = "Talep Kontrol"
REQUIRED = {
    "Talep Kontrol.vbs", "AUTO_BASLAT.ps1", "otomatik_guncelleyici.py",
    "START_GUI.ps1", "server.py", "index.html", "config.json",
    "windows_launcher.py",
    "PYTHON_BOOTSTRAP.ps1", "WEBVIEW2_HAZIRLA.ps1",
    "amount-analysis.css", "app.js", "assets/brand/talep-kontrol-kurumsal.png", "assets/brand/talep-kontrol.ico.png", "brand-v1.css", "desktop-status.css", "desktop-status.js", "export-utils.js", "form-elements.css", "help-ui.css", "help-ui.js", "operations-experience.css", "operations-experience.js", "operations-tables.js", "operations-work.css", "operations-work.js", "responsive.css", "startup_runner.py", "styles.css", "ux28j.css", "ux28j.js", "webgl-themes28l.css", "webgl-themes28l.js",
    "control_read_index.py", "data_architecture_v2.py", "f604_summary.py", "form_excel.py", "kesif_drafts28q.py", "project_ids28r.py",
    "mb51_reconciliation.py", "commitment_balances.py", "capacity_projection.py", "capacity_source_facts.py", "operations_aggregation.py", "central_security.py", "indexed_engine.py", "parquet_minimal.py",
}
KEEP_DIRS = (
    "_runtime", "_runtime_packages", "csv", "kayitlar", "cache",
    "local_data", "local_cache", "logs", "quarantine", "data_v2", "data", "veri",
)
MAX_EXPANDED_BYTES = 1_000_000_000
MAX_ENTRIES = 3000
RELEASE_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")


def canonical_unc(value):
    return isinstance(value,str) and value.startswith('\\\\') and not value.startswith('\\\\\\') and '\\\\' not in value[2:] and len(value[2:].split('\\'))>=2


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def log(destination: pathlib.Path, message: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    line = f"{dt.datetime.now().isoformat(timespec='seconds')} | {message}\n"
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(line)
    print(message, flush=True)


def valid_manifest(share: pathlib.Path) -> tuple[dict, pathlib.Path]:
    manifest_path = share / "Aktif" / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if data.get("schema") != 1 or data.get("product") != PRODUCT:
        raise ValueError("Aktif yayin formati gecersiz.")
    path = data.get("package")
    if not isinstance(path, str):
        raise ValueError("Yayin paket yolu eksik.")
    parts = path.split("/")
    if (len(parts) != 3 or parts[0] != "Paketler" or
        not RELEASE_PATTERN.fullmatch(parts[1]) or parts[2] != "TalepKontrol.zip"):
        raise ValueError("Yayin paket yolu izin verilen yapida degil.")
    if data.get("release_id") != parts[1]:
        raise ValueError("Yayin kimligi paket yoluyla eslesmiyor.")
    digest = data.get("sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Yayin SHA-256 alani gecersiz.")
    size = data.get("size_bytes")
    if type(size) is not int or not 0 < size <= MAX_EXPANDED_BYTES:
        raise ValueError("Yayin boyutu gecersiz.")
    return data, share / "Aktif" / "Paketler" / parts[1] / "TalepKontrol.zip"


def validate_zip(archive: pathlib.Path) -> None:
    total = 0
    seen: set[str] = set()
    count = 0
    with zipfile.ZipFile(archive) as source:
        if source.testzip() is not None:
            raise ValueError("ZIP CRC testi basarisiz.")
        for member in source.infolist():
            if member.is_dir():
                continue
            count += 1
            name = member.filename
            parts = pathlib.PurePosixPath(name).parts
            if (len(parts) < 2 or parts[0] != PRODUCT or
                pathlib.PurePosixPath(name).is_absolute() or
                any(p in (".", "..") or ":" in p or "\\" in p for p in parts)):
                raise ValueError("ZIP icinde guvensiz dosya yolu: " + name)
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("ZIP sembolik bag iceremez.")
            relative = "/".join(parts[1:])
            key = relative.casefold()
            if key in seen:
                raise ValueError("ZIP icinde tekrar eden dosya yolu: " + relative)
            seen.add(key)
            total += member.file_size
            if total > MAX_EXPANDED_BYTES or count > MAX_ENTRIES:
                raise ValueError("ZIP boyut veya dosya adedi sinirini asiyor.")
        missing = {p.casefold() for p in REQUIRED} - seen
        if missing:
            raise ValueError("Guncelleme icin zorunlu dosyalar eksik: " + ", ".join(sorted(missing)))


def unpack(archive: pathlib.Path, stage: pathlib.Path) -> None:
    validate_zip(archive)
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            if member.is_dir():
                continue
            parts = pathlib.PurePosixPath(member.filename).parts[1:]
            output = stage.joinpath(*parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            with source.open(member) as inp, output.open("wb") as dest:
                shutil.copyfileobj(inp, dest)
    # Distinguish a valid archive from an application with broken configuration.
    cfg = json.loads((stage / "config.json").read_text(encoding="utf-8-sig"))
    if cfg.get("product_name") != PRODUCT:
        raise ValueError("Yeni paket Talep Kontrol yapilandirmasina sahip degil.")
    if cfg.get("auto_install_updates") is not True:
        raise ValueError("Yeni pakette otomatik guncelleme kapali.")
    if not canonical_unc(cfg.get("update_share")) or not cfg["update_share"].endswith("\\9-Uygulama\\Aktif"):
        raise ValueError("Yeni paketin guncelleme yolu gecersiz.")
    raw = (stage / "Talep Kontrol.vbs").read_bytes()
    launcher = raw.decode("utf-16" if raw.startswith(b"\xff\xfe") else "utf-8-sig")
    if "AUTO_BASLAT.ps1" not in launcher:
        raise ValueError("Yeni paketin baslaticisi otomatik guncellemeye bagli degil.")
    if cfg.get("shared_writes_enabled") is True:
        raise ValueError("Guvenli merkezi kayit hizmeti olmadan yazma acan paket reddedildi.")
    # Package may not silently repoint live corporate data to an arbitrary local dir.
    if not canonical_unc(cfg.get("external_root", "")):
        raise ValueError("Yeni paket ortak ag kaynak adresini kullanmiyor.")


def preserve_user_files(old: pathlib.Path, stage: pathlib.Path) -> None:
    # Mutable user data wins over package defaults; application code is outside KEEP_DIRS.
    # The entire old install stays as a rollback backup after the swap.
    for dirname in KEEP_DIRS:
        original = old / dirname
        if not original.is_dir() or original.is_symlink():
            continue
        for root, folders, files in os.walk(original, followlinks=False):
            folders[:] = [name for name in folders
                          if not pathlib.Path(root, name).is_symlink()]
            base = pathlib.Path(root)
            for filename in files:
                src = base / filename
                if src.is_symlink():
                    continue
                rel = src.relative_to(old)
                dest = stage / rel
                if dirname in ("_runtime", "_runtime_packages") and dest.exists():
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)


def write_receipt(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


@contextlib.contextmanager
def locked(path: pathlib.Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as e:
                raise RuntimeError("Baska guncelleme islemi calisiyor.") from e
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as e:
                raise RuntimeError("Baska guncelleme islemi calisiyor.") from e
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def other_service_running() -> bool:
    if os.name != "nt":
        return False
    for port in range(8765, 8770):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            pass
    return False


def run(share: pathlib.Path, target: pathlib.Path, userdata: pathlib.Path, *, check_only=False) -> str:
    """Return one of: guncel, guncellendi, yayin_yok, servis_acik.

    On error raise. Caller logs and continues with existing installation.
    """
    logfile = userdata / "Guncelleme" / "guncelleme.log"
    receipt = userdata / "Guncelleme" / "son_kurulum.json"
    with locked(userdata / "Guncelleme" / "islem.lock"):
        manifest_path = share / "Aktif" / "manifest.json"
        if not manifest_path.is_file():
            log(logfile, "Aktif yayin yok veya ag erisilemiyor. Yerel uygulama korunuyor.")
            return "yayin_yok"
        manifest, package = valid_manifest(share)
        try:
            local = json.loads(receipt.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            local = {}
        if local.get("sha256") == manifest["sha256"] and target.is_dir():
            return "guncel"
        if not package.is_file() or package.stat().st_size != manifest["size_bytes"]:
            raise RuntimeError("Aktif yayin paketi eksik veya boyutu uyusmuyor.")
        if check_only:
            return "guncelleme_hazir"
        if other_service_running():
            log(logfile, "Yerel uygulama hizmeti acik; guncelleme sonraki acilisa ertelendi.")
            return "servis_acik"
        parent = target.parent
        parent.mkdir(parents=True, exist_ok=True)
        stage = parent / (".TalepKontrol-hazirlik-" + uuid.uuid4().hex)
        archive = parent / (".TalepKontrol-paket-" + uuid.uuid4().hex + ".zip")
        backup = None
        try:
            log(logfile, "Onayli yayinin kopyasi aliniyor: " + str(manifest.get("release_id", "")))
            shutil.copyfile(package, archive)
            if archive.stat().st_size != manifest["size_bytes"] or sha256(archive) != manifest["sha256"]:
                raise RuntimeError("ZIP ozeti veya boyutu yayin kaydiyla eslesmiyor.")
            stage.mkdir(parents=True)
            unpack(archive, stage)
            if target.is_dir():
                preserve_user_files(target, stage)
                backup = parent / (".TalepKontrol-yedek-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
                os.replace(target, backup)
            try:
                os.replace(stage, target)
            except Exception:
                if backup is not None and backup.exists() and not target.exists():
                    os.replace(backup, target)
                raise
            write_receipt(receipt, {
                "product": PRODUCT, "sha256": manifest["sha256"],
                "release_id": str(manifest.get("release_id", "")),
                "installed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "install_dir": str(target), "previous_install_backup": str(backup) if backup else None,
            })
            log(logfile, "Yerel Talep Kontrol paketi dogrulandi ve guncellendi.")
            return "guncellendi"
        finally:
            archive.unlink(missing_ok=True)
            if stage.exists():
                shutil.rmtree(stage, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--share-root", type=pathlib.Path, required=True)
    parser.add_argument("--install-dir", type=pathlib.Path, required=True)
    parser.add_argument("--user-data", type=pathlib.Path, required=True)
    parser.add_argument("--status-file", type=pathlib.Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    logfile = args.user_data / "Guncelleme" / "guncelleme.log"
    try:
        result = run(args.share_root, args.install_dir, args.user_data, check_only=args.check_only)
        if args.check_only:
            write_receipt(logfile.with_name("paket_kontrolu.json"), {"result": result})
        log(logfile, "SONUC: " + result)
        if args.status_file is not None:
            write_receipt(args.status_file, {"result": result})
        return 0
    except Exception as e:
        try:
            log(logfile, "UYARI: " + str(e))
        except OSError:
            pass
        return 2


if __name__ == "__main__":
    sys.exit(main())
