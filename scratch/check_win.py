import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32

def check_window(hwnd):
    title_len = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(title_len + 1)
    user32.GetWindowTextW(hwnd, buf, title_len + 1)
    title = buf.value
    
    is_visible = user32.IsWindowVisible(hwnd)
    is_iconic = user32.IsIconic(hwnd) # Minimized
    
    print(f"HWND {hwnd}: Title='{title}', Visible={is_visible}, Minimized={is_iconic}")

check_window(397028)
check_window(593296)
