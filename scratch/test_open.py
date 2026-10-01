import json
import os
import subprocess
import ctypes

data = json.load(open("session_data.json", encoding="utf-8"))
folder = data["batches"]["default"]["output_folder"]

print("Output folder:", folder.encode("ascii", errors="backslashreplace").decode("ascii"))
print("Exists:", os.path.exists(folder))

# Method A: ShellExecuteW on explorer.exe with argument
res_a = ctypes.windll.shell32.ShellExecuteW(None, "open", "explorer.exe", f'"{folder}"', None, 1)
print("ShellExecuteW explorer.exe result:", res_a)

# Check windows
