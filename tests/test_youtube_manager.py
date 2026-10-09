import os
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from youtube_manager import extract_youtube_id, YouTubeHistoryManager

def test_extract_youtube_id():
    cases = [
        ("https://www.youtube.com/watch?v=Nsm7tkojwnM", "Nsm7tkojwnM"),
        ("https://youtu.be/Nsm7tkojwnM?si=123", "Nsm7tkojwnM"),
        ("https://www.youtube.com/shorts/Nsm7tkojwnM", "Nsm7tkojwnM"),
        ("https://www.youtube.com/embed/Nsm7tkojwnM", "Nsm7tkojwnM"),
        ("Nsm7tkojwnM", "Nsm7tkojwnM"),
        ("https://example.com/not_youtube", None),
        ("", None),
    ]
    for inp, expected in cases:
        assert extract_youtube_id(inp) == expected, f"Failed for {inp}"

def test_history_manager_code_generation(tmp_path):
    storage = tmp_path / "test_history.json"
    mgr = YouTubeHistoryManager(str(storage))

    day_str = datetime.now().strftime("%d%m")
    expected_code1 = f"COP{day_str}_01"
    expected_code2 = f"COP{day_str}_02"

    # Register first video
    rec1 = mgr.register_or_get("https://www.youtube.com/watch?v=11111111111", title="Video 1")
    assert rec1["asset_code"] == expected_code1
    assert rec1["title"] == "Video 1"

    # Register duplicate URL -> should return existing rec1
    dup_check = mgr.check_url("https://youtu.be/11111111111")
    assert dup_check["exists"] is True
    assert dup_check["record"]["asset_code"] == expected_code1

    rec1_again = mgr.register_or_get("https://youtu.be/11111111111")
    assert rec1_again["asset_code"] == expected_code1

    # Register second video -> code2
    rec2 = mgr.register_or_get("https://www.youtube.com/watch?v=22222222222", title="Video 2")
    assert rec2["asset_code"] == expected_code2

    # Lookup by code
    res = mgr.lookup(expected_code1)
    assert len(res) == 1
    assert res[0]["yt_id"] == "11111111111"

    # Lookup by title keyword
    res = mgr.lookup("video 2")
    assert len(res) == 1
    assert res[0]["asset_code"] == expected_code2

    # Register third video with custom prefix 'VID'
    expected_code3 = f"VID{day_str}_01"
    rec3 = mgr.register_or_get("https://www.youtube.com/watch?v=33333333333", title="Video 3", prefix="VID")
    assert rec3["asset_code"] == expected_code3

    # Check peek next code with custom prefix
    next_vid = mgr.peek_next_code(prefix="VID")
    assert next_vid == f"VID{day_str}_02"

    # Verify CSV file is generated
    csv_file = tmp_path / "danh_sach_youtube_goc.csv"
    mgr._sync_csv_unlocked(str(tmp_path))
    assert csv_file.exists()
    content = csv_file.read_text(encoding="utf-8-sig")
    assert expected_code1 in content
    assert expected_code2 in content
    assert expected_code3 in content
    print("All YouTube Manager tests passed successfully!")

if __name__ == "__main__":
    import tempfile
    test_extract_youtube_id()
    with tempfile.TemporaryDirectory() as td:
        test_history_manager_code_generation(Path(td))

