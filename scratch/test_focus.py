import ctypes
import os
import subprocess
import time

folder = r"F:\Hưng\Quản lý page\news\xuất news reup\1109\part1"

print("Folder exists:", os.path.exists(folder))

# In Windows, to bring a window to the foreground or force a new explorer window:
# If we run `explorer.exe /root,"<folder>"` or `explorer.exe "<folder>"`
# Let's test:
cmd = f'explorer.exe "{folder}"'
print("Executing cmd:", cmd.encode("ascii", "backslashreplace").decode("ascii"))
p = subprocess.Popen(["explorer.exe", folder])
print("PID:", p.pid)
