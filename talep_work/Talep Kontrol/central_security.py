"""Windows token-backed AD role checks for Talep Kontrol local desktop.

Reservation decisions use centrally maintained account grants and Windows
SMB/NTFS ACLs. Other privileged operations require a trusted coordinator.
"""
import ctypes
import json
from pathlib import Path
import re
import ntpath
import os
import sys
from ctypes import wintypes

_SID_RE = re.compile(r"S-1-(?:[0-9]+-)*[0-9]+\Z", re.I)


def current_token_has_sid(sid):
    if sys.platform != 'win32' or not isinstance(sid, str) or not _SID_RE.fullmatch(sid.strip()):
        return False
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    convert = advapi.ConvertStringSidToSidW
    convert.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    convert.restype = wintypes.BOOL
    check = advapi.CheckTokenMembership
    check.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL)]
    check.restype = wintypes.BOOL
    release = kernel.LocalFree
    release.argtypes = [ctypes.c_void_p]
    release.restype = ctypes.c_void_p
    ptr = ctypes.c_void_p()
    if not convert(sid, ctypes.byref(ptr)):
        return False
    try:
        member = wintypes.BOOL()
        # Null token means the effective thread/process Windows token.
        return bool(check(None, ptr, ctypes.byref(member)) and member.value)
    finally:
        release(ptr)


def windows_account():
    """Read the SAM-compatible name from the Windows session."""
    if sys.platform != 'win32':
        return ''
    get_name = ctypes.WinDLL('secur32', use_last_error=True).GetUserNameExW
    get_name.argtypes = [ctypes.c_int, wintypes.LPWSTR, ctypes.POINTER(wintypes.ULONG)]
    get_name.restype = ctypes.c_ubyte
    size = wintypes.ULONG(1024)
    buffer = ctypes.create_unicode_buffer(size.value)
    return buffer.value if get_name(2, buffer, ctypes.byref(size)) else ''


def configured_administrator():
    return r'CEDAS\halit.ozdemir'


def is_designated_administrator():
    return windows_account().casefold() == configured_administrator().casefold()


def role_allowed(config, role):
    # Local per-user config and Python source are user-editable. Even a correct
    # Windows SID membership check does not make a CLIENT a trusted authority:
    # the user can replace administrator SID with an ordinary group SID.
    # Deny privileged writes until an IT-managed trusted coordinator validates
    # both the identity AND its centrally controlled authorization policy.
    return False


PANEL_APPROVAL_POLICY = Path('\\\\10.55.2.238\\paylasim\\GM_Planlama_Tesis_Direktorlugu\\MALZEME YÖNETİMİ MÜDÜRLÜĞÜ\\3 - Müdürlük Ortak Alan\\1-Ortak Döküman Alanı\\8-Talep Kontrol\\9-Uygulama\\Panel-Yetkileri\\PANEL_YETKILERI.json')


def panel_approval_allowed(account):
    if not account:
        return False
    if account.casefold() == configured_administrator().casefold():
        return True
    try:
        records = json.loads(PANEL_APPROVAL_POLICY.read_text(encoding='utf-8-sig'))
        record = records.get(account.casefold()) if isinstance(records, dict) else None
        return (
            isinstance(record, dict)
            and str(record.get('account') or '').casefold() == account.casefold()
            and record.get('enabled') is True
            and record.get('shared_approval') is True
        )
    except (OSError, ValueError):
        return False


def final_record_allowed_here(config):
    """Allow writing reservation decisions for centrally authorized Windows accounts."""
    return (
        config.get('shared_write_mode') == 'WINDOWS_ACL_FINAL_RECORD'
        and config.get('enforce_shared_record_root') is True
        and os.environ.get('TALEP_TEST_MODE') != '1'
        and ntpath.normcase(str(config.get('shared_record_root') or ''))
        == ntpath.normcase('\\\\10.55.2.238\\paylasim\\GM_Planlama_Tesis_Direktorlugu\\MALZEME YÖNETİMİ MÜDÜRLÜĞÜ\\3 - Müdürlük Ortak Alan\\1-Ortak Döküman Alanı\\8-Talep Kontrol\\0-Database')
        and panel_approval_allowed(windows_account())
    )


def security_summary(config):
    return {
        'identitySource': 'WINDOWS_ACCESS_TOKEN',
        'rolesConfigured': {r: bool((config.get('security_role_sids') or {}).get(r))
                            for r in ('user', 'reviewer', 'approver', 'administrator')},
        'adAdministrator': role_allowed(config, 'administrator'),
        'sharedRequestQueue': 'PENDING_IT_ACL_ACCEPTANCE',
        'finalApproval': 'WINDOWS_ACL_AUTHORIZED' if final_record_allowed_here(config) else 'WINDOWS_ACL_RESTRICTED',
        'centralDbWrite': final_record_allowed_here(config),
        'note': 'Rezervasyon kararlarının ortak kaydı, merkezi kullanıcı yetkisine ve Windows paylaşım izinlerine tabidir.'
    }
