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
            code = f"{clean_prefix}{day_str}{next_idx:02d}"
            while code in self.by_code:
                next_idx += 1
                code = f"{clean_prefix}{day_str}{next_idx:02d}"
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

            # Generate unique code for today under this prefix (no middle underscore: H081060)
            curr_idx = self.daily_counters.get(counter_key, 0)
            if curr_idx == 0 and clean_prefix == "COP":
                curr_idx = self.daily_counters.get(date_key, 0)
            curr_idx += 1
            code = f"{clean_prefix}{day_str}{curr_idx:02d}"
            # Ensure no code collision across restarts
            existing_clean_codes = {c.replace("_", "") for c in self.by_code}
            while code in self.by_code or code in existing_clean_codes:
                curr_idx += 1
                code = f"{clean_prefix}{day_str}{curr_idx:02d}"

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
            else:
                # Support code match without underscore (e.g. H081060 vs H0810_60)
                clean_target = yt_id.replace("_", "").upper()
                for c_key, yid in self.by_code.items():
                    if c_key.replace("_", "").upper() == clean_target:
                        yt_id = yid
                        break

            if yt_id in self.by_yt_id:
                rec = self.by_yt_id[yt_id]
                rec["clips_count"] = rec.get("clips_count", 0) + 1
                if clip_name:
                    clips = rec.setdefault("clip_names", [])
                    if clip_name not in clips:
                        clips.append(clip_name)
                self._save_unlocked()
                self._sync_csv_unlocked(output_folder)

    def _match_single_token_unlocked(self, token: str) -> List[Dict[str, Any]]:
        """Match a single query token (Asset Code, Clip Code like H28104901, Filename, YT URL/ID, or Title)."""
        t = (token or "").strip()
        if not t:
            return []

        # 1. Check if token is a YouTube URL or 11-char ID
        extracted_id = extract_youtube_id(t)
        if extracted_id and extracted_id in self.by_yt_id:
            return [self.by_yt_id[extracted_id]]

        # 2. If token looks like a clip filename (e.g. "H31100103_Police Track Down.mp4"), extract code prefix
        stem = re.sub(r"\.(mp4|mkv|mov|webm|avi)$", "", t, flags=re.I).strip()
        code_candidate = stem.split("_")[0].strip() if "_" in stem else stem
        upper_cand = code_candidate.upper().replace("_", "")

        # Direct code match
        if upper_cand in self.by_code:
            rec = self.by_yt_id.get(self.by_code[upper_cand])
            if rec:
                return [rec]
        for c_key, yid in self.by_code.items():
            c_clean = c_key.replace("_", "").upper()
            if c_clean == upper_cand:
                rec = self.by_yt_id.get(yid)
                if rec:
                    return [rec]
            # Clip code match: e.g. H28104901 (base code H281049 + 2-digit clip index 01)
            if len(upper_cand) >= len(c_clean) + 1 and upper_cand.startswith(c_clean) and upper_cand[len(c_clean):].isdigit():
                rec = self.by_yt_id.get(yid)
                if rec:
                    return [rec]

        # 3. Substring search across code, yt_id, title, url, and clip_names
        q_low = t.lower()
        q_clean = q_low.replace("_", "")
        matched = []
        for rec in self.by_yt_id.values():
            code = rec.get("asset_code", "").lower()
            clean_code = code.replace("_", "")
            yt_id = rec.get("yt_id", "").lower()
            title = rec.get("title", "").lower()
            url = rec.get("url", "").lower()
            clip_names_str = " ".join(rec.get("clip_names", [])).lower()
            if (
                q_low in code
                or q_clean in clean_code
                or q_low in yt_id
                or q_low in title
                or q_low in url
                or q_low in clip_names_str
            ):
                matched.append(rec)

        matched.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return matched

    def lookup_with_meta(self, query: str) -> Dict[str, Any]:
        """Support both single search and batch lookup (multiple codes, filenames, or URLs)."""
        raw = (query or "").strip()
        if not raw:
            return {"results": [], "not_found": [], "is_batch": False, "queried_count": 0}

        # Split by newline, comma, semicolon, or tab first
        lines = [p.strip() for p in re.split(r"[\r\n,;\t]+", raw) if p.strip()]

        # If a single line has multiple whitespace-separated tokens that ALL look like codes or URLs, split by whitespace too
        tokens: List[str] = []
        code_or_url_re = re.compile(
            r"^(?:https?://\S+|[A-Za-z]{1,8}\d{4,10}(?:_[^\s]+)?|[A-Za-z0-9_\-]{11})$"
        )
        for ln in lines:
            parts = ln.split()
            if len(parts) > 1 and all(code_or_url_re.match(p) for p in parts):
                tokens.extend(parts)
            else:
                tokens.append(ln)

        is_batch = len(tokens) > 1
        seen_yt_ids = set()
        results: List[Dict[str, Any]] = []
        not_found: List[str] = []

        with self.lock:
            for tok in tokens:
                hits = self._match_single_token_unlocked(tok)
                if not hits:
                    not_found.append(tok)
                else:
                    for h in hits:
                        yid = h.get("yt_id") or h.get("asset_code")
                        if yid not in seen_yt_ids:
                            seen_yt_ids.add(yid)
                            # Attach which query token matched if batch mode
                            rec_copy = dict(h)
                            if is_batch:
                                rec_copy["matched_query"] = tok
                            results.append(rec_copy)

        return {
            "results": results,
            "not_found": not_found,
            "is_batch": is_batch,
            "queried_count": len(tokens),
        }

    def lookup(self, query: str) -> List[Dict[str, Any]]:
        """Find videos by Asset Code(s), Clip Code(s), YouTube ID/URL(s), or Title keyword."""
        return self.lookup_with_meta(query).get("results", [])

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
