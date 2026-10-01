import json
import os
import sys

# Load API key from config.json
with open("config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

keys = cfg.get("api_keys", [])
key = keys[0] if keys else None
print(f"Using key: {key[:8]}...")

# 1. Test yt_dlp info extraction
import yt_dlp

test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ" # Short sample video

ydl_opts = {
    'quiet': True,
    'no_warnings': True,
    'extract_flat': True,
}
with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(test_url, download=False)
    print("YT Info:", info.get("title"), "| Duration:", info.get("duration"), "seconds")

# 2. Test google.genai with YouTube URL
from google import genai
from google.genai import types

client = genai.Client(api_key=key)

prompt = "Watch this video and tell me in 1 sentence what happens in it. Return JSON: {\"summary\": \"...\"}"

model_to_use = cfg.get("model_name", "gemini-3.5-flash-lite")
print(f"Testing model: {model_to_use}")

try:
    resp = client.models.generate_content(
        model=model_to_use,
        contents=[
            types.Content(role="user", parts=[
                types.Part.from_uri(file_uri=test_url, mime_type="video/mp4"),
                types.Part.from_text(text=prompt),
            ])
        ],
        config=types.GenerateContentConfig(
            temperature=0.2,
        )
    )
    print("Gemini Response:\n", resp.text)
    
    # 3. Test downloading ONLY 5 seconds (00:00:10 to 00:00:15)
    print("\nTesting partial download: 00:00:10 to 00:00:15...")
    out_dir = "temp_uploads"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "test_clip_section.mp4")
    if os.path.exists(out_path):
        os.remove(out_path)

    dl_opts = {
        'format': 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'download_ranges': yt_dlp.utils.download_range_func(None, [(10, 15)]),
        'force_keyframes_at_cuts': True,
        'outtmpl': out_path,
        'quiet': False,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(dl_opts) as ydl:
        ydl.download([test_url])
    
    if os.path.exists(out_path):
        print(f"SUCCESS! Downloaded clip size: {os.path.getsize(out_path)} bytes ({os.path.getsize(out_path)/1024/1024:.2f} MB)")
    else:
        print("FAILED to download section.")
except Exception as e:
    print("Error:", e)
