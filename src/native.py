# Discord: A-Dawg#0001 (AE)
# Supports: Forza Horizon 5 / Forza Horizon 6 profile probing
# Officially: MS Store/XBOX PC App, Steam.
# Unofficially: Every version that isn't running on a console of via cloud gaming should work.
# License: MIT
# Year: 2022

from __future__ import annotations

import ctypes
import struct
import sys
import threading
from ctypes import wintypes

import win32process

from utils import MemoryWriteError, ProcessNotFoundError

ERROR_PARTIAL_COPY = 0x012B
PROCESS_VM_READ = 0x0010
PROCESS_ALL_ACCESS = 0x1F0FFF
SIZE_T = ctypes.c_size_t
PSIZE_T = ctypes.POINTER(SIZE_T)

# Thread-local storage for process handles keyed by PID.
# This eliminates the module-level global handle leak and makes the module
# thread-safe for concurrent probing of different processes.
_thread_local = threading.local()

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def _check_zero(result, func, args):
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())
    return args


kernel32.OpenProcess.errcheck = _check_zero
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)

kernel32.ReadProcessMemory.errcheck = _check_zero
kernel32.ReadProcessMemory.argtypes = (
    wintypes.HANDLE,
    wintypes.LPCVOID,
    wintypes.LPVOID,
    SIZE_T,
    PSIZE_T,
)

kernel32.WriteProcessMemory.errcheck = _check_zero
kernel32.WriteProcessMemory.argtypes = (
    wintypes.HANDLE,
    wintypes.LPCVOID,
    wintypes.LPVOID,
    SIZE_T,
    PSIZE_T,
)

kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)


# ---------------------------------------------------------------------------
# Handle management
# ---------------------------------------------------------------------------

def _get_handle(pid: int) -> wintypes.HANDLE:
    """Return an open process handle for *pid*, caching per-thread."""
    cache: dict[int, wintypes.HANDLE] = getattr(_thread_local, "handles", None)
    if cache is None:
        cache = {}
        _thread_local.handles = cache
    handle = cache.get(pid)
    if handle is None:
        try:
            handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        except ctypes.WinError as exc:
            raise ProcessNotFoundError(
                f"Failed to open process {pid}: {exc}"
            ) from exc
        cache[pid] = handle
    return handle


def close_process(pid: int) -> None:
    """Close the cached handle for *pid* if one exists."""
    cache: dict[int, wintypes.HANDLE] | None = getattr(_thread_local, "handles", None)
    if cache is None:
        return
    handle = cache.pop(pid, None)
    if handle is not None:
        kernel32.CloseHandle(handle)


def close_all_processes() -> None:
    """Close every cached handle in the current thread."""
    cache: dict[int, wintypes.HANDLE] | None = getattr(_thread_local, "handles", None)
    if cache is None:
        return
    for handle in cache.values():
        kernel32.CloseHandle(handle)
    cache.clear()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_64bit() -> bool:
    return struct.calcsize("P") == 8


def get_base_address(pid: int) -> int:
    h = _get_handle(pid)
    modules = win32process.EnumProcessModules(h)
    return modules[0]


def read_process_memory(pid: int, address: int, size: int) -> bytes:
    buf = (ctypes.c_char * size)()
    nread = SIZE_T()
    h = _get_handle(pid)
    try:
        kernel32.ReadProcessMemory(h, address, buf, size, ctypes.byref(nread))
    except WindowsError:
        if ctypes.get_last_error() == ERROR_PARTIAL_COPY:
            return buf[: nread.value]
        return b""
    return buf[: nread.value]


def write_process_memory(pid: int, address: int, buf: bytes) -> None:
    nwritten = SIZE_T()
    h = _get_handle(pid)
    try:
        kernel32.WriteProcessMemory(h, address, buf, len(buf), ctypes.byref(nwritten))
    except ctypes.WinError as exc:
        raise MemoryWriteError(
            f"Failed to write {len(buf)} bytes to 0x{address:x} in process {pid}: {exc}"
        ) from exc


def scan_block(pid: int, start_address: int, block_size: int, scan_for: bytes) -> int:
    memory = read_process_memory(pid, start_address, block_size)
    return memory.find(scan_for)


def dereference_pointer(pid: int, pointer_address: int) -> int:
    address_bytes = read_process_memory(pid, pointer_address, 8)
    if len(address_bytes) != 8:
        return 0
    return int.from_bytes(address_bytes, byteorder=sys.byteorder)


def read_int(pid: int, int_address: int) -> int:
    int_bytes = read_process_memory(pid, int_address, 4)
    if len(int_bytes) != 4:
        return 0
    return int.from_bytes(int_bytes, byteorder=sys.byteorder)


def read_long(pid: int, int_address: int) -> int:
    long_bytes = read_process_memory(pid, int_address, 8)
    if len(long_bytes) != 8:
        return 0
    return int.from_bytes(long_bytes, byteorder=sys.byteorder)
