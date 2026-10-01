import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
found = []

def enum_cb(hwnd, lparam):
    if user32.IsWindowVisible(hwnd):
        title_len = user32.GetWindowTextLengthW(hwnd)
        if title_len > 0:
            buf = ctypes.create_unicode_buffer(title_len + 1)
            user32.GetWindowTextW(hwnd, buf, title_len + 1)
            cls_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_name, 256)
            found.append((hwnd, cls_name.value, buf.value))
    return True

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

for h, c, t in found:
    safe_t = t.encode("ascii", "backslashreplace").decode("ascii")
    print(f"HWND {h} [{c}]: {safe_t}")
