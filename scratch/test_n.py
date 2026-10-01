import ctypes
from ctypes import wintypes
import subprocess
import time

user32 = ctypes.windll.user32

def find_visible_explorer_windows():
    found = []
    def enum_cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            cls_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_name, 256)
            if cls_name.value in ("CabinetWClass", "ExploreWClass"):
                title_len = user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(title_len + 1)
                user32.GetWindowTextW(hwnd, buf, title_len + 1)
                found.append((hwnd, cls_name.value, buf.value))
        return True
    
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    return found

print("Initial visible explorer windows:", find_visible_explorer_windows())

folder = r"F:\Hưng\Quản lý page\news\xuất news reup\1109\part1"

# Test launching explorer with /n,
cmd = f'explorer.exe /n,"{folder}"'
print("Launching:", cmd.encode("ascii", "backslashreplace").decode("ascii"))
subprocess.Popen(cmd, shell=True)

time.sleep(2)
print("After /n launch:", find_visible_explorer_windows())
