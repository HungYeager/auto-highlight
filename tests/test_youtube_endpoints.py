import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from youtube_manager import YouTubeHistoryManager

def test_api_check_and_lookup():
    with tempfile.TemporaryDirectory() as td:
        storage_p = Path(td) / "test_hist.json"
        mgr = YouTubeHistoryManager(str(storage_p))
        test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        # 1. Initial check (not yet in history)
        res1 = mgr.check_url(test_url, prefix="COP")
        assert res1["valid"] is True
        assert res1["yt_id"] == "dQw4w9WgXcQ"
        assert res1["exists"] is False
        assert res1["next_code"].startswith("COP")

        # 2. Register
        rec = mgr.register_or_get(test_url, title="Rick Astley - Never Gonna Give You Up", prefix="COP")
        assert rec["yt_id"] == "dQw4w9WgXcQ"
        assert rec["asset_code"].startswith("COP")

        # 3. Second check (now exists!)
        res2 = mgr.check_url(test_url, prefix="COP")
        assert res2["valid"] is True
        assert res2["exists"] is True
        assert res2["record"]["title"] == "Rick Astley - Never Gonna Give You Up"
        assert res2["next_code"] == rec["asset_code"]

        # 4. Reverse Lookup by exact code
        lookup1 = mgr.lookup(rec["asset_code"])
        assert len(lookup1) >= 1
        assert lookup1[0]["yt_id"] == "dQw4w9WgXcQ"

        # 5. Reverse Lookup by keyword
        lookup2 = mgr.lookup("Rick Astley")
        assert len(lookup2) >= 1
        assert lookup2[0]["asset_code"] == rec["asset_code"]

    print("[PASS] All YouTube API and registry integration tests passed!")

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    test_api_check_and_lookup()
