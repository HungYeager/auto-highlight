import yt_dlp

url = 'https://www.youtube.com/watch?v=_uNJRHzC208'

clients = [
    ['android_creator'],
    ['tv_embedded'],
    ['android_vr'],
    ['web_embedded'],
    ['web_safari'],
    ['android', 'web'],
    ['ios', 'web'],
]

for c in clients:
    name = '+'.join(c)
    print(f"Testing client: {name}...")
    ydl_opts = {
        'extractor_args': {'youtube': {'player_client': c}},
        'quiet': True,
        'no_warnings': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            print(f"SUCCESS with {name}! Title: {info.get('title')}")
            break
    except Exception as e:
        print(f"Failed {name}: {str(e)[:100]}")
