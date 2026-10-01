import os
import subprocess
import time

folder = r"F:\Hưng\Quản lý page\news\xuất news reup\1109\part1"
norm = os.path.normpath(os.path.abspath(folder))

print("Testing direct explorer.exe launch...")
p = subprocess.Popen(["explorer.exe", norm])
print("explorer PID:", p.pid)
