import ctypes
import os
import subprocess
import time

user32 = ctypes.windll.user32

folder = r"F:\Hưng\Quản lý page\news\xuất news reup\1109\part1"
norm = os.path.normpath(os.path.abspath(folder))

# Try SwitchToThisWindow after launching explorer
subprocess.Popen(["explorer.exe", norm])

# Wait 500ms for explorer window to create/update
time.sleep(0.5)

# Find window with CabinetWClass
def bring_to_front(folder_path):
    folder_name = os.path.basename(folder_path)
    print("Looking for window containing:", folder_name)
    
    def enum_cb(hwnd, _):
        cls_name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls_name, 256)
        if cls_name.value in ("CabinetWClass", "ExploreWClass"):
            title_len = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(title_len + 1)
            user32.GetWindowTextW(hwnd, buf, title_len + 1)
            print(f"Candidate HWND {hwnd}: '{buf.value}'")
            if folder_name.lower() in buf.value.lower():
                print(f"Found match! Bringing {hwnd} to front...")
                user32.ShowWindow(hwnd, 9) # SW_RESTORE
                user32.SwitchToThisWindow(hwnd, True)
                user32.SetForegroundWindow(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

bring_to_front(norm)
