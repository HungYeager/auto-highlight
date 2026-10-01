# Quy tắc Đóng gói và Phát hành (Packaging & Release Rule)

Mỗi khi người dùng yêu cầu đóng gói, build hoặc xuất bản phát hành (.exe) để đem sang máy khác sử dụng:

1. **Tính độc lập 100% (Standalone for Clean Windows Machines)**:
   - Bản phát hành PHẢI chạy được ngay trên máy tính Windows mới hoàn toàn, không có Python, không có Node.js, không có môi trường ngoài.
   - Luôn sử dụng bộ build `OpenCutStudio.spec` và kịch bản `build_opencutstudio.ps1`.

2. **Đầy đủ bộ binary & assets đi kèm trong thư mục phát hành**:
   - `OpenCutStudio.exe` (đã nhúng Web Studio, backend FastAPI, RapidOCR ONNX models, OpenCV tracking, Google GenAI SDK, Certifi SSL, Pillow, Shapely, PyCLipper).
   - `ffmpeg.exe`, `ffprobe.exe`, `ffplay.exe` (copy trực tiếp cạnh file `.exe`).
   - Thư mục `fonts/` (chứa toàn bộ font TTF chuẩn render).
   - File template cấu hình `config.json` sạch.
   - Thư mục runtime `overlay_assets/cutouts/` và `temp_uploads/`.
   - File hướng dẫn `README.txt` chi tiết.

3. **Mã hóa UTF-8 & Xử lý đường dẫn tiếng Việt an toàn**:
   - Hộp thoại chọn file/thư mục luôn dùng kiến trúc 3 lớp (In-process Tkinter, PowerShell STA WinForms với `[Console]::OutputEncoding = UTF8`, ctypes Comdlg32).
   - Tuyệt đối không để xảy ra lỗi `UnicodeDecodeError` / `cp1258` trên Windows tiếng Việt.
   - Mọi đường dẫn file input/output đều qua chuẩn hóa Unicode (`_safe_resolve_path`).

4. **Đầu ra bắt buộc**:
   - Thư mục phát hành `dist/OpenCutStudio_vX.Y.Z/`
   - File ZIP nén hoàn chỉnh `dist/OpenCutStudio_vX.Y.Z.zip`
