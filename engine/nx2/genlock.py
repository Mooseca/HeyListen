# Copyright (C) 2026 Sacrappy
"""One writer at a time in the lifted C's folder (work/sa/gen).

Every step that rewrites code_*.c in place (the lift's write, its text edits and the chunk split; split_hot.py; hl_gates.py;
oot_patches.py run by hand) holds <gen>.lock while it works. A second one, a lift started by hand beside a build or one a
stopped wrapper left running, ends with a message naming the holder, instead of both writing: each deletes the other's split
parts and patches the other's half-written files, and the edits then fail at random ("the output size places were found
[0, 1, 1, ...] times": the second part of a chunk was gone). A lock whose process is gone is taken over.
"""
import contextlib
import os
import sys
import time


def _alive(pid):
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        k.OpenProcess.restype = ctypes.c_void_p
        h = k.OpenProcess(0x1000, False, pid)   # (PROCESS_QUERY_LIMITED_INFORMATION)
        if not h:
            return ctypes.GetLastError() == 5   # (access denied: it exists)
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(code))
        k.CloseHandle(ctypes.c_void_p(h))
        return bool(ok) and code.value == 259   # (STILL_ACTIVE)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def lock_path(gen):
    return os.path.normpath(gen) + ".lock"


def read_holder(path):
    try:
        with open(path, encoding="utf-8") as f:
            pid, _, rest = f.read().strip().partition(" ")
        return int(pid), rest
    except (OSError, ValueError):
        return 0, ""


def take(gen, what):
    """Takes <gen>.lock and gives it back when the process ends (atexit); SystemExit when a live process holds it"""
    import atexit
    path = _take(gen, what)
    atexit.register(_give, path)
    return path


@contextlib.contextmanager
def hold(gen, what):
    """Holds <gen>.lock for the with block; SystemExit when a live process holds it"""
    path = _take(gen, what)
    try:
        yield
    finally:
        _give(path)


def _give(path):
    if read_holder(path)[0] == os.getpid():
        try:
            os.remove(path)
        except OSError:
            print("genlock: could not remove %s" % path, file=sys.stderr)


def _take(gen, what):
    path = lock_path(gen)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    mine = "%d %s since %s" % (os.getpid(), what, time.strftime("%H:%M:%S"))
    for _ in range(3):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            pid, rest = read_holder(path)
            if pid and pid != os.getpid() and _alive(pid):
                raise SystemExit("genlock: %s is held by process %d (%s): two writers on the lifted C make the edits miss their "
                                 "text at random; wait for it or stop it, then run this again" % (path, pid, rest or "?"))
            try:   # (its process is gone, or the file is empty: taken over)
                os.remove(path)
            except OSError:
                pass
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(mine)
        break
    else:
        raise SystemExit("genlock: cannot take %s" % path)
    return path
