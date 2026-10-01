import os
import subprocess

folder = r"F:\Hưng\Quản lý page\news\xuất news reup\1109\part1"
norm = os.path.normpath(os.path.abspath(folder))

items = os.listdir(norm)
print("Items in folder:", items)

if items:
    first_item = os.path.join(norm, items[0])
    cmd = f'explorer.exe /select,"{first_item}"'
    print("Running:", cmd.encode("ascii", "backslashreplace").decode("ascii"))
    subprocess.Popen(cmd)
else:
    cmd = f'explorer.exe "{norm}"'
    print("Running:", cmd.encode("ascii", "backslashreplace").decode("ascii"))
    subprocess.Popen(cmd)
