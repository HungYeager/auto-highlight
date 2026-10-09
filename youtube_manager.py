"""
Module: youtube_manager.py
Zero-friction YouTube Asset Code tracking, duplicate detection, and reverse lookup registry.
Format: [PREFIX][DDMM]_[INDEX] (e.g., COP0710_01)
"""

import os
import re
import json
import csv
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List


def extract_youtube_id(url_or_id: str) -> Optional[str]:
    """Extract canonical 11-character YouTube video ID from various URL formats.
    Supports watch?v=, youtu.be/, shorts/, embed/, and raw IDs.
    """
    if not url_or_id or not isinstance(url_or_id, str):
        return None
    s = url_or_id.strip()
    if re.fullmatch(r"[a-zA-Z0-9_\-]{11}", s):
        return s

    patterns = [
        r"(?:v=|\/v\/|embed\/|shorts\/|youtu\.be\/|\/e\/)([a-zA-Z0-9_\-]{11})",
        r"(?:watch\?.*v=)([a-zA-Z0-9_\-]{11})",
    ]
    for p in patterns:
        m = re.search(p, s)
        if m:
            return m.group(1)
    return None


class YouTubeHistoryManager:
    """Thread-safe persistent registry for YouTube asset codes, duplicate detection, and reverse lookup."""

    def __init__(self, storage_path: Optional[str] = None):
        self.lock = threading.Lock()
        self.storage_path = Path(storage_path) if storage_path else Path(__file__).parent / "youtube_history.json"
        self._load()

    def _load(self):
        with self.lock:
            if self.storage_path.exists():
                try:
                    with open(self.storage_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.by_yt_id: Dict[str, Dict[str, Any]] = data.get("by_yt_id", {})
                    self.by_code: Dict[str, str] = data.get("by_code", {})
                    self.daily_counters: Dict[str, int] = data.get("daily_counters", {})
                    return
                except Exception as e:
                    print(f"[YouTubeHistoryManager] Error reading {self.storage_path}: {e}")
            self.by_yt_id = {}
            self.by_code = {}
            self.daily_counters = {}

    def _save_unlocked(self):
        try:
            temp_path = self.storage_path.with_suffix(".tmp")
            data = {
                "by_yt_id": self.by_yt_id,
                "by_code": self.by_code,
                "daily_counters": self.daily_counters,
            }
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            temp_path.replace(self.storage_path)
        except Exception as e:
            print(f"[YouTubeHistoryManager] Error saving history: {e}")

    def peek_next_code(self, prefix: str = "COP", target_date: Optional[datetime] = None) -> str:
        """Preview what the next code will be for today without incrementing counter."""
        now = target_date or datetime.now()
        day_str = now.strftime("%d%m")
        date_key = now.strftime("%Y%m%d")
        clean_prefix = (prefix or "COP").strip().upper()
        counter_key = f"{clean_prefix}_{date_key}"
        with self.lock:
            curr = self.daily_counters.get(counter_key, 0)
            if curr == 0 and clean_prefix == "COP":
                curr = self.daily_counters.get(date_key, 0)
            next_idx = curr + 1
            code = f"{clean_prefix}{day_str}_{next_idx:02d}"
            while code in self.by_code:
                next_idx += 1
                code = f"{clean_prefix}{day_str}_{next_idx:02d}"
            return code

    def check_url(self, url: str, prefix: str = "COP") -> Dict[str, Any]:
        """Fast instant check whether a YouTube URL has been processed before."""
        yt_id = extract_youtube_id(url)
        if not yt_id:
            return {"valid": False, "exists": False, "yt_id": None, "record": None, "next_code": ""}

        with self.lock:
            record = self.by_yt_id.get(yt_id)
            if record:
                return {
                    "valid": True,
                    "exists": True,
                    "yt_id": yt_id,
                    "record": record,
                    "next_code": record.get("asset_code", ""),
                }

        next_code = self.peek_next_code(prefix)
        return {
            "valid": True,
            "exists": False,
            "yt_id": yt_id,
            "record": None,
            "next_code": next_code,
        }

    def register_or_get(
        self,
        url: str,
        title: str = "",
        duration: float = 0.0,
        channel: str = "",
        prefix: str = "COP",
        output_folder: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Registers a YouTube video into history if not already present.
        Returns the existing or newly created record with its asset_code.
        """
        yt_id = extract_youtube_id(url)
        if not yt_id:
            return {}

        now = datetime.now()
        day_str = now.strftime("%d%m")
        date_key = now.strftime("%Y%m%d")
        clean_prefix = (prefix or "COP").strip().upper()
        counter_key = f"{clean_prefix}_{date_key}"

        canonical_url = f"https://www.youtube.com/watch?v={yt_id}"

        with self.lock:
            if yt_id in self.by_yt_id:
                rec = self.by_yt_id[yt_id]
                # Update title/duration if previously missing
                if not rec.get("title") and title:
                    rec["title"] = title
                if not rec.get("duration") and duration:
                    rec["duration"] = duration
                if not rec.get("channel") and channel:
                    rec["channel"] = channel
                self._save_unlocked()
                self._sync_csv_unlocked(output_folder)
                return rec

            # Generate unique code for today under this prefix
            curr_idx = self.daily_counters.get(counter_key, 0)
            if curr_idx == 0 and clean_prefix == "COP":
                curr_idx = self.daily_counters.get(date_key, 0)
            curr_idx += 1
            code = f"{clean_prefix}{day_str}_{curr_idx:02d}"
            # Ensure no code collision across restarts
            while code in self.by_code:
                curr_idx += 1
                code = f"{clean_prefix}{day_str}_{curr_idx:02d}"

            self.daily_counters[counter_key] = curr_idx

            rec = {
                "asset_code": code,
                "yt_id": yt_id,
                "url": canonical_url,
                "title": title or "YouTube Video",
                "duration": duration,
                "channel": channel,
                "date_added": now.strftime("%d/%m/%Y"),
                "created_at": now.isoformat(),
                "clips_count": 0,
                "clip_names": [],
            }
            self.by_yt_id[yt_id] = rec
            self.by_code[code] = yt_id
            self._save_unlocked()
            self._sync_csv_unlocked(output_folder)
            return rec

    def increment_clips(self, yt_id_or_code: str, clip_name: str = "", output_folder: Optional[str] = None):
        """Record that a clip was cut/exported for this YouTube asset."""
        with self.lock:
            yt_id = yt_id_or_code
            if yt_id in self.by_code:
                yt_id = self.by_code[yt_id]
            if yt_id in self.by_yt_id:
                rec = self.by_yt_id[yt_id]
                rec["clips_count"] = rec.get("clips_count", 0) + 1
                if clip_name:
                    clips = rec.setdefault("clip_names", [])
                    if clip_name not in clips:
                        clips.append(clip_name)
                self._save_unlocked()
                self._sync_csv_unlocked(output_folder)

    def lookup(self, query: str) -> List[Dict[str, Any]]:
        """Find videos by Asset Code, YouTube ID, or Title keyword."""
        q = (query or "").strip().lower()
        if not q:
            return []

        results = []
        with self.lock:
            # Check exact code match first
            upper_q = q.upper()
            if upper_q in self.by_code:
                rec = self.by_yt_id.get(self.by_code[upper_q])
                if rec:
                    return [rec]

            for rec in self.by_yt_id.values():
                code = rec.get("asset_code", "").lower()
                yt_id = rec.get("yt_id", "").lower()
                title = rec.get("title", "").lower()
                url = rec.get("url", "").lower()
                if q in code or q in yt_id or q in title or q in url:
                    results.append(rec)

        # Sort newest first
        results.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return results

    def get_all(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return history records sorted by newest first."""
        with self.lock:
            records = list(self.by_yt_id.values())
        records.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return records[:limit]

    def _sync_csv_unlocked(self, output_folder: Optional[str] = None):
        """Export a clean, UTF-8 BOM CSV that opens directly in Microsoft Excel."""
        target_dirs = [Path(".")]
        if output_folder:
            out_p = Path(output_folder)
            if out_p.exists() and out_p.is_dir():
                target_dirs.append(out_p)

        headers = ["Mã Video", "Ngày Làm", "Tiêu Đề Video", "Link YouTube Gốc", "Số Lượng Clip", "YouTube ID"]
        records = sorted(self.by_yt_id.values(), key=lambda r: r.get("created_at", ""), reverse=True)

        for d in target_dirs:
            try:
                csv_p = d / "danh_sach_youtube_goc.csv"
                with open(csv_p, "w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                    for r in records:
                        writer.writerow([
                            r.get("asset_code", ""),
                            r.get("date_added", ""),
                            r.get("title", ""),
                            r.get("url", ""),
                            r.get("clips_count", 0),
                            r.get("yt_id", ""),
                        ])
            except Exception:
                pass


# Global singleton
yt_history_manager = YouTubeHistoryManager()
