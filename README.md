# 🎬 Viral Bodycam Clipper

Công cụ desktop để phân tích, cắt và xuất clip bodycam dạng 9:16 (TikTok/Reels/Shorts).  
Sử dụng **Google Gemini AI** để phân tích video và tạo sub tự động.

---

## ✅ Yêu cầu hệ thống

| Thứ cần | Phiên bản |
|---|---|
| Windows 10/11 | 64-bit |
| Python | 3.10+ |
| FFmpeg | bất kỳ (thêm vào PATH) |
| Google API Key | Gemini Flash |

---

## 🚀 Cài đặt lần đầu

### Bước 1 — Cài Python
Tải tại: https://python.org/downloads  
> ⚠️ Nhớ tích **"Add Python to PATH"** khi cài.

### Bước 2 — Cài FFmpeg
Chạy lệnh này trong PowerShell (Admin):
```
winget install --id Gyan.FFmpeg -e
```
Hoặc tải thủ công: https://ffmpeg.org/download.html → giải nén → thêm vào PATH.

### Bước 3 — Chạy setup
Double-click file `setup.bat` — nó sẽ tự cài các thư viện Python cần thiết.

### Bước 4 — Lấy Google API Key
1. Vào: https://aistudio.google.com/apikey
2. Tạo API Key mới (miễn phí)
3. Dán vào ô **API Key** trong app khi mở lần đầu

---

## ▶️ Sử dụng hàng ngày

Double-click **`run.bat`** để mở app.

---

## 🔧 Tính năng chính

### Tab 1 — Phân tích Video
- Kéo thả hoặc chọn video bodycam
- Gemini AI tự phân tích và chọn **5 khoảnh khắc viral nhất**
- Xem thumbnail + thông tin từng clip
- Cắt clip chính xác 16 giây

### Tab 2 — Editor Reup
- **Preview real-time** 9:16 ngay trên màn hình
- **Title text**: font, màu, vị trí, hiệu ứng
- **Background**: blur / ảnh tĩnh / video loop
- **Copyright Evasion**: đổi màu, lật video, watermark, film grain, speed tweak
- **Auto-subtitles (Gemini AI)**: tự động tạo sub khớp từng lời nói, có thể chỉnh vị trí
- **Blur box**: làm mờ biển số, mặt người,...
- **Export**: xuất 1 clip hoặc tất cả cùng lúc với progress bar

---

## 📁 Cấu trúc file

```
auto highlight/
├── app.py              ← Code chính
├── run.bat             ← Mở app
├── setup.bat           ← Cài lần đầu
├── requirements.txt    ← Thư viện Python
└── config.json         ← Lưu API key + output folder
```

---

## ❓ Xử lý lỗi thường gặp

| Lỗi | Cách fix |
|---|---|
| `ffmpeg not found` | Cài FFmpeg và thêm vào PATH |
| `API key invalid` | Kiểm tra key tại aistudio.google.com |
| App crash khi mở | Chạy lại `setup.bat` để cập nhật thư viện |
| Sub không khớp | Thử lại — Gemini có thể trả về kết quả khác nhau |

---

## 📌 Ghi chú

- API Key **miễn phí** (Gemini Flash tier)
- Mỗi lần phân tích video mất **~30–60 giây** tuỳ độ dài video
- Sub được tạo bằng audio-only mode để tăng độ chính xác
- File `.srt` được lưu cùng folder với clip gốc
