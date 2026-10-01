import yt_dlp

url = 'https://www.youtube.com/watch?v=_uNJRHzC208'

# Test 1: player_client fallback
for client in ['android', 'ios', 'tv', 'mweb', 'web']:
    print(f"\n--- Testing player_client: {client} ---")
    ydl_opts = {
        'extractor_args': {'youtube': {'player_client': [client]}},
        'quiet': False,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            print(f"SUCCESS with {client}: {info.get('title')}")
            break
    except Exception as e:
        print(f"Failed {client}: {e}")

# Test 2: cookies from browser
for browser in ['chrome', 'edge', 'brave', 'firefox']:
    print(f"\n--- Testing cookies from browser: {browser} ---")
    ydl_opts = {
        'cookiesfrombrowser': (browser,),
        'quiet': False,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            print(f"SUCCESS with {browser} cookies: {info.get('title')}")
            break
    except Exception as e:
        print(f"Failed {browser}: {e}")
