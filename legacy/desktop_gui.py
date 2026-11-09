# -*- coding: utf-8 -*-
"""
Legacy Tkinter Desktop GUI for OpenCut Bodycam Studio (CliperApp & VideoPlayer)
===============================================================================
Extracted from app.py so the headless FastAPI Web Studio does not load
6,000 lines of Tkinter GUI classes at startup.
"""
import app as _core
from app import *
for _k, _v in vars(_core).items():
    if _k.startswith('_') and not _k.startswith('__'):
        globals()[_k] = _v

# ──────────────────────────────────────────────────────────────────────────────
# Premium UI Widget Classes
# ──────────────────────────────────────────────────────────────────────────────

class ToolTip:
    """Hover tooltip — shows after 400ms delay, hides immediately on leave."""

    def __init__(self, widget, text: str, delay: int = 500):
        self._widget   = widget
        self._text     = text
        self._delay    = delay
        self._tw: Optional[tk.Toplevel] = None
        self._after_id = None
        widget.bind("<Enter>",       self._schedule,   add="+")
        widget.bind("<Leave>",       self._hide,       add="+")
        widget.bind("<ButtonPress>", self._hide,       add="+")
        widget.bind("<Destroy>",     self._on_destroy, add="+")

    def _cancel_pending(self):
        if self._after_id:
            try:
                self._widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _schedule(self, _event=None):
        self._cancel_pending()  # reset timer if cursor re-enters quickly
        try:
            self._after_id = self._widget.after(self._delay, self._show)
        except Exception:
            pass

    def _show(self):
        self._after_id = None
        if self._tw:
            return
        try:
            x = self._widget.winfo_rootx() + 20
            y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        except Exception:
            return
        self._tw = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)
        # Hide if cursor enters the tooltip window itself
        tw.bind("<Enter>", self._hide)
        frame = tk.Frame(tw, bg="#2d2d40", bd=1, relief="solid",
                         highlightbackground=CLR_BORDER, highlightthickness=1)
        frame.pack()
        tk.Label(frame, text=self._text, bg="#2d2d40", fg="#d4d4e8",
                 font=("Segoe UI", 8), padx=8, pady=4,
                 wraplength=280, justify="left").pack()

    def _hide(self, _event=None):
        self._cancel_pending()
        if self._tw:
            try:
                self._tw.destroy()
            except Exception:
                pass
            self._tw = None

    def _on_destroy(self, _event=None):
        """Widget is being destroyed — clean up without referencing it."""
        self._after_id = None   # can't cancel, widget gone
        if self._tw:
            try:
                self._tw.destroy()
            except Exception:
                pass
            self._tw = None

    def update_text(self, text: str):
        self._text = text



class Toast:
    """Slide-in notification overlay — auto-dismisses after a timeout."""

    _active: list = []   # class-level stack of visible toasts

    def __init__(self, parent: tk.Tk, message: str,
                 kind: str = "info", duration: int = 3500):
        colors = {
            "info":    (CLR_ACCENT,  "#1e1b3a"),
            "success": (CLR_SUCCESS, "#0f2a1f"),
            "warning": (CLR_WARN,    "#2a2000"),
            "error":   (CLR_ERROR,   "#2a0f0f"),
        }
        fg, bg = colors.get(kind, colors["info"])
        icons  = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✕"}

        # Stack offset so multiple toasts don't overlap
        stack_offset = len(Toast._active) * 52

        self._frame = tk.Frame(parent, bg=bg, highlightbackground=fg,
                               highlightthickness=1, padx=12, pady=8)
        self._frame.place(relx=1.0, rely=1.0, anchor="se",
                          x=-16, y=-(16 + stack_offset))

        tk.Label(self._frame, text=f"{icons.get(kind, 'ℹ')}  {message}",
                 bg=bg, fg=fg, font=("Segoe UI", 9, "bold")).pack(side=LEFT)

        Toast._active.append(self)
        parent.after(duration, self._dismiss)

    def _dismiss(self):
        try:
            Toast._active.remove(self)
        except ValueError:
            pass
        try:
            self._frame.destroy()
        except Exception:
            pass


class PremiumScale(tk.Canvas):
    """Custom-drawn slider replacing the ugly default tk.Scale.

    Features:
    - Rounded track with accent fill
    - Circular thumb with hover glow
    - Value label that follows the thumb
    """

    def __init__(self, parent, variable, from_=0, to=100, resolution=1,
                 orient=HORIZONTAL, command=None, value_format=None,
                 width=None, **kw):
        h = 36
        super().__init__(parent, height=h, bg=CLR_BG, highlightthickness=0,
                         cursor="hand2")
        if width:
            self.configure(width=width)

        self._var       = variable
        self._from      = float(from_)
        self._to        = float(to)
        self._res       = float(resolution)
        self._cmd       = command
        self._fmt       = value_format  # e.g. "{:.1f}" or "{:.0f}°"
        self._dragging  = False
        self._hover     = False

        # Layout constants
        self._pad    = 14          # horizontal padding
        self._track_y = h // 2     # vertical center
        self._track_h = 4          # track thickness
        self._thumb_r = 7          # thumb radius

        self.bind("<Configure>", self._on_resize)
        self.bind("<Button-1>",  self._on_click)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))

        # Redraw when variable changes externally
        self._var.trace_add("write", lambda *_: self._draw())

    def _set_hover(self, h):
        self._hover = h
        self._draw()

    def _val_to_x(self, val):
        w = self.winfo_width() or 200
        track_w = w - 2 * self._pad
        frac = (val - self._from) / max(self._to - self._from, 1e-9)
        return self._pad + frac * track_w

    def _x_to_val(self, x):
        w = self.winfo_width() or 200
        track_w = w - 2 * self._pad
        frac = max(0.0, min(1.0, (x - self._pad) / max(track_w, 1)))
        raw = self._from + frac * (self._to - self._from)
        # Snap to resolution
        if self._res > 0:
            raw = round(raw / self._res) * self._res
        return max(self._from, min(self._to, raw))

    def _on_resize(self, _e=None):
        self._draw()

    def _on_click(self, e):
        self._dragging = True
        val = self._x_to_val(e.x)
        self._var.set(val)
        self._fire_command(val)

    def _on_drag(self, e):
        if self._dragging:
            val = self._x_to_val(e.x)
            self._var.set(val)
            self._fire_command(val)

    def _on_release(self, _e):
        self._dragging = False
        self._draw()

    def _fire_command(self, val):
        if self._cmd:
            try:
                self._cmd(str(val))
            except Exception:
                pass

    def _draw(self):
        self.delete("all")
        w = self.winfo_width() or 200
        y = self._track_y
        pad = self._pad
        track_w = w - 2 * pad

        try:
            val = float(self._var.get())
        except (ValueError, tk.TclError):
            val = self._from

        frac = (val - self._from) / max(self._to - self._from, 1e-9)
        frac = max(0.0, min(1.0, frac))
        thumb_x = pad + frac * track_w

        # Track background (dark rounded rect)
        self._round_rect(pad, y - 2, w - pad, y + 2, 2, CLR_BORDER, CLR_BORDER)
        # Track fill (accent)
        if thumb_x > pad + 2:
            self._round_rect(pad, y - 2, thumb_x, y + 2, 2, CLR_ACCENT, CLR_ACCENT)

        # Thumb
        r = self._thumb_r + (2 if self._hover or self._dragging else 0)
        # Outer glow on hover
        if self._hover or self._dragging:
            self.create_oval(thumb_x - r - 3, y - r - 3,
                             thumb_x + r + 3, y + r + 3,
                             fill="", outline=CLR_ACCENT_H, width=1)
        # Thumb circle
        self.create_oval(thumb_x - r, y - r, thumb_x + r, y + r,
                         fill=CLR_ACCENT if not self._dragging else CLR_ACCENT_H,
                         outline="", width=0)
        # Inner dot
        self.create_oval(thumb_x - 2, y - 2, thumb_x + 2, y + 2,
                         fill="#ffffff", outline="")

        # Value label above thumb
        if self._fmt:
            txt = self._fmt.format(val)
        else:
            txt = f"{val:g}"
        self.create_text(thumb_x, y - r - 8, text=txt,
                         fill=CLR_FG2, font=("Segoe UI", 7), anchor="s")

    def _round_rect(self, x1, y1, x2, y2, r, fill, outline):
        """Draw a small rounded rectangle (for the track)."""
        self.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=0)


class AccentButton(tk.Button):
    """Primary action button — gradient-like accent fill, glow on hover."""

    def __init__(self, parent, text="", command=None, icon="", **kw):
        display = f"{icon}  {text}" if icon else text
        font  = kw.pop("font",  ("Segoe UI", 11, "bold"))
        pady  = kw.pop("pady",  9)
        padx  = kw.pop("padx",  16)
        super().__init__(
            parent, text=display, command=command,
            bg=CLR_ACCENT, fg="white", activebackground=CLR_ACCENT_D,
            activeforeground="white", font=font,
            relief=FLAT, cursor="hand2", pady=pady, padx=padx, bd=0,
            **kw,
        )
        self.bind("<Enter>", lambda e: self.config(bg=CLR_ACCENT_H) if self["state"] != "disabled" else None)
        self.bind("<Leave>", lambda e: self.config(bg=CLR_ACCENT) if self["state"] != "disabled" else None)


class SecondaryButton(tk.Button):
    """Secondary action button — subtle outlined style."""

    _BG = "#1e1e2e"
    _BG_H = "#2a2a3e"

    def __init__(self, parent, text="", command=None, icon="", **kw):
        display = f"{icon}  {text}" if icon else text
        font  = kw.pop("font",  ("Segoe UI", 10, "bold"))
        pady  = kw.pop("pady",  7)
        padx  = kw.pop("padx",  12)
        super().__init__(
            parent, text=display, command=command,
            bg=self._BG, fg=CLR_FG, activebackground=self._BG_H,
            activeforeground=CLR_FG, font=font,
            relief=FLAT, cursor="hand2", pady=pady, padx=padx, bd=0,
            highlightbackground=CLR_BORDER, highlightthickness=1,
            **kw,
        )
        self.bind("<Enter>", lambda e: self.config(bg=self._BG_H) if self["state"] != "disabled" else None)
        self.bind("<Leave>", lambda e: self.config(bg=self._BG) if self["state"] != "disabled" else None)


class DangerButton(tk.Button):
    """Destructive action button — red-tinted."""

    _BG   = "#2a1215"
    _BG_H = "#3d1a1e"

    def __init__(self, parent, text="", command=None, icon="", **kw):
        display = f"{icon}  {text}" if icon else text
        font  = kw.pop("font",  ("Segoe UI", 10, "bold"))
        pady  = kw.pop("pady",  7)
        padx  = kw.pop("padx",  12)
        super().__init__(
            parent, text=display, command=command,
            bg=self._BG, fg=CLR_ERROR, activebackground=self._BG_H,
            activeforeground="#fca5a5", font=font,
            relief=FLAT, cursor="hand2", pady=pady, padx=padx, bd=0,
            **kw,
        )
        self.bind("<Enter>", lambda e: self.config(bg=self._BG_H) if self["state"] != "disabled" else None)
        self.bind("<Leave>", lambda e: self.config(bg=self._BG) if self["state"] != "disabled" else None)


class SuccessButton(tk.Button):
    """Success / positive action button — green-tinted."""

    _BG   = "#0a2a1e"
    _BG_H = "#0f3d2a"

    def __init__(self, parent, text="", command=None, icon="", **kw):
        display = f"{icon}  {text}" if icon else text
        font  = kw.pop("font",  ("Segoe UI", 10, "bold"))
        pady  = kw.pop("pady",  7)
        padx  = kw.pop("padx",  12)
        super().__init__(
            parent, text=display, command=command,
            bg=self._BG, fg=CLR_SUCCESS, activebackground=self._BG_H,
            activeforeground="#6ee7b7", font=font,
            relief=FLAT, cursor="hand2", pady=pady, padx=padx, bd=0,
            **kw,
        )
        self.bind("<Enter>", lambda e: self.config(bg=self._BG_H) if self["state"] != "disabled" else None)
        self.bind("<Leave>", lambda e: self.config(bg=self._BG) if self["state"] != "disabled" else None)


class SectionCard(tk.Frame):
    """Visual grouping card with accent-bar header and optional collapse."""

    def __init__(self, parent, title: str, collapsible: bool = True, **kw):
        super().__init__(parent, bg=CLR_SURFACE, highlightbackground=CLR_BORDER,
                         highlightthickness=1, padx=0, pady=0, **kw)

        self._collapsed = False
        self._collapsible = collapsible

        # Header row
        hdr = tk.Frame(self, bg=CLR_SURFACE, padx=10, pady=6)
        hdr.pack(fill=X)

        # Accent bar (left edge)
        tk.Frame(hdr, bg=CLR_ACCENT, width=3).pack(side=LEFT, fill=Y, padx=(0, 8))

        self._chevron_lbl = tk.Label(
            hdr, text="▾" if not self._collapsed else "▸",
            bg=CLR_SURFACE, fg=CLR_DIM, font=("Segoe UI", 9),
            cursor="hand2" if collapsible else "",
        )
        if collapsible:
            self._chevron_lbl.pack(side=LEFT, padx=(0, 4))

        tk.Label(hdr, text=title.upper(), bg=CLR_SURFACE, fg=CLR_HEADER,
                 font=("Segoe UI", 9, "bold")).pack(side=LEFT)

        if collapsible:
            hdr.bind("<Button-1>", self._toggle)
            for child in hdr.winfo_children():
                child.bind("<Button-1>", self._toggle)

        # Content area
        self._content = tk.Frame(self, bg=CLR_SURFACE, padx=12)
        self._content.pack(fill=X, pady=(0, 10))

    @property
    def content(self) -> tk.Frame:
        """Return the inner frame where controls should be packed."""
        return self._content

    def _toggle(self, _e=None):
        if not self._collapsible:
            return
        self._collapsed = not self._collapsed
        self._chevron_lbl.config(text="▸" if self._collapsed else "▾")
        if self._collapsed:
            self._content.pack_forget()
        else:
            self._content.pack(fill=X)



# ──────────────────────────────────────────────────────────────────────────────
# Video Player — FFmpeg pipe → PIL → Canvas (no OpenCV needed)
# ──────────────────────────────────────────────────────────────────────────────

PLAYBACK_FPS = 24          # frames per second for preview playback
PLAYBACK_VF  = (
    f"scale={PREVIEW_W}:{PREVIEW_H}:"
    "force_original_aspect_ratio=decrease,"
    f"pad={PREVIEW_W}:{PREVIEW_H}:(ow-iw)/2:(oh-ih)/2:color=black,"
    "format=rgb24"
)


class VideoPlayer:
    """
    Plays a [start, start+duration) window of a video on a tk.Canvas by
    piping raw RGB24 frames from FFmpeg into PIL ImageTk at PLAYBACK_FPS.
    Loops video+audio indefinitely until stop() is called.

    Audio: ffplay subprocess (-nodisp, looped in a daemon thread).
    Video: raw RGB24 frames piped to PIL Canvas on the Tk main thread.
    """

    def __init__(self, canvas: tk.Canvas, width: int, height: int,
                 on_state_change=None):
        self._canvas      = canvas
        self._w           = width
        self._h           = height
        self._on_state    = on_state_change   # callback(playing: bool)
        self._stop_evt    = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._photo_ref   = None              # keep ImageTk ref alive
        self._audio_proc: Optional[subprocess.Popen] = None
        self._audio_lock  = threading.Lock()
        self._audio_thread: Optional[threading.Thread] = None
        # Track the active FFmpeg decode pipe so stop() can kill it to
        # unblock the blocking proc.stdout.read() in _run.
        self._video_proc: Optional[subprocess.Popen] = None
        self._video_proc_lock = threading.Lock()
        # Monotonic counter — incremented each play(); old _audio_loops bail.
        self._audio_gen  = 0
        # Event set when the first video frame is decoded; audio waits on this
        # so that both streams start from the same wall-clock moment.
        self._first_frame_evt = threading.Event()

    # ── Public API ─────────────────────────────────────────────────────────

    def play(self, video_path: Path, start_sec: float,
             duration: float = CLIP_DURATION):
        """Stop any running playback then start fresh (video + audio)."""
        self.stop()
        self._stop_evt.clear()
        self._first_frame_evt.clear()   # reset sync gate for this play()
        self._thread = threading.Thread(
            target=self._run,
            args=(video_path, start_sec, duration),
            daemon=True,
        )
        self._thread.start()
        # Start audio ONLY after the first video frame is ready so both
        # streams begin from the same perceived moment (A/V sync fix).
        def _sync_audio():
            self._first_frame_evt.wait(timeout=3.0)   # max 3s for first frame
            if not self._stop_evt.is_set():
                self._start_audio(video_path, start_sec, duration)
        threading.Thread(target=_sync_audio, daemon=True).start()
        if self._on_state:
            self._canvas.after(0, lambda: self._on_state(True))

    def stop(self):
        self._stop_evt.set()
        self._first_frame_evt.set()   # unblock any waiting _sync_audio thread
        self._stop_audio()
        # Kill the FFmpeg decode pipe so proc.stdout.read() in _run unblocks.
        # Without this, each stop() leaks a thread + process indefinitely.
        with self._video_proc_lock:
            vp, self._video_proc = self._video_proc, None
        if vp and vp.poll() is None:
            try:
                vp.kill()
            except Exception:
                pass
        # Do NOT join — called from Tk main thread; join would freeze UI.
        self._thread = None
        if self._on_state:
            try:
                self._canvas.after(0, lambda: self._on_state(False))
            except Exception:
                pass

    # ── Audio (ffplay — ships with FFmpeg, no extra pip deps) ─────────────

    def _start_audio(self, video_path: Path, start_sec: float,
                     duration: float):
        """
        Play audio via ffplay hidden subprocess.
        A daemon thread loops ffplay each time the 16s segment ends.
        """
        self._stop_audio()  # kill any previous audio first

        # Bump gen BEFORE clearing _stop_evt so that any old _audio_loop
        # that wakes from proc.wait() sees a stale gen and exits instead of
        # restarting a new ffplay (the race that doubled audio processes).
        self._audio_gen += 1
        my_audio_gen = self._audio_gen

        # CREATE_NO_WINDOW keeps the console hidden on Windows.
        NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        def _make_proc():
            try:
                return subprocess.Popen(
                    [
                        FFPLAY,
                        "-nodisp", "-autoexit",
                        "-loglevel", "quiet",
                        "-ss", str(start_sec),
                        "-t",  str(duration),
                        str(video_path),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    creationflags=NO_WIN,
                )
            except Exception:
                return None

        def _audio_loop():
            # Guard against the play() race: stop() sets _stop_evt, then
            # play() clears it; old loop would restart without this check.
            while not self._stop_evt.is_set() and my_audio_gen == self._audio_gen:
                proc = _make_proc()
                if proc is None:
                    break
                with self._audio_lock:
                    self._audio_proc = proc
                proc.wait()     # blocks until 16s segment ends
                with self._audio_lock:
                    self._audio_proc = None
                # Immediately loop back

        self._audio_thread = threading.Thread(
            target=_audio_loop, daemon=True)
        self._audio_thread.start()

    def _stop_audio(self):
        """Terminate ffplay immediately."""
        with self._audio_lock:
            proc = self._audio_proc
            self._audio_proc = None
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass



    @property
    def is_playing(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Worker ─────────────────────────────────────────────────────────────

    def _run(self, video_path: Path, start_sec: float, duration: float):
        frame_size   = self._w * self._h * 3          # RGB24 bytes per frame
        frame_delay  = 1.0 / PLAYBACK_FPS

        while not self._stop_evt.is_set():
            proc = self._open_pipe(video_path, start_sec, duration)
            if proc is None:
                break

            # Register so stop() can kill this proc to unblock the read
            with self._video_proc_lock:
                self._video_proc = proc

            session_start = None
            frame_idx = 0
            try:
                while not self._stop_evt.is_set():
                    # Read one full frame — loop because Windows pipes
                    # may return fewer bytes than requested in a single call.
                    raw  = b""
                    need = frame_size
                    while need > 0 and not self._stop_evt.is_set():
                        chunk = proc.stdout.read(need)
                        if not chunk:
                            need = -1   # pipe closed / EOF (or proc killed)
                            break
                        raw  += chunk
                        need -= len(chunk)

                    if len(raw) < frame_size:
                        # Segment finished, pipe closed, or stop() killed proc
                        break

                    # Signal audio thread that first frame is ready (A/V sync).
                    # Only set once per play() call; subsequent frames skip this.
                    if not self._first_frame_evt.is_set():
                        session_start = time.monotonic()
                        self._first_frame_evt.set()

                    if session_start is None:
                        session_start = time.monotonic()

                    # Calculate ideal display time for this frame
                    ideal_elapsed = frame_idx * frame_delay
                    actual_elapsed = time.monotonic() - session_start
                    wait_time = ideal_elapsed - actual_elapsed

                    # If this frame is too late (e.g. lagging behind by more than 2 frames),
                    # skip rendering it to catch up with the audio.
                    if wait_time < -2 * frame_delay:
                        frame_idx += 1
                        continue

                    img = Image.frombuffer("RGB", (self._w, self._h), raw)

                    # IMPORTANT: ImageTk.PhotoImage must be created on the
                    # Tk main thread. Pass the PIL Image via after() and
                    # construct the PhotoImage inside that callback.
                    def _draw(i=img):
                        p = ImageTk.PhotoImage(i)   # ← main thread ✓
                        self._photo_ref = p
                        self._canvas.delete("all")
                        self._canvas.create_image(
                            self._w // 2, self._h // 2,
                            image=p, anchor="center",
                        )
                    self._canvas.after(0, _draw)

                    if wait_time > 0:
                        time.sleep(wait_time)

                    frame_idx += 1

            finally:
                with self._video_proc_lock:
                    if self._video_proc is proc:
                        self._video_proc = None
                try:
                    proc.stdout.close()
                    proc.wait(timeout=2)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

    def _open_pipe(self, video_path: Path, start_sec: float,
                   duration: float) -> Optional[subprocess.Popen]:
        """Start an FFmpeg process that outputs raw RGB24 to stdout."""
        cmd = [
            FFMPEG, "-loglevel", "quiet",
            "-ss", str(start_sec),
            "-i",  str(video_path),
            "-t",  str(duration),
            "-vf", PLAYBACK_VF,
            "-r",  str(PLAYBACK_FPS),
            "-f",  "rawvideo",
            "-pix_fmt", "rgb24",
            "pipe:1",
        ]
        try:
            return subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
        except Exception:
            return None



# ──────────────────────────────────────────────────────────────────────────────
# Main Application
# ──────────────────────────────────────────────────────────────────────────────

class CliperApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE}  {APP_VERSION}")
        self.geometry("1200x920")
        self.minsize(1020, 760)
        self.configure(bg=CLR_BG)
        self.resizable(True, True)

        self._cfg          = load_config()
        self._stop         = threading.Event()
        self._key_rows: list[dict]   = []
        self._video_files: list[Path] = []
        # per-video results: path_str -> {status, candidates, error}
        self._video_results: dict[str, dict] = {}
        self._active_threads: list[threading.Thread] = []
        self._selected_video: Optional[Path] = None
        self._preview_ref    = None          # PIL ImageTk ref
        self._running_count  = 0             # threads still working
        self._last_cut_path: Optional[Path] = None
        self._selected_title_for_reup: str  = ""
        # Tab 2 editor state
        self._edit_queue:    list            = []   # list of {clip_path, title, state}
        self._edit_sel_idx:  int             = -1
        self._frame_cache:   dict            = {}   # str(clip_path) → PIL.Image
        self._edit_bg_cache: dict            = {}   # (key, video_y) → PIL.Image
        self._edit_photo_ref = None                 # keep ImageTk ref alive
        self._edit_drag_origin: tuple        = (0, 0)
        self._drag_text_origin: tuple        = (0, 0)
        # Must be an instance (not class) Lock so it works before _build_ui
        self._preview_proc_lock = threading.Lock()
        self._import_sem = threading.Semaphore(5)

        self._build_styles()
        # Probe available encoders BEFORE building the UI so the encoder
        # combobox in Tab 2 already shows NVENC/QSV if the hardware is present.
        # Takes ~100ms — negligible compared to Tk widget construction time.
        _probe_encoders()
        self._build_ui()
        self._check_deps()
        self._bind_shortcuts()
        self.update_idletasks()
        self._setup_drag_and_drop()
        threading.Thread(target=self._check_for_updates, daemon=True).start()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _toast(self, message: str, kind: str = "info", duration: int = 3500):
        """Show a floating toast notification on the main window."""
        Toast(self, message, kind=kind, duration=duration)

    def _bind_shortcuts(self):
        """Register global keyboard shortcuts."""
        self.bind_all("<Control-Shift-A>",
                      lambda e: self._start_analyze() if self._btn_analyze["state"] != "disabled" else None)
        self.bind_all("<Control-Shift-KeyRelease-A>", lambda e: None)  # absorb keyup
        self.bind_all("<Control-Shift-S>",
                      lambda e: self._stop_work() if self._btn_stop["state"] != "disabled" else None)
        self.bind_all("<Escape>", self._on_escape)
        # KeyRelease (not KeyPress) so auto-repeat doesn't toggle ON→OFF→ON rapidly.
        self.bind_all("<KeyRelease-d>", self._on_d_key)
        self.bind_all("<KeyRelease-D>", self._on_d_key)

    def _on_d_key(self, event):
        """Toggle draw mode with D key — only when Tab 2 is active and no text widget is focused."""
        # Don't intercept D while the user is typing in an Entry, Text, or Spinbox
        focused = self.focus_get()
        if isinstance(focused, (tk.Entry, tk.Text, tk.Spinbox)):
            return
        try:
            tab_idx = self._tab_notebook.index("current")
        except Exception:
            return
        if tab_idx == 1:   # 0 = Analyze, 1 = Edit
            self._toggle_draw_mode()

    def _on_escape(self, _event=None):
        """Escape key: cancel draw mode if active, else unfocus current widget."""
        if getattr(self, "_draw_mode_on", False):
            self._toggle_draw_mode()

    def _on_close(self):
        """Persist config before exit."""
        try:
            self._save_config()
        except Exception:
            pass
        self.destroy()


    # ── Styles ─────────────────────────────────────────────────────────────

    def _build_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TFrame",           background=CLR_BG)
        s.configure("Panel.TFrame",     background=CLR_PANEL)
        s.configure("Surface.TFrame",   background=CLR_SURFACE)
        s.configure("TLabel",           background=CLR_BG, foreground=CLR_FG,
                    font=("Segoe UI", 10))
        s.configure("Panel.TLabel",     background=CLR_PANEL, foreground=CLR_FG,
                    font=("Segoe UI", 10))
        s.configure("Surface.TLabel",   background=CLR_SURFACE, foreground=CLR_FG,
                    font=("Segoe UI", 10))
        s.configure("Section.TLabel",   background=CLR_PANEL, foreground=CLR_HEADER,
                    font=("Segoe UI", 10, "bold"))
        s.configure("BgSection.TLabel", background=CLR_BG,    foreground=CLR_HEADER,
                    font=("Segoe UI", 10, "bold"))
        s.configure("Title.TLabel",     background=CLR_BG,    foreground=CLR_ACCENT,
                    font=("Segoe UI", 16, "bold"))
        s.configure("Status.TLabel",    background=CLR_BG,    foreground=CLR_SUCCESS,
                    font=("Segoe UI", 10, "bold"))
        s.configure("TButton",          font=("Segoe UI", 10),
                    background=CLR_SURFACE, foreground=CLR_FG, borderwidth=0)
        s.map("TButton", background=[("active", CLR_ACCENT)])
        s.configure("TEntry",           fieldbackground=CLR_INPUT_BG,
                    foreground=CLR_FG, insertcolor=CLR_FG,
                    borderwidth=1, relief="flat")
        s.configure("TCombobox",        fieldbackground=CLR_INPUT_BG,
                    foreground=CLR_FG, background=CLR_PANEL,
                    arrowcolor=CLR_FG2)
        s.map("TCombobox", fieldbackground=[("readonly", CLR_INPUT_BG)])
        s.configure("TProgressbar",     troughcolor=CLR_SURFACE,
                    background=CLR_ACCENT, thickness=6)
        s.configure("TSeparator",       background=CLR_BORDER)
        s.configure("Queue.Treeview",   background=CLR_INPUT_BG,
                    foreground=CLR_FG,   fieldbackground=CLR_INPUT_BG,
                    borderwidth=0,       rowheight=30, font=("Segoe UI", 9))
        s.configure("Queue.Treeview.Heading", background=CLR_PANEL,
                    foreground=CLR_DIM,  font=("Segoe UI", 9, "bold"),
                    borderwidth=0)
        s.map("Queue.Treeview", background=[("selected", CLR_ACCENT_D)])
        # Scrollbar — minimal dark style
        s.configure("Vertical.TScrollbar",
                    background=CLR_SURFACE, troughcolor=CLR_BG,
                    arrowcolor=CLR_DIM, borderwidth=0)
        s.map("Vertical.TScrollbar",
              background=[("active", CLR_BORDER), ("pressed", CLR_ACCENT)])

    # ── UI Build ───────────────────────────────────────────────────────────

    def _build_ui(self):
        # Title bar
        top = ttk.Frame(self, padding=(20, 12, 20, 0))
        top.pack(fill=X)
        ttk.Label(top, text=f"🚔  {APP_TITLE}", style="Title.TLabel").pack(side=LEFT)
        self._status_lbl = ttk.Label(top, text="● Ready", style="Status.TLabel")
        self._status_lbl.pack(side=RIGHT)
        ttk.Separator(self, orient=HORIZONTAL).pack(fill=X, padx=20, pady=8)

        # Update banner frame (hidden until update check finds a newer version)
        self._update_banner = ttk.Frame(self, style="Panel.TFrame")

        # Body: left config panel + right main panel
        body = ttk.Frame(self, padding=(20, 0, 20, 0))
        body.pack(fill=BOTH, expand=True)

        # ── Left Panel (scrollable, fixed width 400) ────────────────────
        left_outer = ttk.Frame(body, style="Panel.TFrame")
        left_outer.pack(side=LEFT, fill=Y, expand=False)
        left_outer.configure(width=400)
        left_outer.pack_propagate(False)

        left_canvas = tk.Canvas(left_outer, bg=CLR_PANEL,
                                highlightthickness=0, width=384)
        left_sb = ttk.Scrollbar(left_outer, orient=VERTICAL,
                                command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_sb.set)
        left_sb.pack(side=RIGHT, fill=Y)
        left_canvas.pack(side=LEFT, fill=BOTH, expand=True)

        left_inner = ttk.Frame(left_canvas, style="Panel.TFrame", padding=14)
        self._left_canvas = left_canvas   # saved for scroll-to-bottom on key add
        self._left_win_id = left_canvas.create_window(
            (0, 0), window=left_inner, anchor="nw")
        left_inner.bind("<Configure>",
            lambda e: left_canvas.configure(
                scrollregion=left_canvas.bbox("all")))
        left_canvas.bind("<Configure>",
            lambda e: left_canvas.itemconfig(self._left_win_id, width=e.width))
        left_canvas.bind_all("<MouseWheel>",
            lambda e: left_canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        self._build_left(left_inner)

        # ── Right Panel ─────────────────────────────────────────────────
        right = ttk.Frame(body, padding=(12, 0, 0, 0))
        right.pack(side=RIGHT, fill=BOTH, expand=True)
        self._build_right(right)

        # Progress bar
        foot = ttk.Frame(self, padding=(20, 6, 20, 10))
        foot.pack(fill=X)
        self._prog_var = tk.DoubleVar()
        ttk.Progressbar(foot, variable=self._prog_var, maximum=100,
                        style="TProgressbar").pack(fill=X)
        self._prog_lbl = ttk.Label(foot, text="", font=("Segoe UI", 8),
                                   foreground=CLR_DIM)
        self._prog_lbl.pack(anchor=E, pady=(2, 0))

    # ── Left Panel ─────────────────────────────────────────────────────────

    def _build_left(self, p):
        # ── API KEYS ───────────────────────────────────────────────────────
        api_card = SectionCard(p, "API Keys", collapsible=False)
        api_card.pack(fill=X, pady=(0, 8))
        c = api_card.content

        ttk.Label(c, text="Round-robin load balancing across all keys.",
                  background=CLR_SURFACE, foreground=CLR_DIM,
                  font=("Segoe UI", 8)).pack(anchor=W, pady=(0, 6))

        # Container for dynamic key rows
        self._keys_container = tk.Frame(c, bg=CLR_SURFACE)
        self._keys_container.pack(fill=X, pady=(0, 4))

        # Restore saved keys
        saved_keys = self._cfg.get("api_keys", [])
        if isinstance(saved_keys, str):
            saved_keys = [k.strip() for k in saved_keys.splitlines() if k.strip()]
        if not saved_keys:
            saved_keys = [self._cfg.get("api_key", "")]
        for key in saved_keys:
            self._add_key_row(value=key)
        if not self._key_rows:
            self._add_key_row()

        SecondaryButton(c, text="Add API Key", icon="＋",
                        command=self._add_key_row,
                        font=("Segoe UI", 9, "bold"), pady=4).pack(
            anchor=W, pady=(0, 2))

        # ── AI MODEL ───────────────────────────────────────────────────────
        model_card = SectionCard(p, "AI Model", collapsible=False)
        model_card.pack(fill=X, pady=(0, 8))
        mc = model_card.content

        _model_opts = [
            ("gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite (Recommended)"),
            ("gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite"),
        ]
        self._model_label_to_id = {lbl: mid for mid, lbl in _model_opts}
        self._model_id_to_label = {mid: lbl for mid, lbl in _model_opts}

        saved_model = self._cfg.get("model_name", "gemini-3.5-flash-lite")
        default_label = self._model_id_to_label.get(saved_model, "Gemini 3.5 Flash Lite (Recommended)")

        self._model_var = tk.StringVar(value=default_label)

        m_row = tk.Frame(mc, bg=CLR_SURFACE)
        m_row.pack(fill=X, pady=(0, 4))
        tk.Label(m_row, text="Model:", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 9, "bold"), width=7, anchor=W).pack(side=LEFT)

        model_cb = ttk.Combobox(
            m_row, textvariable=self._model_var,
            values=[lbl for _, lbl in _model_opts],
            state="readonly", font=("Segoe UI", 9)
        )
        model_cb.pack(side=LEFT, fill=X, expand=True)

        # ── CTA Toggle ─────────────────────────────────────────────────────
        self._cta_var = tk.BooleanVar(value=bool(self._cfg.get("include_cta", False)))
        cta_row = tk.Frame(mc, bg=CLR_SURFACE)
        cta_row.pack(fill=X, pady=(2, 0))
        tk.Checkbutton(
            cta_row,
            text="CTA cuối tiêu đề  (👉 Follow for more!)",
            variable=self._cta_var,
            bg=CLR_SURFACE, fg=CLR_FG2,
            selectcolor=CLR_SURFACE,
            activebackground=CLR_SURFACE, activeforeground=CLR_FG,
            font=("Segoe UI", 8),
            command=self._save_config,   # auto-save on toggle
        ).pack(side=LEFT)

        # ── INPUT VIDEOS ───────────────────────────────────────────────────
        vid_card = SectionCard(p, "Input Videos", collapsible=False)
        vid_card.pack(fill=X, pady=(0, 8))
        c = vid_card.content

        sel_row = tk.Frame(c, bg=CLR_SURFACE)
        sel_row.pack(fill=X, pady=(0, 6))
        SecondaryButton(sel_row, text="Select Files…", icon="📂",
                        command=self._pick_video_files,
                        font=("Segoe UI", 9, "bold"), pady=4).pack(side=LEFT)
        DangerButton(sel_row, text="Clear", icon="✕",
                     command=self._clear_video_files,
                     font=("Segoe UI", 9, "bold"), pady=4).pack(side=RIGHT)

        list_frame = tk.Frame(c, bg=CLR_INPUT_BG,
                              highlightbackground=CLR_BORDER, highlightthickness=1)
        list_frame.pack(fill=X, pady=(0, 4))
        self._file_listbox = tk.Listbox(
            list_frame, height=6,
            bg=CLR_INPUT_BG, fg=CLR_FG,
            selectbackground=CLR_ACCENT_D,
            font=("Segoe UI", 9), borderwidth=0, highlightthickness=0,
            activestyle="none",
            selectmode="extended",  # enables Shift+Click, Ctrl+Click multi-select
        )
        lb_sb = ttk.Scrollbar(list_frame, orient=VERTICAL,
                              command=self._file_listbox.yview)
        self._file_listbox.configure(yscrollcommand=lb_sb.set)
        lb_sb.pack(side=RIGHT, fill=Y)
        self._file_listbox.pack(fill=X, expand=True)
        # Hotkeys: Delete removes selected; Ctrl+A selects all
        self._file_listbox.bind("<Delete>",  lambda _e: self._remove_selected_files())
        self._file_listbox.bind("<Control-a>", lambda _e: self._file_listbox.select_set(0, END))

        self._file_count_lbl = tk.Label(c, text="No files selected.",
                                        bg=CLR_SURFACE, fg=CLR_DIM,
                                        font=("Segoe UI", 8))
        self._file_count_lbl.pack(anchor=W, pady=(0, 2))

        # Restore saved file list
        saved_files = self._cfg.get("video_files", [])
        if saved_files:
            existing = [Path(f) for f in saved_files if Path(f).exists()]
            if existing:
                self._video_files = existing
                self._refresh_file_listbox()

        # ── OUTPUT FOLDER ──────────────────────────────────────────────────
        out_card = SectionCard(p, "Output Folder", collapsible=False)
        out_card.pack(fill=X, pady=(0, 8))
        c = out_card.content

        out_row = tk.Frame(c, bg=CLR_SURFACE)
        out_row.pack(fill=X, pady=(0, 4))
        self._output_var = tk.StringVar(value=self._cfg.get("output_folder", ""))
        tk.Entry(out_row, textvariable=self._output_var,
                 bg=CLR_INPUT_BG, fg=CLR_FG, insertbackground=CLR_FG,
                 font=("Segoe UI", 9), relief=FLAT, bd=1,
                 highlightbackground=CLR_BORDER, highlightthickness=1).pack(
            side=LEFT, fill=X, expand=True)
        SecondaryButton(out_row, text="📂",
                        command=lambda: self._pick_folder(self._output_var),
                        font=("Segoe UI", 10), pady=2, padx=6).pack(
            side=RIGHT, padx=(4, 0))

        tk.Label(c, text=f"Clip duration constraint: {CLIP_DURATION}s",
                 bg=CLR_SURFACE, fg=CLR_DIM,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(4, 0))

        # ── ACTION BUTTONS ─────────────────────────────────────────────────
        tk.Frame(p, bg=CLR_BORDER, height=1).pack(fill=X, pady=10)

        self._btn_analyze = AccentButton(
            p, text="ANALYZE ALL", icon="▶",
            command=self._start_analyze,
        )
        self._btn_analyze.pack(fill=X, pady=(0, 6))
        ToolTip(self._btn_analyze, "Analyze all loaded videos in parallel  (Ctrl+Shift+A)")

        self._btn_stop = tk.Button(
            p, text="⏹  STOP ALL",
            bg="#3d0f0f", fg=CLR_ERROR, activebackground="#5a1515",
            activeforeground="#fca5a5",
            font=("Segoe UI", 11, "bold"), relief=FLAT,
            cursor="hand2", pady=9, state=DISABLED,
            command=self._stop_work,
        )
        self._btn_stop.pack(fill=X, pady=(0, 6))

        self._btn_retry = tk.Button(
            p, text="🔄  RETRY ERRORS",
            bg="#2a1800", fg=CLR_WARN, activebackground="#3d2200",
            activeforeground="#fde68a",
            font=("Segoe UI", 10, "bold"), relief=FLAT,
            cursor="hand2", pady=7, state=DISABLED,
            command=self._retry_errors,
        )
        self._btn_retry.pack(fill=X)
        ToolTip(self._btn_retry, "Re-analyze all videos that returned an error")


    # ── Right Panel (Notebook with 2 tabs) ──────────────────────────────────────

    def _build_right(self, p):
        self._tab_notebook = ttk.Notebook(p)
        self._tab_notebook.pack(fill=BOTH, expand=True)

        tab1 = ttk.Frame(self._tab_notebook)
        self._tab_notebook.add(tab1, text="  📋  Analyze & Select  ")

        tab2 = ttk.Frame(self._tab_notebook)
        self._tab_notebook.add(tab2, text="  ✏️  Edit & Export  ")

        self._build_tab1(tab1)
        self._build_tab2(tab2)

    # ── Tab 1: Analyze & Select ───────────────────────────────────────────────

    def _build_tab1(self, p):
        p.configure(padding=(14, 8, 0, 14))

        # ── Scrollable upper section ─────────────────────────────────────────
        # Holds: VIDEO QUEUE, RESULTS, Titles, and Action Buttons.
        # CLIP PREVIEW + LOG are kept fixed at the bottom (always visible).
        upper_outer = ttk.Frame(p)
        upper_outer.pack(fill=BOTH, expand=True)

        upper_canvas = tk.Canvas(upper_outer, bg=CLR_BG, highlightthickness=0)
        upper_sb = ttk.Scrollbar(upper_outer, orient=VERTICAL, command=upper_canvas.yview)
        upper_canvas.configure(yscrollcommand=upper_sb.set)
        upper_sb.pack(side=RIGHT, fill=Y)
        upper_canvas.pack(side=LEFT, fill=BOTH, expand=True)

        scroll_content = ttk.Frame(upper_canvas)
        scroll_win = upper_canvas.create_window((0, 0), window=scroll_content, anchor="nw")

        scroll_content.bind("<Configure>",
            lambda e: upper_canvas.configure(scrollregion=upper_canvas.bbox("all")))
        upper_canvas.bind("<Configure>",
            lambda e: upper_canvas.itemconfig(scroll_win, width=e.width))

        # Mousewheel only active when hovering over this panel
        def _mw(e): upper_canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        upper_canvas.bind("<Enter>",  lambda e: upper_canvas.bind_all("<MouseWheel>", _mw))
        upper_canvas.bind("<Leave>",  lambda e: upper_canvas.unbind_all("<MouseWheel>"))

        # All top-section widgets go into scroll_content, aliased as p_top
        p_top = scroll_content

        # ── VIDEO QUEUE (Treeview) ───────────────────────────────────────
        ttk.Label(p_top, text="VIDEO QUEUE", style="BgSection.TLabel").pack(
            anchor=W, pady=(0, 4))

        queue_frame = ttk.Frame(p_top)
        queue_frame.pack(fill=X, pady=(0, 8))

        self._queue = ttk.Treeview(
            queue_frame,
            columns=("icon", "name", "status"),
            show="headings",
            height=7,
            style="Queue.Treeview",
            selectmode="browse",
        )
        self._queue.heading("icon",   text="")
        self._queue.heading("name",   text="Video File")
        self._queue.heading("status", text="Status")
        self._queue.column("icon",   width=28,  minwidth=28,  stretch=False, anchor=W)
        self._queue.column("name",   width=260, minwidth=120, anchor=W)
        self._queue.column("status", width=140, minwidth=80,  anchor=W)

        # Tag colors for statuses
        self._queue.tag_configure(ST_QUEUED,    foreground=CLR_DIM)
        self._queue.tag_configure(ST_UPLOADING, foreground=CLR_WARN)
        self._queue.tag_configure(ST_ANALYZING, foreground=CLR_WARN)
        self._queue.tag_configure(ST_DONE,      foreground=CLR_SUCCESS)
        self._queue.tag_configure(ST_ERROR,     foreground=CLR_ERROR)

        q_sb = ttk.Scrollbar(queue_frame, orient=VERTICAL, command=self._queue.yview)
        self._queue.configure(yscrollcommand=q_sb.set)
        q_sb.pack(side=RIGHT, fill=Y)
        self._queue.pack(fill=X)
        self._queue.bind("<<TreeviewSelect>>", self._on_queue_select)

        ttk.Separator(p_top, orient=HORIZONTAL).pack(fill=X, pady=(0, 8))

        # ── RESULTS + CUT ─────────────────────────────────────────────────
        results_head = ttk.Frame(p_top)
        results_head.pack(fill=X, pady=(0, 4))
        ttk.Label(results_head, text="RESULTS", style="BgSection.TLabel").pack(side=LEFT)
        self._results_video_lbl = ttk.Label(
            results_head, text="— select a completed video above —",
            font=("Segoe UI", 9), foreground=CLR_DIM)
        self._results_video_lbl.pack(side=LEFT, padx=(8, 0))

        cand_row = ttk.Frame(p_top)
        cand_row.pack(fill=X, pady=(0, 4))
        ttk.Label(cand_row, text="Candidate:").pack(side=LEFT, padx=(0, 6))
        self._cand_var = tk.StringVar(value="—")
        self._cand_box = ttk.Combobox(cand_row, textvariable=self._cand_var,
                                      state="readonly", width=44)
        self._cand_box.pack(side=LEFT, fill=X, expand=True)
        self._cand_box.bind("<<ComboboxSelected>>", self._on_candidate_selected)

        self._reason_txt = scrolledtext.ScrolledText(
            p_top, bg=CLR_INPUT_BG, fg=CLR_DIM,
            font=("Segoe UI", 9), height=3, wrap=WORD,
            state=DISABLED, borderwidth=1, relief=SUNKEN,
        )
        self._reason_txt.pack(fill=X, pady=(0, 6))

        tk.Label(p_top, text="Viral Titles — click to select & copy:",
                 bg=CLR_BG, fg=CLR_FG2, font=("Segoe UI", 9, "bold")).pack(
            anchor=W, pady=(4, 4))
        self._title_btns: list[tk.Button] = []
        for i in range(5):
            btn = tk.Button(
                p_top, text=f"{i+1}. —",
                bg=CLR_SURFACE, fg=CLR_FG,
                font=("Segoe UI", 9), relief=FLAT,
                anchor=W, justify=LEFT,
                wraplength=600, cursor="hand2",
                pady=6, padx=10,
                activebackground=CLR_ACCENT_D,
                highlightbackground=CLR_BORDER, highlightthickness=1,
            )
            btn.pack(fill=X, pady=2)
            self._title_btns.append(btn)

        # CUT button
        self._btn_cut = tk.Button(
            p_top, text="✂  CUT SELECTED CLIP  (exact 16s)",
            bg="#0a2a1e", fg=CLR_SUCCESS,
            activebackground="#0f3d2a", activeforeground="#6ee7b7",
            font=("Segoe UI", 11, "bold"), relief=FLAT,
            cursor="hand2", pady=9,
            state=DISABLED, command=self._start_cut,
        )
        self._btn_cut.pack(fill=X, pady=(10, 0))
        ToolTip(self._btn_cut, "Cut the selected 16-second clip from the source video")

        # Send to Edit Tab button (enabled after a successful cut)
        self._btn_send_edit = tk.Button(
            p_top, text="📤  Send to Edit Tab",
            bg="#0f1e3d", fg="#60a5fa",
            activebackground="#172d5c", activeforeground="#93c5fd",
            font=("Segoe UI", 10, "bold"), relief=FLAT,
            cursor="hand2", pady=7,
            state=DISABLED, command=self._send_to_edit_tab,
        )
        self._btn_send_edit.pack(fill=X, pady=(4, 0))
        ToolTip(self._btn_send_edit, "Add this clip + title to the Edit & Export queue")
        # Dummy label kept for backwards compatibility
        self._reup_title_lbl = tk.Label(p_top, text="", bg=CLR_BG,
                                        fg=CLR_DIM, font=("Segoe UI", 8), wraplength=580)
        self._reup_title_lbl.pack(anchor=W)

        # ── PREVIEW + LOG (side by side) ───────────────────────────────────
        # NOTE: parented to `p` (not p_top) — sits OUTSIDE the scroll area,
        # always visible at the bottom of the tab.
        bottom = ttk.Frame(p)
        bottom.pack(fill=BOTH, expand=False, pady=(6, 0))

        # Preview
        prev_frame = ttk.Frame(bottom, style="Panel.TFrame", padding=6)
        prev_frame.pack(side=LEFT, anchor="nw", expand=False)

        prev_hdr = ttk.Frame(prev_frame, style="Panel.TFrame")
        prev_hdr.pack(fill=X, pady=(0, 4))
        ttk.Label(prev_hdr, text="CLIP PREVIEW", style="Section.TLabel",
                  background=CLR_PANEL).pack(side=LEFT)
        self._prev_lbl = ttk.Label(prev_hdr, text="— select a candidate —",
                                   style="Panel.TLabel", foreground=CLR_DIM,
                                   font=("Segoe UI", 8))
        self._prev_lbl.pack(side=LEFT, padx=(8, 0))

        # Play button lives in the HEADER — always visible regardless of height
        self._btn_play = tk.Button(
            prev_hdr,
            text="▶ Play",
            bg="#1e40af", fg="white",
            font=("Segoe UI", 9, "bold"), relief=FLAT,
            activebackground="#1d4ed8", padx=8, pady=2,
            state=DISABLED,
            command=self._toggle_preview_playback,
        )
        self._btn_play.pack(side=RIGHT, padx=(6, 0))

        self._preview_canvas = tk.Canvas(
            prev_frame, bg="#0d0d1a",
            width=PREVIEW_W, height=PREVIEW_H,
            highlightthickness=1, highlightbackground="#3C3C3C",
        )
        self._preview_canvas.pack(anchor="nw")
        self._draw_preview_placeholder()

        # Instantiate player — canvas is ready
        self._player = VideoPlayer(
            self._preview_canvas, PREVIEW_W, PREVIEW_H,
            on_state_change=self._on_player_state_change,
        )

        # Log
        log_frame = ttk.Frame(bottom, padding=(10, 0, 0, 0))
        log_frame.pack(side=LEFT, fill=BOTH, expand=True)
        ttk.Label(log_frame, text="ACTIVITY LOG", style="BgSection.TLabel").pack(
            anchor=W, pady=(0, 4))
        self._log_widget = scrolledtext.ScrolledText(
            log_frame, bg=CLR_INPUT_BG, fg=CLR_FG,
            font=("Consolas", 8), state=DISABLED,
            wrap=WORD, borderwidth=1, relief=SUNKEN,
        )
        self._log_widget.pack(fill=BOTH, expand=True)
        self._logger = ToolLogger(self._log_widget)

    # ── Tab 2: Edit & Export ─────────────────────────────────────────────────

    def _build_tab2(self, p):
        # ── Top-level: fixed left + scrollable right ──────────────────────────
        outer = ttk.Frame(p)
        outer.pack(fill=BOTH, expand=True)

        # ── Fixed left panel: queue + preview (NEVER scrolls) ─────────────────
        fixed = ttk.Frame(outer, style="Panel.TFrame")
        fixed.pack(side=LEFT, fill=Y, padx=(10, 0), pady=(8, 10))

        # ── Left column: clip queue ───────────────────────────────────────────
        queue_col = ttk.Frame(fixed, style="Panel.TFrame", padding=(6, 6, 6, 6))
        queue_col.pack(side=LEFT, fill=Y, padx=(0, 8))
        queue_col.configure(width=165)
        queue_col.pack_propagate(False)

        # Dynamic queue count label — updated via _update_queue_count_label()
        self._queue_count_var = tk.StringVar(value="QUEUE")
        ttk.Label(queue_col, textvariable=self._queue_count_var,
                  style="Section.TLabel",
                  background=CLR_PANEL).pack(anchor=W, pady=(0, 4))

        # EXTENDED selectmode: Shift+click = range, Ctrl+click = toggle.
        # _on_edit_select still loads only the focused item into the editor;
        # multi-selection is used by bulk Remove.
        self._edit_listbox = tk.Listbox(
            queue_col, bg=CLR_INPUT_BG, fg=CLR_FG,
            font=("Segoe UI", 8), selectbackground="#3730a3",
            activestyle="none", borderwidth=0, highlightthickness=0,
            selectmode=tk.EXTENDED,
        )
        self._edit_listbox.pack(fill=BOTH, expand=True)
        self._edit_listbox.bind("<<ListboxSelect>>", self._on_edit_select)

        tk.Button(
            queue_col, text="🗑 Remove",
            bg="#7f1d1d", fg="white",
            font=("Segoe UI", 8), relief=FLAT, padx=6, pady=3,
            command=self._edit_queue_remove,
        ).pack(fill=X, pady=(6, 0))

        tk.Button(
            queue_col, text="📥 Import 16s Clip",
            bg="#0f766e", fg="white",
            font=("Segoe UI", 8, "bold"), relief=FLAT, padx=6, pady=3,
            command=self._import_16s_clip,
        ).pack(fill=X, pady=(6, 0))

        # ── Middle column: portrait preview canvas (sticky) ───────────────────
        prev_col = ttk.Frame(fixed, style="Panel.TFrame", padding=6)
        prev_col.pack(side=LEFT, fill=Y, padx=(0, 8))

        ttk.Label(prev_col, text="PREVIEW  — drag title │ Draw Mode → blur box",
                  style="Section.TLabel", background=CLR_PANEL).pack(anchor=W, pady=(0, 4))

        self._edit_canvas = tk.Canvas(
            prev_col, width=EDIT_PREV_W, height=EDIT_PREV_H,
            bg="#0d0d1a",
            highlightthickness=1, highlightbackground="#3C3C3C",
            cursor="fleur",
        )
        self._edit_canvas.pack()
        self._draw_edit_placeholder()

        # ── Scrubber bar (seek to any frame in the clip) ──────────────────────
        scrub_row = tk.Frame(prev_col, bg=CLR_PANEL)
        scrub_row.pack(fill=X, pady=(4, 0))
        tk.Label(scrub_row, text="⏱ Seek", bg=CLR_PANEL, fg=CLR_DIM,
                 font=("Segoe UI", 8)).pack(side=LEFT, padx=(0, 6))
        self._scrub_pos = tk.DoubleVar(value=0.0)
        self._scrub_job = None   # debounce after_id

        def _on_scrub(val):
            # Debounce: cancel any pending regen, schedule new one 80ms later
            if self._scrub_job:
                try:
                    self.after_cancel(self._scrub_job)
                except Exception:
                    pass
            self._scrub_job = self.after(80, _seek_frame)

        def _seek_frame():
            self._scrub_job = None
            if self._edit_sel_idx < 0:
                return
            item = self._edit_queue[self._edit_sel_idx]
            clip = item["clip_path"]
            pct  = self._scrub_pos.get() / 100.0
            # Invalidate frame cache for this clip so next regen uses the seeked frame
            src_key = str(clip)
            # Determine timestamp to seek to
            dur = get_video_duration(clip)
            if dur is None:
                dur = 10.0
            seek_t = max(0.1, pct * dur)
            # Extract frame at seek_t and store in cache
            try:
                tmp = Path(tempfile.mktemp(suffix="_scrub.jpg"))
                subprocess.run(
                    [FFMPEG, "-loglevel", "quiet",
                     "-ss", f"{seek_t:.2f}", "-i", str(clip),
                     "-frames:v", "1", "-q:v", "3", str(tmp)],
                    capture_output=True, timeout=8,
                )
                if tmp.exists():
                    from PIL import Image as _PILImage
                    _img = _PILImage.open(tmp).convert("RGB")
                    _img.load()
                    try: tmp.unlink()
                    except Exception: pass
                    self._frame_cache[src_key] = _img
                    # Also clear bg cache so bg refreshes with new frame
                    for k in list(self._edit_bg_cache.keys()):
                        if k[0] == src_key:
                            del self._edit_bg_cache[k]
                    self._regen_edit_preview()
            except Exception:
                pass

        self._scrub_scale = PremiumScale(
            scrub_row, variable=self._scrub_pos,
            from_=0.0, to=100.0, resolution=0.5,
            value_format="{:.0f}%",
            command=_on_scrub,
        )
        self._scrub_scale.pack(side=LEFT, fill=X, expand=True)
        ToolTip(scrub_row, "Drag to seek to any frame in the clip — preview updates automatically")

        # ── Play / Stop preview button ────────────────────────────────────────
        play_row = tk.Frame(prev_col, bg=CLR_PANEL)
        play_row.pack(fill=X, pady=(4, 0))
        self._edit_play_job   = None   # after() loop id
        self._edit_play_proc  = None   # ffmpeg Popen for frame pipe
        self._edit_playing    = False

        def _toggle_play():
            if self._edit_playing:
                self._stop_edit_play()
            else:
                self._start_edit_play()

        self._btn_edit_play = tk.Button(
            play_row, text="▶  Play Preview",
            bg=CLR_ACCENT_D, fg=CLR_FG,
            activebackground=CLR_ACCENT, activeforeground=CLR_FG,
            font=("Segoe UI", 9, "bold"), relief=FLAT, cursor="hand2",
            pady=4, command=_toggle_play,
        )
        self._btn_edit_play.pack(fill=X)
        ToolTip(self._btn_edit_play, "Play the clip as a live preview in the canvas")

        # Draw-mode and resize-mode must be initialised before any canvas event fires
        self._edit_draw_mode   = False
        self._edit_resize_mode = False
        self._edit_canvas.bind("<Button-1>",        self._on_edit_drag_start)
        self._edit_canvas.bind("<B1-Motion>",       self._on_edit_drag)
        self._edit_canvas.bind("<ButtonRelease-1>", self._on_edit_drag_end)
        self._edit_canvas.bind("<Motion>",          self._on_edit_motion)
        # D/d key → toggle draw mode (focus must be on canvas or tab frame)
        self._edit_canvas.bind("<d>", lambda e: self._toggle_draw_mode())
        self._edit_canvas.bind("<D>", lambda e: self._toggle_draw_mode())

        # ── Right side: scrollable controls + pinned export footer ────────────
        right_outer = ttk.Frame(outer)
        right_outer.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 10), pady=(8, 10))

        # Pinned Export footer (always visible at the bottom)
        footer = ttk.Frame(right_outer)
        footer.pack(side=BOTTOM, fill=X, pady=(6, 0))

        # ── Export Settings panel (collapsible) ──────────────────────────────
        exp_outer = tk.Frame(footer, bg=CLR_BORDER, bd=0)
        exp_outer.pack(fill=X, pady=(0, 6))
        exp_inner = tk.Frame(exp_outer, bg=CLR_SURFACE)
        exp_inner.pack(fill=X, padx=1, pady=1)

        # Header row with toggle
        exp_hdr = tk.Frame(exp_inner, bg=CLR_SURFACE)
        exp_hdr.pack(fill=X, pady=(4, 0))
        self._exp_collapsed = tk.BooleanVar(value=False)
        self._exp_chevron = tk.Label(
            exp_hdr, text="▾", bg=CLR_SURFACE, fg=CLR_ACCENT,
            font=("Segoe UI", 11), cursor="hand2")
        self._exp_chevron.pack(side=LEFT, padx=(6, 2))
        tk.Label(exp_hdr, text="⚙️  Export Settings",
                 bg=CLR_SURFACE, fg=CLR_FG2, font=("Segoe UI", 8, "bold"),
                 cursor="hand2").pack(side=LEFT)

        # Content frame that can be shown/hidden
        exp_cfg_frame = tk.Frame(exp_inner, bg=CLR_SURFACE)
        exp_cfg_frame.pack(fill=X, padx=6, pady=(2, 6))

        def _toggle_exp_settings(*_):
            if self._exp_collapsed.get():
                exp_cfg_frame.pack_forget()
                self._exp_chevron.config(text="▸")
                self._exp_collapsed.set(False)   # flip: collapsed=True means hidden
            else:
                exp_cfg_frame.pack(fill=X, padx=6, pady=(2, 6))
                self._exp_chevron.config(text="▾")
                self._exp_collapsed.set(True)

        exp_hdr.bind("<Button-1>", _toggle_exp_settings)
        self._exp_chevron.bind("<Button-1>", _toggle_exp_settings)
        for _w in exp_hdr.winfo_children():
            _w.bind("<Button-1>", _toggle_exp_settings)

        _RC = self._cfg.get("render_cfg", {})

        def _row(parent, label_text):
            r = tk.Frame(parent, bg=CLR_SURFACE)
            r.pack(fill=X, pady=1)
            tk.Label(r, text=label_text, bg=CLR_SURFACE, fg=CLR_FG2,
                     font=("Segoe UI", 8), width=11, anchor=W).pack(side=LEFT)
            return r

        # Resolution
        _res_opts = ["1080×1920 (Full HD)", "720×1280 (HD)", "540×960 (SD)"]
        _res_map   = {
            "1080×1920 (Full HD)": (1080, 1920),
            "720×1280 (HD)":        (720,  1280),
            "540×960 (SD)":         (540,   960),
        }
        _res_default = next(
            (k for k, (w, h) in _res_map.items()
             if w == _RC.get("width", 1080) and h == _RC.get("height", 1920)),
            "1080×1920 (Full HD)"
        )
        self._export_res_var = tk.StringVar(value=_res_default)
        r = _row(exp_cfg_frame, "Resolution")
        ttk.Combobox(r, textvariable=self._export_res_var,
                     values=_res_opts, state="readonly", width=18,
                     font=("Segoe UI", 8)).pack(side=LEFT)

        # Video encoder — only show encoders available on this machine
        _all_encs = [
            ("libx264",   "H.264 (CPU)"),
            ("libx265",   "H.265/HEVC (CPU)"),
            ("h264_nvenc", "H.264 NVENC (NVIDIA)"),
            ("hevc_nvenc", "HEVC NVENC (NVIDIA)"),
            ("h264_qsv",  "H.264 QSV (Intel)"),
            ("hevc_qsv",  "HEVC QSV (Intel)"),
        ]
        _enc_labels = [lbl for enc, lbl in _all_encs if enc in AVAILABLE_ENCODERS]
        _enc_to_id  = {lbl: enc for enc, lbl in _all_encs}
        _id_to_lbl  = {enc: lbl for enc, lbl in _all_encs}
        _enc_default_lbl = _id_to_lbl.get(_RC.get("vcodec", "libx264"), "H.264 (CPU)")
        self._export_enc_var = tk.StringVar(value=_enc_default_lbl)
        r = _row(exp_cfg_frame, "Encoder")
        self._enc_combo = ttk.Combobox(r, textvariable=self._export_enc_var,
                                        values=_enc_labels, state="readonly", width=18,
                                        font=("Segoe UI", 8))
        self._enc_combo.pack(side=LEFT)
        self._enc_to_id = _enc_to_id   # save for _get_render_cfg

        # FPS
        _fps_opts = ["Original", "24", "30", "60"]
        _fps_default = str(_RC.get("fps", "")) or "Original"
        if _fps_default not in _fps_opts:
            _fps_default = "Original"
        self._export_fps_var = tk.StringVar(value=_fps_default)
        r = _row(exp_cfg_frame, "Frame Rate")
        ttk.Combobox(r, textvariable=self._export_fps_var,
                     values=_fps_opts, state="readonly", width=18,
                     font=("Segoe UI", 8)).pack(side=LEFT)

        # Quality (CRF)
        self._export_crf_var = tk.IntVar(value=int(_RC.get("crf", 20)))
        r = _row(exp_cfg_frame, "Quality (CRF)")
        tk.Scale(
            r, variable=self._export_crf_var,
            from_=15, to=35, orient="horizontal",
            bg=CLR_SURFACE, fg=CLR_FG, troughcolor=CLR_BG,
            highlightthickness=0, length=100, showvalue=True,
            font=("Segoe UI", 7),
        ).pack(side=LEFT)
        tk.Label(r, text="← better", bg=CLR_SURFACE, fg=CLR_DIM,
                 font=("Segoe UI", 7)).pack(side=LEFT, padx=(4, 0))

        # Preset
        _preset_opts = ["ultrafast", "fast", "medium", "slow"]
        self._export_preset_var = tk.StringVar(value=_RC.get("preset", "fast"))
        r = _row(exp_cfg_frame, "Preset")
        ttk.Combobox(r, textvariable=self._export_preset_var,
                     values=_preset_opts, state="readonly", width=18,
                     font=("Segoe UI", 8)).pack(side=LEFT)
        ToolTip(r, "ultrafast = fastest encode / largest file;  slow = best compression")

        # Concurrent export threads (GPU users can run 2–4 in parallel)
        self._export_threads_var = tk.IntVar(value=int(_RC.get("export_threads", 1)))
        r = _row(exp_cfg_frame, "Threads")
        tk.Scale(
            r, variable=self._export_threads_var,
            from_=1, to=4, orient="horizontal", resolution=1,
            bg=CLR_SURFACE, fg=CLR_FG, troughcolor=CLR_BG,
            highlightthickness=0, length=100, showvalue=True,
            font=("Segoe UI", 7),
        ).pack(side=LEFT)
        tk.Label(r, text="parallel exports (GPU: 2–4 recommended)",
                 bg=CLR_SURFACE, fg=CLR_DIM, font=("Segoe UI", 7)
                 ).pack(side=LEFT, padx=(6, 0))
        ToolTip(r, "Number of clips to encode simultaneously.\n"
                   "CPU encoders: keep at 1. NVENC/QSV: 2–4 is safe.")

        self._btn_export_one = AccentButton(
            footer, text="Export Current", icon="📱",
            command=self._start_reup, state=DISABLED,
            font=("Segoe UI", 10, "bold"), pady=8,
        )
        self._btn_export_one.pack(fill=X, pady=(0, 4))
        ToolTip(self._btn_export_one, "Render the currently selected clip as a 9:16 portrait video")

        self._btn_export_all = tk.Button(
            footer, text="📦  Export All",
            bg="#0f766e", fg="white",
            activebackground="#0d6b63", activeforeground="#99f6e4",
            font=("Segoe UI", 10, "bold"), relief=FLAT,
            cursor="hand2", pady=8, state=DISABLED,
            command=self._start_export_all,
        )
        self._btn_export_all.pack(fill=X, pady=(0, 4))
        ToolTip(self._btn_export_all, "Render ALL clips in the queue as 9:16 portrait videos")

        # ── Render progress bar (hidden until export starts) ──────────────────
        self._render_progress_frame = tk.Frame(footer, bg=CLR_BG)
        self._render_progress_frame.pack(fill=X, pady=(0, 4))
        self._render_progress_var  = tk.DoubleVar(value=0.0)
        self._render_progress_lbl  = tk.Label(
            self._render_progress_frame,
            text="", bg=CLR_BG, fg=CLR_FG2, font=("Segoe UI", 8)
        )
        self._render_progress_lbl.pack(anchor=E)
        self._render_progress_bar = ttk.Progressbar(
            self._render_progress_frame,
            variable=self._render_progress_var,
            maximum=100, mode="determinate", length=200,
        )
        self._render_progress_bar.pack(fill=X)
        self._render_progress_frame.pack_forget()  # hidden by default

        def _open_output():
            folder = self._output_var.get().strip()
            if folder and Path(folder).exists():
                os.startfile(folder)
            else:
                self._toast("No output folder configured", kind="warning")

        SecondaryButton(footer, text="Open Output Folder", icon="📂",
                        command=_open_output,
                        font=("Segoe UI", 8, "bold"), pady=4).pack(
            fill=X, pady=(0, 2))

        self._btn_reup = self._btn_export_one   # alias for worker callbacks


        # Scrollable controls area (fills remaining space above footer)
        scroll_canvas = tk.Canvas(right_outer, bg=CLR_BG, highlightthickness=0)
        sb = ttk.Scrollbar(right_outer, orient=VERTICAL, command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=RIGHT, fill=Y)
        scroll_canvas.pack(side=LEFT, fill=BOTH, expand=True)

        ctrl_frame = ttk.Frame(scroll_canvas)
        ctrl_win = scroll_canvas.create_window((0, 0), window=ctrl_frame, anchor="nw")

        def _on_ctrl_resize(event):
            scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))
        ctrl_frame.bind("<Configure>", _on_ctrl_resize)

        def _on_scroll_resize(event):
            scroll_canvas.itemconfig(ctrl_win, width=event.width)
        scroll_canvas.bind("<Configure>", _on_scroll_resize)

        def _on_mouse_wheel(event):
            scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_mw(event):
            scroll_canvas.bind_all("<MouseWheel>", _on_mouse_wheel)
        def _unbind_mw(event):
            scroll_canvas.unbind_all("<MouseWheel>")
        scroll_canvas.bind("<Enter>", _bind_mw)
        scroll_canvas.bind("<Leave>", _unbind_mw)

        # ── Right column: controls (scrollable) ───────────────────────────────
        ctrl_col = ttk.Frame(ctrl_frame)
        ctrl_col.pack(fill=BOTH, expand=True, padx=10, pady=8)
        self._build_tab2_controls(ctrl_col)

    def _build_tab2_controls(self, p):
        """Right-side controls panel for Tab 2."""

        # ── Per-instance settings-mode state ─────────────────────────────────
        _excl = {"blur_boxes", "text_x", "text_y"}
        self._global_edit_state = {k: v for k, v in _default_edit_state().items()
                                   if k not in _excl}
        self._edit_sync_all = tk.BooleanVar(value=False)

        # ── Settings Mode Toggle ─────────────────────────────────────────────
        mode_card = SectionCard(p, "Settings Mode", collapsible=False)
        mode_card.pack(fill=X, pady=(0, 6))
        mc = mode_card.content

        for _lbl, _val in [("🔓  Per Video", False), ("🔗  Sync All", True)]:
            tk.Radiobutton(
                mc, text=_lbl, variable=self._edit_sync_all, value=_val,
                command=self._on_sync_mode_toggle,
                bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
                activebackground=CLR_SURFACE, activeforeground=CLR_ACCENT_H,
                font=("Segoe UI", 9), indicatoron=True,
            ).pack(side=LEFT, padx=(0, 12))

        self._sync_status_lbl = tk.Label(
            mc, text="", font=("Segoe UI", 7, "italic"),
            fg=CLR_DIM, bg=CLR_SURFACE)
        self._sync_status_lbl.pack(side=RIGHT, padx=4)
        ToolTip(mode_card, "Per Video: each clip has independent settings.\n"
                "Sync All: changing any control updates all clips at once.")

        # ── Title Text Content ────────────────────────────────────────────────
        title_card = SectionCard(p, "Title Text", collapsible=False)
        title_card.pack(fill=X, pady=(0, 6))
        tc = title_card.content

        self._edit_title_text_var = tk.StringVar()
        self._edit_title_entry = tk.Entry(
            tc, textvariable=self._edit_title_text_var,
            bg=CLR_INPUT_BG, fg=CLR_FG, insertbackground=CLR_FG,
            font=("Segoe UI", 9), relief=FLAT, bd=0,
            highlightbackground=CLR_BORDER, highlightthickness=1,
        )
        self._edit_title_entry.pack(fill=X, pady=(0, 4), ipady=4)
        self._edit_title_text_var.trace_add("write", self._on_title_text_modified)
        ToolTip(self._edit_title_entry, "Edit the title text that will appear on the video")

        # Suggestions frame
        self._edit_suggestions_frame = tk.Frame(tc, bg=CLR_SURFACE)
        self._edit_suggestions_frame.pack(fill=X, pady=(4, 0))

        # ── Source Mask ───────────────────────────────────────────────────────
        mask_card = SectionCard(p, "Source Mask")
        mask_card.pack(fill=X, pady=(0, 6))
        mc2 = mask_card.content

        tk.Label(mc2, text="Crop edges of the source video to hide banners/watermarks.",
                 bg=CLR_SURFACE, fg=CLR_DIM, font=("Segoe UI", 8),
                 wraplength=300, justify=LEFT).pack(anchor=W, pady=(0, 4))

        # Mask position selector
        _mpos_row = tk.Frame(mc2, bg=CLR_SURFACE)
        _mpos_row.pack(anchor=W, pady=(0, 6))
        self._edit_mask_position = tk.StringVar(value="top")
        for _ml, _mv in [("Top", "top"), ("Bottom", "bottom"), ("Both", "both")]:
            tk.Radiobutton(
                _mpos_row, text=_ml,
                variable=self._edit_mask_position, value=_mv,
                bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
                activebackground=CLR_SURFACE, font=("Segoe UI", 9),
                cursor="hand2", command=self._regen_edit_preview,
            ).pack(side=LEFT, padx=(0, 12))

        tk.Label(mc2, text="Top Crop", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W)
        self._edit_source_mask = tk.DoubleVar(value=0.0)
        PremiumScale(
            mc2, variable=self._edit_source_mask,
            from_=0.0, to=0.30, resolution=0.01,
            value_format="{:.0%}",
            command=lambda v: self._regen_edit_preview(),
        ).pack(fill=X)

        tk.Label(mc2, text="Bottom Crop", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(6, 0))
        self._edit_source_mask_bottom = tk.DoubleVar(value=0.0)
        PremiumScale(
            mc2, variable=self._edit_source_mask_bottom,
            from_=0.0, to=0.30, resolution=0.01,
            value_format="{:.0%}",
            command=lambda v: self._regen_edit_preview(),
        ).pack(fill=X)
        ToolTip(mask_card, "Crop top/bottom edges of source video to remove banners or watermarks")

        # ── Blur Regions ─────────────────────────────────────────────────────
        blur_card = SectionCard(p, "Blur Regions")
        blur_card.pack(fill=X, pady=(0, 6))
        bc = blur_card.content

        tk.Label(bc, text="Enable Draw Mode → click-drag on preview to add blur boxes.",
                 bg=CLR_SURFACE, fg=CLR_DIM, font=("Segoe UI", 8),
                 wraplength=300, justify=LEFT).pack(anchor=W, pady=(0, 6))

        draw_row = tk.Frame(bc, bg=CLR_SURFACE)
        draw_row.pack(fill=X, pady=(0, 4))
        self._btn_draw_mode = tk.Button(
            draw_row, text="✏  Draw Mode: OFF",
            bg="#0f1e3d", fg="#60a5fa",
            activebackground="#172d5c", activeforeground="#93c5fd",
            font=("Segoe UI", 9, "bold"), relief=FLAT,
            cursor="hand2", padx=8, pady=5,
            command=self._toggle_draw_mode,
        )
        self._btn_draw_mode.pack(side=LEFT, fill=X, expand=True)
        ToolTip(self._btn_draw_mode, "Toggle blur-box draw mode — shortcut: D")
        DangerButton(draw_row, text="Clear All", icon="🗑",
                     command=self._clear_blur_boxes,
                     font=("Segoe UI", 8, "bold"), pady=4).pack(
            side=RIGHT, padx=(4, 0))

        # ── Mode selector: Blur vs Delogo ──────────────────────────────────
        mode_row = tk.Frame(bc, bg=CLR_SURFACE)
        mode_row.pack(fill=X, pady=(0, 4))
        tk.Label(mode_row, text="Next box mode:", bg=CLR_SURFACE,
                 fg=CLR_FG2, font=("Segoe UI", 8)).pack(side=LEFT, padx=(0, 6))
        self._blur_box_mode = tk.StringVar(value="blur")
        for _m_val, _m_lbl in [("blur", "🫧 Blur"), ("delogo", "🔍 Delogo (inpaint)")]:
            tk.Radiobutton(
                mode_row, text=_m_lbl, variable=self._blur_box_mode, value=_m_val,
                bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_SURFACE,
                activebackground=CLR_SURFACE, font=("Segoe UI", 8),
                relief=FLAT, cursor="hand2",
            ).pack(side=LEFT, padx=(0, 8))

        # ── Auto-detect buttons ─────────────────────────────────────────────
        _auto_row = tk.Frame(bc, bg=CLR_SURFACE)
        _auto_row.pack(fill=X, pady=(0, 4))

        def _autodetect_logo():
            if self._edit_sel_idx < 0:
                messagebox.showwarning("No clip", "Select a clip first.", parent=self)
                return
            clip = self._edit_queue[self._edit_sel_idx].get("clip_path", "")
            if not clip:
                return
            self._blur_btn_logo.config(state=DISABLED, text="🔍 Detecting…")
            def _run():
                bbox = detect_logo_bbox(clip)
                self.after(0, _on_logo_result, bbox)
            def _on_logo_result(bbox):
                self._blur_btn_logo.config(state=NORMAL, text="🔍 Auto-detect Logo")
                if bbox is None:
                    messagebox.showinfo("Not found",
                        "No static logo/watermark detected in this clip.", parent=self)
                    return
                x, y, w, h = bbox
                box = {"x": x, "y": y, "w": w, "h": h,
                       "mode": self._blur_box_mode.get()}
                self._edit_queue[self._edit_sel_idx]["state"].setdefault("blur_boxes", []).append(box)
                self._refresh_blur_listbox()
                self._regen_edit_preview()
            threading.Thread(target=_run, daemon=True).start()

        def _autodetect_subtitle():
            if self._edit_sel_idx < 0:
                messagebox.showwarning("No clip", "Select a clip first.", parent=self)
                return
            clip = self._edit_queue[self._edit_sel_idx].get("clip_path", "")
            if not clip:
                return
            self._blur_btn_sub.config(state=DISABLED, text="📝 Detecting…")
            def _run():
                result = detect_subtitle_region(clip)
                self.after(0, _on_sub_result, result)
            def _on_sub_result(result):
                self._blur_btn_sub.config(state=NORMAL, text="📝 Auto-detect Subtitle")
                if result is None:
                    messagebox.showinfo("Not found",
                        "No subtitle band detected in this clip.", parent=self)
                    return
                x, y, w, h, start_time = result
                box = {"x": x, "y": y, "w": w, "h": h,
                       "mode": "delogo",  # delogo is better for subtitle removal
                       "start_time": round(start_time, 3)}
                self._edit_queue[self._edit_sel_idx]["state"].setdefault("blur_boxes", []).append(box)
                self._refresh_blur_listbox()
                self._regen_edit_preview()
                messagebox.showinfo("Detected",
                    f"Subtitle band detected at y={y} (starts at {start_time:.1f}s).\n"
                    "Added as Delogo box — you can adjust in the list.", parent=self)
            threading.Thread(target=_run, daemon=True).start()

        self._blur_btn_logo = tk.Button(
            _auto_row, text="🔍 Auto-detect Logo",
            bg="#0f1e3d", fg="#60a5fa",
            activebackground="#172d5c", activeforeground="#93c5fd",
            font=("Segoe UI", 8, "bold"), relief=FLAT,
            cursor="hand2", padx=8, pady=3,
            command=_autodetect_logo,
        )
        self._blur_btn_logo.pack(side=LEFT, fill=X, expand=True, padx=(0, 3))

        self._blur_btn_sub = tk.Button(
            _auto_row, text="📝 Auto-detect Subtitle",
            bg="#1a2a1a", fg="#86efac",
            activebackground="#223322", activeforeground="#a7f3d0",
            font=("Segoe UI", 8, "bold"), relief=FLAT,
            cursor="hand2", padx=8, pady=3,
            command=_autodetect_subtitle,
        )
        self._blur_btn_sub.pack(side=LEFT, fill=X, expand=True)

        self._blur_listbox = tk.Listbox(
            bc, bg=CLR_INPUT_BG, fg=CLR_FG,
            font=("Consolas", 8), height=3,
            selectbackground=CLR_ACCENT_D,
            activestyle="none", borderwidth=0, highlightthickness=0,
        )
        self._blur_listbox.pack(fill=X, pady=(4, 2))

        # Action row: remove + track
        _blur_action_row = tk.Frame(bc, bg=CLR_SURFACE)
        _blur_action_row.pack(fill=X, pady=(0, 4))
        SecondaryButton(_blur_action_row, text="Remove Selected",
                        command=self._remove_selected_blur_box,
                        font=("Segoe UI", 8), pady=3).pack(side=LEFT)

        # Track Object button — launches OpenCV CSRT tracking popup
        tk.Button(
            _blur_action_row, text="🎯 Track Object",
            bg="#1a2e1a", fg="#4ade80",
            activebackground="#223322", activeforeground="#86efac",
            font=("Segoe UI", 8, "bold"), relief=FLAT,
            cursor="hand2", padx=8, pady=3,
            command=self._open_track_popup,
        ).pack(side=RIGHT)

        ToolTip(blur_card, "Draw blur boxes over sensitive regions (faces, plates, badges)\n"
                "🔍 Auto-detect Logo: finds static watermark via temporal variance\n"
                "📝 Auto-detect Subtitle: finds burned-in subtitle band + start time\n"
                "🎯 Track Object: select a region on frame 1 → blur follows it automatically")

        # ── Font ─────────────────────────────────────────────────────────────
        font_card = SectionCard(p, "Font")
        font_card.pack(fill=X, pady=(0, 6))
        fc = font_card.content

        self._edit_font_var = tk.StringVar(value="Impact")
        font_combo = ttk.Combobox(
            fc, textvariable=self._edit_font_var,
            values=["Impact", "Arial Bold", "Arial",
                    "Segoe UI Bold", "Calibri Bold", "Verdana Bold",
                    "Comic Sans", "Trebuchet Bold"],
            state="readonly", width=18,
        )
        font_combo.pack(anchor=W, pady=(0, 6))
        self._edit_font_var.trace_add("write", lambda *_: self._regen_edit_preview())
        ToolTip(font_combo, "Choose the title font family")

        tk.Label(fc, text="Font Size", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W)
        self._edit_font_size = tk.IntVar(value=52)
        PremiumScale(fc, variable=self._edit_font_size,
                     from_=24, to=80, resolution=1,
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X, pady=(0, 4))

        # Bold / Italic / Decorations row
        style_row = tk.Frame(fc, bg=CLR_SURFACE)
        style_row.pack(anchor=W, pady=(2, 0))
        self._edit_font_bold = tk.BooleanVar(value=False)
        tk.Checkbutton(
            style_row, text="B",
            variable=self._edit_font_bold,
            bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
            activebackground=CLR_SURFACE, font=("Segoe UI", 10, "bold"),
            command=self._regen_edit_preview,
        ).pack(side=LEFT, padx=(0, 4))

        self._edit_font_italic = tk.BooleanVar(value=False)
        self._edit_text_decoration = tk.StringVar(value="none")

        tk.Checkbutton(
            style_row, text="I",
            variable=self._edit_font_italic,
            font=("Segoe UI", 10, "italic"),
            bg=CLR_SURFACE, fg=CLR_FG2, selectcolor=CLR_ACCENT_D,
            activebackground=CLR_SURFACE,
            command=self._regen_edit_preview,
        ).pack(side=LEFT, padx=(0, 4))

        def _set_decoration(val):
            cur = self._edit_text_decoration.get()
            self._edit_text_decoration.set("none" if cur == val else val)
            _u_btn.config(relief=SUNKEN if self._edit_text_decoration.get() == "underline"    else FLAT)
            _s_btn.config(relief=SUNKEN if self._edit_text_decoration.get() == "strikethrough" else FLAT)
            self._regen_edit_preview()

        _u_btn = tk.Button(
            style_row, text="U",
            font=("Segoe UI", 10, "underline"),
            bg=CLR_SURFACE, fg=CLR_FG2, relief=FLAT, padx=4, pady=1,
            cursor="hand2", activebackground=CLR_ACCENT_D,
            command=lambda: _set_decoration("underline"),
        )
        _u_btn.pack(side=LEFT, padx=(0, 4))
        _s_btn = tk.Button(
            style_row, text="S",
            font=("Segoe UI", 10, "overstrike"),
            bg=CLR_SURFACE, fg=CLR_FG2, relief=FLAT, padx=4, pady=1,
            cursor="hand2", activebackground=CLR_ACCENT_D,
            command=lambda: _set_decoration("strikethrough"),
        )
        _s_btn.pack(side=LEFT)

        # Alignment
        tk.Label(fc, text="Alignment", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(8, 2))
        self._edit_align_var = tk.StringVar(value="left")
        align_row = tk.Frame(fc, bg=CLR_SURFACE)
        align_row.pack(anchor=W)
        for label, val in [("◀ Left", "left"), ("≡ Center", "center"), ("Right ▶", "right")]:
            tk.Radiobutton(
                align_row, text=label,
                variable=self._edit_align_var, value=val,
                bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
                activebackground=CLR_SURFACE, font=("Segoe UI", 8),
                cursor="hand2",
                command=self._regen_edit_preview,
            ).pack(side=LEFT, padx=(0, 8))

        # Title box width
        tk.Label(fc, text="Title Box Width", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(8, 0))
        self._edit_title_wrap_pct = tk.DoubleVar(value=1.0)
        PremiumScale(fc, variable=self._edit_title_wrap_pct,
                     from_=0.3, to=1.0, resolution=0.05,
                     value_format="{:.0%}",
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)
        ToolTip(font_card, "Font, size, style and alignment for the title overlay")

        # ── Text Color ────────────────────────────────────────────────────────
        color_card = SectionCard(p, "Text Color")
        color_card.pack(fill=X, pady=(0, 6))
        cc = color_card.content

        self._edit_color_var     = tk.StringVar(value="white")
        self._edit_color_hex_var = tk.StringVar(value="#FFFFFF")

        def _pick_color():
            from tkinter import colorchooser
            initial = self._edit_color_hex_var.get()
            result  = colorchooser.askcolor(color=initial, title="Text colour")
            if result and result[1]:
                self._edit_color_hex_var.set(result[1].upper())
                self._edit_color_swatch.config(bg=result[1])
                _hex_entry.delete(0, END)
                _hex_entry.insert(0, result[1].upper())
                self._regen_edit_preview()

        def _hex_changed(*_):
            v = _hex_entry.get().strip()
            if len(v) == 7 and v.startswith("#"):
                try:
                    self._edit_color_swatch.config(bg=v)
                    self._edit_color_hex_var.set(v.upper())
                    self._regen_edit_preview()
                except Exception:
                    pass

        clr_row = tk.Frame(cc, bg=CLR_SURFACE)
        clr_row.pack(fill=X, pady=(0, 6))
        self._edit_color_swatch = tk.Label(
            clr_row, bg="#FFFFFF", width=3,
            relief="solid", cursor="hand2",
        )
        self._edit_color_swatch.pack(side=LEFT, padx=(0, 8))
        self._edit_color_swatch.bind("<Button-1>", lambda e: _pick_color())
        _hex_entry = tk.Entry(
            clr_row, textvariable=self._edit_color_hex_var,
            bg=CLR_INPUT_BG, fg=CLR_FG, insertbackground=CLR_FG,
            font=("Segoe UI", 9), relief=FLAT, width=9,
            highlightbackground=CLR_BORDER, highlightthickness=1,
        )
        _hex_entry.pack(side=LEFT)
        _hex_entry.bind("<FocusOut>", _hex_changed)
        _hex_entry.bind("<Return>",   _hex_changed)
        SecondaryButton(clr_row, text="Pick…", command=_pick_color,
                        font=("Segoe UI", 8), pady=2, padx=6).pack(
            side=LEFT, padx=(6, 0))

        # Color presets
        preset_row = tk.Frame(cc, bg=CLR_SURFACE)
        preset_row.pack(anchor=W)
        for _label, _hex_val, _fg in [
            ("White",  "#FFFFFF", "#111"),
            ("Yellow", "#FFF000", "#333"),
            ("Black",  "#000000", "#ccc"),
            ("Red",    "#FF3333", "#fff"),
            ("Cyan",   "#00FFFF", "#111"),
        ]:
            def _set_preset(h=_hex_val):
                self._edit_color_hex_var.set(h)
                self._edit_color_swatch.config(bg=h)
                _hex_entry.delete(0, END)
                _hex_entry.insert(0, h)
                self._regen_edit_preview()
            tk.Button(
                preset_row, text=_label,
                bg=_hex_val, fg=_fg, relief=FLAT,
                font=("Segoe UI", 7, "bold"), padx=5, pady=2,
                cursor="hand2",
                command=_set_preset,
            ).pack(side=LEFT, padx=(0, 3), pady=(4, 0))
        ToolTip(color_card, "Text fill color — use the hex field for exact values")

        # ── Text Stroke (Border) ──────────────────────────────────────────────
        tk.Label(cc, text="Stroke / Border", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8, "bold")).pack(anchor=W, pady=(10, 2))

        self._edit_stroke_width    = tk.IntVar(value=0)
        self._edit_stroke_color_hex = tk.StringVar(value="#000000")

        _stk_w_row = tk.Frame(cc, bg=CLR_SURFACE)
        _stk_w_row.pack(fill=X)
        tk.Label(_stk_w_row, text="Width:", bg=CLR_SURFACE, fg=CLR_DIM,
                 font=("Segoe UI", 8), width=6, anchor=W).pack(side=LEFT)
        PremiumScale(_stk_w_row, variable=self._edit_stroke_width,
                     from_=0, to=8, resolution=1,
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(side=LEFT, fill=X, expand=True)

        _stk_c_row = tk.Frame(cc, bg=CLR_SURFACE)
        _stk_c_row.pack(anchor=W, pady=(4, 0))
        self._edit_stroke_swatch = tk.Label(
            _stk_c_row, bg="#000000", width=3, relief="solid", cursor="hand2",
        )
        self._edit_stroke_swatch.pack(side=LEFT, padx=(0, 6))

        def _pick_stroke_color():
            from tkinter import colorchooser
            r = colorchooser.askcolor(self._edit_stroke_color_hex.get(), title="Stroke / Border color")
            if r and r[1]:
                self._edit_stroke_color_hex.set(r[1].upper())
                self._edit_stroke_swatch.config(bg=r[1])
                self._regen_edit_preview()
        self._edit_stroke_swatch.bind("<Button-1>", lambda e: _pick_stroke_color())

        for _slbl, _shex, _sfg in [
            ("Black",  "#000000", "#ccc"),
            ("White",  "#FFFFFF", "#111"),
            ("Shadow", "#1A1A1A", "#ccc"),
            ("Red",    "#CC0000", "#fff"),
        ]:
            def _set_sc(h=_shex):
                self._edit_stroke_color_hex.set(h)
                self._edit_stroke_swatch.config(bg=h)
                self._regen_edit_preview()
            tk.Button(
                _stk_c_row, text=_slbl, bg=_shex, fg=_sfg, relief=FLAT,
                font=("Segoe UI", 7, "bold"), padx=5, pady=2,
                cursor="hand2", command=_set_sc,
            ).pack(side=LEFT, padx=(0, 3))
        ToolTip(_stk_c_row, "Stroke color — applied around the text outline")

        # ── Spacing ───────────────────────────────────────────────────────────
        spacing_card = SectionCard(p, "Spacing")
        spacing_card.pack(fill=X, pady=(0, 6))
        sc = spacing_card.content

        tk.Label(sc, text="Letter Spacing", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W)
        self._edit_letter_spacing = tk.IntVar(value=0)
        PremiumScale(sc, variable=self._edit_letter_spacing,
                     from_=-10, to=60, resolution=1,
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)

        tk.Label(sc, text="Line Height", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(6, 0))
        self._edit_line_height = tk.DoubleVar(value=1.2)
        PremiumScale(sc, variable=self._edit_line_height,
                     from_=0.8, to=3.0, resolution=0.1,
                     value_format="{:.1f}x",
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)
        ToolTip(spacing_card, "Letter spacing: pixels between characters\nLine height: multiplier for line gap")

        # ── Text Background ───────────────────────────────────────────────────
        textbg_card = SectionCard(p, "Text Background")
        textbg_card.pack(fill=X, pady=(0, 6))
        tbc = textbg_card.content

        self._edit_textbg_var = tk.StringVar(value="none")
        bg_mode_row = tk.Frame(tbc, bg=CLR_SURFACE)
        bg_mode_row.pack(anchor=W, pady=(0, 6))
        for label, val in [("None", "none"), ("Box", "box"), ("Outline", "outline")]:
            tk.Radiobutton(
                bg_mode_row, text=label,
                variable=self._edit_textbg_var, value=val,
                bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
                activebackground=CLR_SURFACE, font=("Segoe UI", 9),
                cursor="hand2",
                command=self._regen_edit_preview,
            ).pack(side=LEFT, padx=(0, 12))

        # Box style
        box_style_row = tk.Frame(tbc, bg=CLR_SURFACE)
        box_style_row.pack(fill=X, pady=(0, 4))
        tk.Label(box_style_row, text="Style:", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(side=LEFT)
        self._edit_box_mode = tk.StringVar(value="frame")
        for _lbl, _val in [("Frame", "frame"), ("Per Line", "per_line")]:
            tk.Radiobutton(
                box_style_row, text=_lbl,
                variable=self._edit_box_mode, value=_val,
                bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
                activebackground=CLR_SURFACE, font=("Segoe UI", 8),
                cursor="hand2",
                command=self._regen_edit_preview,
            ).pack(side=LEFT, padx=(8, 0))

        # Box color presets + custom picker
        boxclr_row = tk.Frame(tbc, bg=CLR_SURFACE)
        boxclr_row.pack(fill=X, pady=(4, 4))
        tk.Label(boxclr_row, text="Color:", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(side=LEFT)
        self._edit_box_bg_color = tk.StringVar(value="black")
        # Restore saved custom color from config
        _saved_box_hex = self._cfg.get("box_bg_custom_hex", "#222222")
        self._edit_box_bg_color_hex = tk.StringVar(value=_saved_box_hex)
        for _lbl, _val, _clr in [
            ("Black", "black",    "#111"),
            ("Dark",  "darkgray", "#333"),
            ("Gray",  "gray",     "#888"),
            ("White", "white",    "#eee"),
        ]:
            tk.Radiobutton(
                boxclr_row, text=_lbl,
                variable=self._edit_box_bg_color, value=_val,
                bg=CLR_SURFACE, fg=_clr, selectcolor=CLR_ACCENT_D,
                activebackground=CLR_SURFACE, font=("Segoe UI", 8, "bold"),
                cursor="hand2",
                command=self._regen_edit_preview,
            ).pack(side=LEFT, padx=(6, 0))

        # Custom color swatch
        self._box_custom_swatch = tk.Button(
            boxclr_row, text="Custom", width=6,
            bg=_saved_box_hex, fg="white" if _saved_box_hex < "#888888" else "black",
            font=("Segoe UI", 7, "bold"), relief=FLAT, cursor="hand2", padx=4, pady=2,
            command=self._pick_box_bg_color,
        )
        self._box_custom_swatch.pack(side=LEFT, padx=(8, 0))
        ToolTip(self._box_custom_swatch, "Pick any custom background color")

        # Box numeric sliders (radius, padding, opacity)
        tk.Label(tbc, text="Corner Radius", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(2, 0))
        self._edit_box_radius = tk.IntVar(value=0)
        PremiumScale(tbc, variable=self._edit_box_radius,
                     from_=0, to=30, resolution=1,
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)

        tk.Label(tbc, text="Padding H", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(4, 0))
        self._edit_box_pad_x = tk.IntVar(value=30)
        PremiumScale(tbc, variable=self._edit_box_pad_x,
                     from_=0, to=60, resolution=1,
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)

        tk.Label(tbc, text="Padding V", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(4, 0))
        self._edit_box_pad_y = tk.IntVar(value=20)
        PremiumScale(tbc, variable=self._edit_box_pad_y,
                     from_=0, to=40, resolution=1,
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)

        tk.Label(tbc, text="Box Opacity", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(4, 0))
        self._edit_box_opacity = tk.IntVar(value=90)
        PremiumScale(tbc, variable=self._edit_box_opacity,
                     from_=20, to=100, resolution=5,
                     value_format="{:.0f}%",
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)

        # Reset box width
        def _reset_box_width():
            if self._edit_sel_idx < 0:
                return
            st = self._edit_queue[self._edit_sel_idx]["state"]
            st["box_x1_pct"] = -1.0
            st["box_x2_pct"] = -1.0
            self._regen_edit_preview()

        SecondaryButton(tbc, text="Reset Box Width", icon="↺",
                        command=_reset_box_width,
                        font=("Segoe UI", 8), pady=3).pack(
            anchor=W, pady=(6, 0))
        ToolTip(textbg_card, "Add a colored box or outline behind the title text")

        # ── Blending ──────────────────────────────────────────────────────────
        blend_card = SectionCard(p, "Blending")
        blend_card.pack(fill=X, pady=(0, 6))
        blc = blend_card.content

        tk.Label(blc, text="Text Opacity", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W)
        self._edit_text_opacity = tk.IntVar(value=100)
        PremiumScale(blc, variable=self._edit_text_opacity,
                     from_=0, to=100, resolution=5,
                     value_format="{:.0f}%",
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)

        tk.Label(blc, text="Rotation", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(6, 0))
        self._edit_text_rotation = tk.DoubleVar(value=0.0)
        PremiumScale(blc, variable=self._edit_text_rotation,
                     from_=-45, to=45, resolution=1,
                     value_format="{:.0f}°",
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)
        ToolTip(blend_card, "Text opacity and rotation angle")

        # ── Video Position & Scale ─────────────────────────────────────────────
        vid_card = SectionCard(p, "Video Position & Scale")
        vid_card.pack(fill=X, pady=(0, 6))
        vc = vid_card.content

        tk.Label(vc, text="Y Offset", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W)
        self._edit_video_y = tk.IntVar(value=0)
        PremiumScale(vc, variable=self._edit_video_y,
                     from_=-400, to=400, resolution=1,
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)

        tk.Label(vc, text="Width Scale", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(6, 0))
        self._edit_video_w_scale = tk.DoubleVar(value=1.0)
        PremiumScale(vc, variable=self._edit_video_w_scale,
                     from_=0.5, to=1.5, resolution=0.05,
                     value_format="{:.2f}x",
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)

        tk.Label(vc, text="Height Scale", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(6, 0))
        self._edit_video_h_scale = tk.DoubleVar(value=1.0)
        PremiumScale(vc, variable=self._edit_video_h_scale,
                     from_=0.5, to=1.5, resolution=0.05,
                     value_format="{:.2f}x",
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)
        ToolTip(vid_card, "Shift and scale the video layer within the portrait frame")

        # ── Options ───────────────────────────────────────────────────────────
        opt_card = SectionCard(p, "Options")
        opt_card.pack(fill=X, pady=(0, 6))
        oc = opt_card.content

        self._opt_color_grade = tk.BooleanVar(value=False)
        self._opt_subtitles   = tk.BooleanVar(value=False)
        self._sub_style       = tk.StringVar(value="Normal")
        self._sub_highlight_color = tk.StringVar(value="#FFD700")  # gold
        self._sub_dim_color       = tk.StringVar(value="#FFFFFF")  # white (unhighlighted)
        self._sub_font_size   = tk.IntVar(value=36)

        tk.Checkbutton(
            oc, text="Cinematic color grade",
            variable=self._opt_color_grade,
            bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
            activebackground=CLR_SURFACE, font=("Segoe UI", 9),
            cursor="hand2",
            command=self._regen_edit_preview,
        ).pack(anchor=W)

        self._sub_margin_v = tk.IntVar(value=200)   # pixels from bottom in full-res (1920)

        def _on_sub_toggle():
            if self._opt_subtitles.get():
                _sub_opts_frame.pack(fill=X, pady=(4, 0))
            else:
                _sub_opts_frame.pack_forget()
            self._regen_edit_preview()

        def _on_style_change(*_):
            if self._sub_style.get() == "Normal":
                _kar_opts_row.pack_forget()
            else:
                _kar_opts_row.pack(fill=X, pady=(4, 0))
            self._regen_edit_preview()

        tk.Checkbutton(
            oc,
            text="Auto-subtitles (Gemini AI)",
            variable=self._opt_subtitles,
            bg=CLR_SURFACE, fg=CLR_FG,
            selectcolor=CLR_ACCENT_D, activebackground=CLR_SURFACE,
            font=("Segoe UI", 9), cursor="hand2",
            command=_on_sub_toggle,
        ).pack(anchor=W)

        # ── Subtitle options (hidden until enabled) ────────────────────────────
        _sub_opts_frame = tk.Frame(oc, bg=CLR_SURFACE)

        # Style row
        _style_row = tk.Frame(_sub_opts_frame, bg=CLR_SURFACE)
        _style_row.pack(fill=X)
        tk.Label(_style_row, text="Style:", bg=CLR_SURFACE,
                 fg=CLR_DIM, font=("Segoe UI", 8), width=8, anchor=W).pack(side=LEFT)
        _style_cb = ttk.Combobox(
            _style_row, textvariable=self._sub_style, state="readonly", width=16,
            values=["Normal", "Word Pop", "Highlight Line"],
        )
        _style_cb.pack(side=LEFT, padx=(2, 0))
        self._sub_style.trace_add("write", _on_style_change)

        # Position slider
        tk.Label(_sub_opts_frame, text="Sub position (from bottom)", bg=CLR_SURFACE,
                 fg=CLR_DIM, font=("Segoe UI", 8)).pack(anchor=W, pady=(4, 0))
        PremiumScale(_sub_opts_frame, variable=self._sub_margin_v,
                     from_=40, to=500, resolution=10,
                     command=lambda v: self._regen_edit_preview()).pack(fill=X)

        # Karaoke-specific options (hidden until Word Pop or Highlight Line selected)
        _kar_opts_row = tk.Frame(_sub_opts_frame, bg=CLR_SURFACE)

        # ── Dim color (non-highlighted words) ────────────────────────────────
        _dim_row = tk.Frame(_kar_opts_row, bg=CLR_SURFACE)
        _dim_row.pack(fill=X, pady=(0, 2))
        tk.Label(_dim_row, text="Đã chạy:", bg=CLR_SURFACE,
                 fg=CLR_DIM, font=("Segoe UI", 8), width=9, anchor=W).pack(side=LEFT)
        self._sub_dim_swatch = tk.Label(
            _dim_row, bg=self._sub_dim_color.get(),
            width=3, relief="solid", cursor="hand2",
        )
        self._sub_dim_swatch.pack(side=LEFT, padx=(4, 0))

        def _pick_dim_color():
            from tkinter import colorchooser as _cc
            color = _cc.askcolor(self._sub_dim_color.get(),
                                 title="Subtitle dim (non-highlighted) colour")
            if color and color[1]:
                self._sub_dim_color.set(color[1])
                self._sub_dim_swatch.config(bg=color[1])
                self._regen_edit_preview()
        self._sub_dim_swatch.bind("<ButtonPress-1>", lambda _: _pick_dim_color())

        # ── Highlight color (spoken word) ─────────────────────────────────────
        _hl_row = tk.Frame(_kar_opts_row, bg=CLR_SURFACE)
        _hl_row.pack(fill=X, pady=(0, 2))
        tk.Label(_hl_row, text="Chưa chạy:", bg=CLR_SURFACE,
                 fg=CLR_DIM, font=("Segoe UI", 8), width=9, anchor=W).pack(side=LEFT)
        self._sub_hl_swatch = tk.Label(
            _hl_row, bg=self._sub_highlight_color.get(),
            width=3, relief="solid", cursor="hand2",
        )
        self._sub_hl_swatch.pack(side=LEFT, padx=(4, 0))

        def _pick_hl_color():
            from tkinter import colorchooser as _cc
            color = _cc.askcolor(self._sub_highlight_color.get(),
                                 title="Màu chữ chưa chạy (upcoming words)")
            if color and color[1]:
                self._sub_highlight_color.set(color[1])
                self._sub_hl_swatch.config(bg=color[1])
                self._regen_edit_preview()
        self._sub_hl_swatch.bind("<ButtonPress-1>", lambda _: _pick_hl_color())

        # ── Size slider ────────────────────────────────────────────────────────
        _sz_row = tk.Frame(_kar_opts_row, bg=CLR_SURFACE)
        _sz_row.pack(fill=X, pady=(4, 0))
        tk.Label(_sz_row, text="Size:", bg=CLR_SURFACE,
                 fg=CLR_DIM, font=("Segoe UI", 8)).pack(side=LEFT)
        PremiumScale(_sz_row, variable=self._sub_font_size,
                     from_=18, to=120, resolution=2,
                     command=lambda v: self._regen_edit_preview()).pack(side=LEFT, fill=X, expand=True)

        # starts hidden; _on_style_change shows it when non-Normal
        ToolTip(opt_card, "Cinematic grade: adds warm film look\n"
                "Auto-subtitles (Gemini): uploads clip to Gemini for accurate transcription\n"
                "Word Pop: each word appears as spoken (CapCut style)\n"
                "Highlight Line: full line visible, spoken word highlighted")

        # ── Copyright Evasion ─────────────────────────────────────────────────
        ev_card = SectionCard(p, "\U0001f6e1  Copyright Evasion")
        ev_card.pack(fill=X, pady=(0, 6))
        ec = ev_card.content

        tk.Label(ec, text="Apply transforms to avoid platform re-upload detection.",
                 bg=CLR_SURFACE, fg=CLR_DIM, font=("Segoe UI", 8),
                 wraplength=300, justify=LEFT).pack(anchor=W, pady=(0, 8))

        # ── 1. Background type ────────────────────────────────────────────────
        tk.Label(ec, text="Background", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 9, "bold")).pack(anchor=W)
        self._ev_bg_type = tk.StringVar(value="blur")
        bg_type_row = tk.Frame(ec, bg=CLR_SURFACE)
        bg_type_row.pack(anchor=W, pady=(2, 6))
        for _lbl, _val in [("Blurred", "blur"), ("Image", "image"), ("Video", "video")]:
            tk.Radiobutton(
                bg_type_row, text=_lbl, variable=self._ev_bg_type, value=_val,
                command=self._on_ev_bg_type_change,
                bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
                activebackground=CLR_SURFACE, font=("Segoe UI", 9),
            ).pack(side=LEFT, padx=(0, 8))
        ToolTip(bg_type_row, "Blurred: default mirror blur\nImage: static photo background\nVideo: looping video background")

        # File pickers (hidden by default, shown when image/video selected)
        self._ev_bg_file_frame = tk.Frame(ec, bg=CLR_SURFACE)
        self._ev_bg_file_frame.pack(fill=X, pady=(0, 4))

        self._ev_bg_image_var = tk.StringVar()
        self._ev_bg_video_var = tk.StringVar()

        def _pick_bg_image():
            p_ = filedialog.askopenfilename(
                title="Select Background Image",
                filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.webp"), ("All", "*.*")])
            if p_:
                if Path(p_).suffix.lower() in {".mp4", ".mov", ".webm", ".mkv", ".avi", ".ts", ".m4v"}:
                    self._ev_bg_video_var.set(p_)
                    self._ev_bg_type.set("video")
                else:
                    self._ev_bg_image_var.set(p_)
                    self._ev_bg_type.set("image")
                self._on_ev_bg_type_change()

        def _pick_bg_video():
            p_ = filedialog.askopenfilename(
                title="Select Background Video",
                filetypes=[("Videos", "*.mp4 *.mov *.avi *.mkv"), ("All", "*.*")])
            if p_:
                if Path(p_).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
                    self._ev_bg_image_var.set(p_)
                    self._ev_bg_type.set("image")
                else:
                    self._ev_bg_video_var.set(p_)
                    self._ev_bg_type.set("video")
                self._on_ev_bg_type_change()

        self._ev_img_row = tk.Frame(self._ev_bg_file_frame, bg=CLR_SURFACE)
        self._ev_img_row.pack(fill=X)
        SecondaryButton(self._ev_img_row, text="Choose Image", icon="\U0001f5bc",
                        command=_pick_bg_image, font=("Segoe UI", 8), pady=3
                        ).pack(side=LEFT, padx=(0, 4))
        tk.Label(self._ev_img_row, textvariable=self._ev_bg_image_var,
                 bg=CLR_SURFACE, fg=CLR_DIM, font=("Segoe UI", 7),
                 width=22, anchor=W).pack(side=LEFT)

        self._ev_vid_row = tk.Frame(self._ev_bg_file_frame, bg=CLR_SURFACE)
        self._ev_vid_row.pack(fill=X, pady=(2, 0))
        SecondaryButton(self._ev_vid_row, text="Choose Video", icon="\U0001f3ac",
                        command=_pick_bg_video, font=("Segoe UI", 8), pady=3
                        ).pack(side=LEFT, padx=(0, 4))
        tk.Label(self._ev_vid_row, textvariable=self._ev_bg_video_var,
                 bg=CLR_SURFACE, fg=CLR_DIM, font=("Segoe UI", 7),
                 width=22, anchor=W).pack(side=LEFT)

        ttk.Separator(ec, orient=HORIZONTAL).pack(fill=X, pady=8)

        # ── 2. Color Transform ────────────────────────────────────────────────
        tk.Label(ec, text="Color Transform", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 9, "bold")).pack(anchor=W)

        tk.Label(ec, text="Hue Shift", bg=CLR_SURFACE, fg=CLR_DIM,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(4, 0))
        self._ev_hue_shift = tk.IntVar(value=0)
        PremiumScale(ec, variable=self._ev_hue_shift,
                     from_=-180, to=180, resolution=1,
                     value_format="{:.0f}\u00b0",
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)
        ToolTip(ec, "Shift all colors by this angle (breaks color hash fingerprinting)")

        tk.Label(ec, text="Saturation", bg=CLR_SURFACE, fg=CLR_DIM,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(4, 0))
        self._ev_saturation = tk.DoubleVar(value=1.0)
        PremiumScale(ec, variable=self._ev_saturation,
                     from_=0.5, to=2.0, resolution=0.05,
                     value_format="{:.2f}x",
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)

        # Color presets row
        _preset_row = tk.Frame(ec, bg=CLR_SURFACE)
        _preset_row.pack(anchor=W, pady=(4, 0))
        tk.Label(_preset_row, text="Preset:", bg=CLR_SURFACE, fg=CLR_DIM,
                 font=("Segoe UI", 8)).pack(side=LEFT, padx=(0, 4))
        for _lbl, _h, _s in [
            ("Normal", 0, 1.0), ("Warm", 15, 1.2), ("Cool", -20, 0.9),
            ("Vivid", 0, 1.6),  ("B&W", 0, 0.0),
        ]:
            def _apply_preset(h=_h, s=_s):
                self._ev_hue_shift.set(h); self._ev_saturation.set(s)
                self._regen_edit_preview()
            tk.Button(
                _preset_row, text=_lbl,
                bg=CLR_PANEL, fg=CLR_FG, activebackground=CLR_ACCENT_D,
                font=("Segoe UI", 7), relief=FLAT, padx=4, pady=2, cursor="hand2",
                command=_apply_preset,
            ).pack(side=LEFT, padx=(0, 2))

        ttk.Separator(ec, orient=HORIZONTAL).pack(fill=X, pady=8)

        # ── 3. Flip ───────────────────────────────────────────────────────────
        tk.Label(ec, text="Flip", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 9, "bold")).pack(anchor=W)
        flip_row = tk.Frame(ec, bg=CLR_SURFACE)
        flip_row.pack(anchor=W, pady=(4, 0))
        self._ev_flip_h = tk.BooleanVar(value=False)
        self._ev_flip_v = tk.BooleanVar(value=False)
        tk.Checkbutton(
            flip_row, text="\u21d4  Horizontal",
            variable=self._ev_flip_h, command=self._regen_edit_preview,
            bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
            activebackground=CLR_SURFACE, font=("Segoe UI", 9),
        ).pack(side=LEFT, padx=(0, 12))
        tk.Checkbutton(
            flip_row, text="\u21d5  Vertical",
            variable=self._ev_flip_v, command=self._regen_edit_preview,
            bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
            activebackground=CLR_SURFACE, font=("Segoe UI", 9),
        ).pack(side=LEFT)
        ToolTip(flip_row, "Horizontal flip is most effective at evading platform detection")

        ttk.Separator(ec, orient=HORIZONTAL).pack(fill=X, pady=8)

        # ── 4. Watermark ──────────────────────────────────────────────────────
        tk.Label(ec, text="Watermark", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 9, "bold")).pack(anchor=W)

        self._ev_wm_text = tk.StringVar()
        self._ev_wm_text.trace_add("write",
            lambda *_: self.after(200, self._regen_edit_preview))  # debounced
        wm_entry = tk.Entry(
            ec, textvariable=self._ev_wm_text,
            bg=CLR_INPUT_BG, fg=CLR_FG, insertbackground=CLR_FG,
            font=("Segoe UI", 9), relief=FLAT, bd=0,
            highlightbackground=CLR_BORDER, highlightthickness=1,
        )
        wm_entry.pack(fill=X, ipady=4, pady=(4, 6))
        ToolTip(wm_entry, "Text to burn as watermark (e.g. '@yourhandle')")

        # 3×3 position grid
        tk.Label(ec, text="Position", bg=CLR_SURFACE, fg=CLR_DIM,
                 font=("Segoe UI", 8)).pack(anchor=W)
        self._ev_wm_pos = tk.StringVar(value="BR")
        _pos_grid = tk.Frame(ec, bg=CLR_SURFACE)
        _pos_grid.pack(anchor=W, pady=(2, 6))
        for _row_i, _row in enumerate([
            [("TL", "\u2196"), ("TC", "\u2191"), ("TR", "\u2197")],
            [("ML", "\u2190"), ("MC", "\u25a0"), ("MR", "\u2192")],
            [("BL", "\u2199"), ("BC", "\u2193"), ("BR", "\u2198")],
        ]):
            _rf = tk.Frame(_pos_grid, bg=CLR_SURFACE)
            _rf.pack()
            for _pos, _sym in _row:
                tk.Radiobutton(
                    _rf, text=_sym, variable=self._ev_wm_pos, value=_pos,
                    command=self._regen_edit_preview,
                    bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
                    activebackground=CLR_SURFACE, font=("Segoe UI", 10),
                    indicatoron=False, width=3, relief=FLAT,
                    cursor="hand2", padx=2, pady=1,
                ).pack(side=LEFT, padx=1, pady=1)

        # Watermark size + opacity
        tk.Label(ec, text="Size", bg=CLR_SURFACE, fg=CLR_DIM,
                 font=("Segoe UI", 8)).pack(anchor=W)
        self._ev_wm_size = tk.IntVar(value=28)
        PremiumScale(ec, variable=self._ev_wm_size,
                     from_=12, to=80, resolution=1,
                     command=lambda v: self._regen_edit_preview()).pack(fill=X)

        tk.Label(ec, text="Opacity", bg=CLR_SURFACE, fg=CLR_DIM,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(4, 0))
        self._ev_wm_opacity = tk.IntVar(value=50)
        PremiumScale(ec, variable=self._ev_wm_opacity,
                     from_=10, to=100, resolution=5,
                     value_format="{:.0f}%",
                     command=lambda v: self._regen_edit_preview()).pack(fill=X)

        # Watermark color picker
        wm_clr_row = tk.Frame(ec, bg=CLR_SURFACE)
        wm_clr_row.pack(anchor=W, pady=(4, 0))
        tk.Label(wm_clr_row, text="Color:", bg=CLR_SURFACE, fg=CLR_DIM,
                 font=("Segoe UI", 8)).pack(side=LEFT, padx=(0, 4))
        self._ev_wm_color = tk.StringVar(value="#FFFFFF")
        self._ev_wm_swatch = tk.Label(
            wm_clr_row, bg="#FFFFFF", width=3, relief="solid",
            cursor="hand2", borderwidth=1)
        self._ev_wm_swatch.pack(side=LEFT)

        def _pick_wm_color():
            from tkinter import colorchooser
            c = colorchooser.askcolor(self._ev_wm_color.get(), title="Watermark Color")
            if c and c[1]:
                self._ev_wm_color.set(c[1])
                self._ev_wm_swatch.config(bg=c[1])
                self._regen_edit_preview()

        self._ev_wm_swatch.bind("<Button-1>", lambda e: _pick_wm_color())

        ttk.Separator(ec, orient=HORIZONTAL).pack(fill=X, pady=8)

        # ── 5. Anti-detect ────────────────────────────────────────────────────
        tk.Label(ec, text="Anti-Detection", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 9, "bold")).pack(anchor=W)

        self._ev_add_grain = tk.BooleanVar(value=False)
        tk.Checkbutton(
            ec, text="\U0001f4f7  Film Grain (breaks hash fingerprint)",
            variable=self._ev_add_grain, command=self._regen_edit_preview,
            bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
            activebackground=CLR_SURFACE, font=("Segoe UI", 9),
        ).pack(anchor=W, pady=(4, 0))
        ToolTip(ec, "Adds random noise to each frame — breaks YouTube/TikTok perceptual hash detection")

        tk.Label(ec, text="Grain Strength", bg=CLR_SURFACE, fg=CLR_DIM,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(4, 0))
        self._ev_grain_strength = tk.IntVar(value=3)
        PremiumScale(ec, variable=self._ev_grain_strength,
                     from_=1, to=10, resolution=1,
                     command=lambda v: self._regen_edit_preview()).pack(fill=X)

        self._ev_speed_tweak = tk.BooleanVar(value=False)
        tk.Checkbutton(
            ec, text="\u23f3  Speed Tweak \u00b12% (breaks temporal fingerprint)",
            variable=self._ev_speed_tweak, command=self._regen_edit_preview,
            bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
            activebackground=CLR_SURFACE, font=("Segoe UI", 9),
        ).pack(anchor=W, pady=(6, 0))
        ToolTip(ec, "Speeds video up by ~2% — inaudible but breaks timestamp-based detection")

        self._on_ev_bg_type_change()   # set initial visibility of file picker rows

    # ── Tab 2 editor helpers ──────────────────────────────────────────────────

    def _on_ev_bg_type_change(self, *_):
        """Show/hide file picker rows based on selected background type."""
        bg = self._ev_bg_type.get()
        for widget, visible in [
            (self._ev_img_row, bg == "image"),
            (self._ev_vid_row, bg == "video"),
        ]:
            if visible:
                widget.pack(fill=X, pady=(0, 2))
            else:
                widget.pack_forget()
        self._regen_edit_preview()

    # ── Edit tab video playback ──────────────────────────────────────────────

    def _start_edit_play(self):
        """Pipe raw RGB24 frames from FFmpeg into the edit canvas at ~12 fps.
        Also launches an ffplay subprocess for audio, mirroring VideoPlayer."""
        if self._edit_sel_idx < 0:
            return
        self._stop_edit_play()   # kill any previous session

        clip = self._edit_queue[self._edit_sel_idx]["clip_path"]
        if not clip.exists():
            return

        pct     = self._scrub_pos.get() / 100.0
        dur     = get_video_duration(clip) or 10.0
        seek_t  = max(0.0, pct * dur)
        remain  = max(1.0, dur - seek_t)    # seconds left from seek point
        FPS     = 12
        W, H    = EDIT_PREV_W, EDIT_PREV_H
        FRAME_B = W * H * 3   # bytes per RGB24 frame

        cmd = [
            FFMPEG, "-loglevel", "quiet",
            "-ss", f"{seek_t:.2f}", "-i", str(clip),
            "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                   f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,fps={FPS}",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
        ]

        self._edit_play_stop_evt = threading.Event()
        stop_evt = self._edit_play_stop_evt
        self._edit_playing = True
        self._btn_edit_play.config(text="⏹  Stop")
        self._edit_audio_proc: Optional[subprocess.Popen] = None

        NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        frame_queue: list = []
        _first_frame_evt = threading.Event()   # signalled when first frame arrives

        def _read_frames():
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    creationflags=NO_WIN,
                )
                self._edit_play_proc = proc
                first = True
                while not stop_evt.is_set():
                    raw = proc.stdout.read(FRAME_B)
                    if len(raw) < FRAME_B:
                        break
                    frame_queue.append(raw)
                    if first:
                        first = False
                        _first_frame_evt.set()  # ← unblock audio thread
                proc.stdout.close()
                proc.wait(timeout=2)
            except Exception:
                pass
            finally:
                stop_evt.set()
                _first_frame_evt.set()  # unblock even on error

        def _start_audio_synced():
            """Wait for first video frame then launch ffplay — eliminates A/V drift."""
            _first_frame_evt.wait(timeout=8.0)
            if stop_evt.is_set():
                return
            try:
                self._edit_audio_proc = subprocess.Popen(
                    [
                        FFPLAY, "-nodisp", "-autoexit",
                        "-loglevel", "quiet",
                        "-ss", f"{seek_t:.2f}",
                        "-t",  f"{remain:.2f}",
                        str(clip),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    creationflags=NO_WIN,
                )
            except Exception:
                self._edit_audio_proc = None

        threading.Thread(target=_read_frames,       daemon=True).start()
        threading.Thread(target=_start_audio_synced, daemon=True).start()

        interval_ms = 1000 // FPS

        def _tick():
            if stop_evt.is_set() and not frame_queue:
                self._stop_edit_play()
                return
            if frame_queue:
                raw = frame_queue.pop(0)
                from PIL import Image, ImageTk
                img = Image.frombytes("RGB", (W, H), raw)
                photo = ImageTk.PhotoImage(img)
                self._edit_canvas.create_image(0, 0, anchor="nw", image=photo)
                self._edit_canvas._play_photo = photo   # prevent GC
            self._edit_play_job = self.after(interval_ms, _tick)

        self._edit_play_job = self.after(80, _tick)

    def _stop_edit_play(self):
        """Stop playback (video frame pipe + audio ffplay) and restore static preview."""
        if self._edit_play_job:
            try: self.after_cancel(self._edit_play_job)
            except Exception: pass
            self._edit_play_job = None

        if hasattr(self, "_edit_play_stop_evt"):
            self._edit_play_stop_evt.set()

        if self._edit_play_proc:
            try:
                self._edit_play_proc.kill()
                self._edit_play_proc.stdout.close()
            except Exception: pass
            self._edit_play_proc = None

        # Kill audio ffplay process
        if getattr(self, "_edit_audio_proc", None):
            try:
                self._edit_audio_proc.terminate()
            except Exception: pass
            self._edit_audio_proc = None

        self._edit_playing = False
        if hasattr(self, "_btn_edit_play"):
            self._btn_edit_play.config(text="▶  Play Preview")

        # Restore the static PIL composite preview
        self._regen_edit_preview()

    def _on_title_text_modified(self, *args):
        if self._edit_sel_idx >= 0:
            new_text = self._edit_title_text_var.get()
            self._edit_queue[self._edit_sel_idx]["title"] = new_text
            self._regen_edit_preview()

    def _send_to_edit_tab(self):
        """Push last cut clip + selected title onto the Tab 2 queue."""
        if not self._last_cut_path or not self._last_cut_path.exists():
            messagebox.showwarning("No Clip", "Cut a clip first.")
            return
        title = self._selected_title_for_reup.strip()
        if not title:
            messagebox.showwarning("No Title",
                "Click one of the title buttons to select a title first.")
            return

        # Fetch suggested titles from currently selected candidate
        suggested = []
        if self._selected_video:
            res = self._video_results.get(str(self._selected_video), {})
            candidates = res.get("candidates", [])
            cand_idx = self._cand_box.current()
            if 0 <= cand_idx < len(candidates):
                suggested = candidates[cand_idx].get("suggested_titles", [])

        item = {
            "clip_path": self._last_cut_path,
            "title":     title,
            "suggested_titles": suggested,
            "state":     _default_edit_state(),
        }
        # In Sync All mode, immediately apply the global template to new items
        if getattr(self, "_edit_sync_all", None) and self._edit_sync_all.get():
            item["state"].update(self._global_edit_state)
        self._edit_queue.append(item)
        self._edit_listbox.insert(END, self._last_cut_path.stem)
        self._update_queue_count_label()

        idx = len(self._edit_queue) - 1
        self._edit_listbox.selection_clear(0, END)
        self._edit_listbox.selection_set(idx)
        self._edit_sel_idx = idx

        self._btn_export_one.config(state=NORMAL)
        self._btn_export_all.config(state=NORMAL)
        self._tab_notebook.select(1)   # switch to Tab 2
        self._on_edit_select()

    def _on_edit_select(self, _event=None):
        """Load queue item state into controls and refresh preview."""
        sel = self._edit_listbox.curselection()
        if not sel:
            return
        self._edit_sel_idx = sel[0]
        item = self._edit_queue[self._edit_sel_idx]

        # In Sync All mode: push global visual settings into item before loading.
        # blur_boxes / text_x / text_y are intentionally absent from _global_edit_state.
        if getattr(self, "_edit_sync_all", None) and self._edit_sync_all.get():
            item["state"].update(self._global_edit_state)

        # Snapshot state BEFORE any .set() calls.
        # tk.Scale.command fires on programmatic .set(), so intermediate _regen_edit_preview
        # calls would read stale widget values and corrupt the new item's state.
        # We suppress those calls with _loading_item and use a frozen snapshot for loading.
        st = dict(item["state"])   # local copy — immune to mid-load mutations
        self._loading_item = True
        try:
            self._edit_title_text_var.set(item["title"])

            _fn = {
                "impact":   "Impact",   "arialbd":  "Arial Bold",  "arial":    "Arial",
                "segoeuib": "Segoe UI Bold", "calibrib": "Calibri Bold",
                "verdanab": "Verdana Bold",  "comicbd":  "Comic Sans",
                "trebucbd": "Trebuchet Bold",
            }
            self._edit_font_var.set(_fn.get(st.get("font_name", "impact"), "Impact"))
            self._edit_font_size.set(st.get("font_size", 52))
            self._edit_color_var.set(st.get("text_color", "white"))
            self._edit_textbg_var.set(st.get("text_bg", "none"))
            self._edit_align_var.set(st.get("text_align", "left"))
            self._edit_video_y.set(st.get("video_y", 0))

            self._edit_video_w_scale.set(st.get("video_w_scale", 1.0))
            self._edit_video_h_scale.set(st.get("video_h_scale", 1.0))

            self._opt_color_grade.set(st.get("color_grade", False))
            self._opt_subtitles.set(st.get("subtitles", False))
            self._sub_style.set(st.get("sub_style", "Normal"))
            _c = st.get("sub_highlight_color", "#FFD700")
            self._sub_highlight_color.set(_c)
            if hasattr(self, "_sub_hl_swatch"):
                self._sub_hl_swatch.config(bg=_c)
            self._sub_font_size.set(int(st.get("sub_font_size", 36)))

            smt = st.get("source_mask_top", 0.0)
            self._edit_source_mask.set(smt)
            smb = st.get("source_mask_bottom", 0.0)
            self._edit_source_mask_bottom.set(smb)
            self._edit_mask_position.set(st.get("mask_position", "top"))
            twp = st.get("title_wrap_pct", 1.0)
            self._edit_title_wrap_pct.set(twp)

            _br = int(st.get("box_radius", 0))
            self._edit_box_radius.set(_br)
            self._edit_box_mode.set(st.get("box_mode", "frame"))

            _bpx = int(st.get("box_pad_x", 30))
            self._edit_box_pad_x.set(_bpx)
            _bpy = int(st.get("box_pad_y", 20))
            self._edit_box_pad_y.set(_bpy)
            self._edit_font_bold.set(bool(st.get("font_bold", False)))
            self._edit_box_bg_color.set(st.get("box_bg_color", "black"))
            _cus_hex = st.get("box_bg_color_hex", self._cfg.get("box_bg_custom_hex", "#222222"))
            self._edit_box_bg_color_hex.set(_cus_hex)
            try:
                self._box_custom_swatch.config(bg=_cus_hex)
            except Exception:
                pass
            _bop = int(st.get("box_opacity", 90))
            self._edit_box_opacity.set(_bop)

            # OpenCut typography state
            self._edit_font_italic.set(bool(st.get("font_italic", False)))
            self._edit_text_decoration.set(st.get("text_decoration", "none"))
            _ls = int(st.get("letter_spacing", 0))
            self._edit_letter_spacing.set(_ls)
            _lh = float(st.get("line_height", 1.2))
            self._edit_line_height.set(_lh)
            _top = int(st.get("text_opacity", 100))
            self._edit_text_opacity.set(_top)
            _rot = float(st.get("text_rotation", 0.0))
            self._edit_text_rotation.set(_rot)
            # Hex color: load from text_color_hex, or map preset → hex
            _PRESET_HEX = {"white": "#FFFFFF", "yellow": "#FFF000", "black": "#000000"}
            _hex = st.get("text_color_hex", "") or _PRESET_HEX.get(st.get("text_color", "white"), "#FFFFFF")
            self._edit_color_hex_var.set(_hex)
            try:
                self._edit_color_swatch.config(bg=_hex)
            except Exception:
                pass

            if "box_x1_pct" not in item["state"]:
                item["state"]["box_x1_pct"] = -1.0
            if "box_x2_pct" not in item["state"]:
                item["state"]["box_x2_pct"] = -1.0

            # Rebuild blur-box listbox from saved state
            self._blur_listbox.delete(0, END)
            for _i, _b in enumerate(st.get("blur_boxes", [])):
                self._blur_listbox.insert(
                    END,
                    f"Box {_i+1}: ({_b['x']},{_b['y']})  {_b['w']}×{_b['h']} px"
                )

            # ── Copyright Evasion widgets ────────────────────────────────────
            self._ev_bg_type.set(st.get("bg_type", "blur"))
            self._ev_bg_image_var.set(st.get("bg_image_path", ""))
            self._ev_bg_video_var.set(st.get("bg_video_path", ""))
            self._on_ev_bg_type_change()

            self._ev_hue_shift.set(int(st.get("hue_shift", 0)))
            self._ev_saturation.set(float(st.get("saturation", 1.0)))
            self._ev_flip_h.set(bool(st.get("flip_h", False)))
            self._ev_flip_v.set(bool(st.get("flip_v", False)))

            self._ev_wm_text.set(st.get("watermark_text", ""))
            self._ev_wm_pos.set(st.get("watermark_pos", "BR"))
            self._ev_wm_size.set(int(st.get("watermark_size", 28)))
            self._ev_wm_opacity.set(int(st.get("watermark_opacity", 50)))
            _wm_clr = st.get("watermark_color", "#FFFFFF")
            self._ev_wm_color.set(_wm_clr)
            try:
                self._ev_wm_swatch.config(bg=_wm_clr)
            except Exception:
                pass

            self._ev_add_grain.set(bool(st.get("add_grain", False)))
            self._ev_grain_strength.set(int(st.get("grain_strength", 3)))
            self._ev_speed_tweak.set(bool(st.get("speed_tweak", False)))
            self._sub_margin_v.set(int(st.get("sub_margin_v", 200)))

        finally:
            self._loading_item = False

        self._regen_edit_preview()  # single authoritative regen after full widget load
        self._refresh_edit_suggestions_ui()

    def _edit_queue_remove(self):
        """Remove all currently selected items from the queue (Shift/Ctrl multi-select)."""
        sel = list(self._edit_listbox.curselection())
        if not sel:
            return
        # Delete in reverse order so indices stay valid as we pop.
        for idx in sorted(sel, reverse=True):
            self._edit_queue.pop(idx)
            self._edit_listbox.delete(idx)
        self._edit_sel_idx = -1
        if not self._edit_queue:
            self._btn_export_one.config(state=DISABLED)
            self._btn_export_all.config(state=DISABLED)
            self._draw_edit_placeholder()
        else:
            # Select the item nearest to the first removed index
            new_idx = min(sel[0], len(self._edit_queue) - 1)
            self._edit_listbox.selection_set(new_idx)
            self._edit_sel_idx = new_idx
            self._on_edit_select()
        self._update_queue_count_label()
        self._refresh_edit_suggestions_ui()

    def _update_queue_count_label(self):
        """Refresh the QUEUE header to show current item count."""
        n = len(self._edit_queue)
        if hasattr(self, "_queue_count_var"):
            self._queue_count_var.set(f"QUEUE  ({n} clip{'s' if n != 1 else ''})")

    def _draw_edit_placeholder(self):
        if not hasattr(self, "_edit_canvas"):
            return
        self._edit_canvas.delete("all")
        self._edit_canvas.create_rectangle(
            0, 0, EDIT_PREV_W, EDIT_PREV_H, fill="#0d0d1a", outline="")
        self._edit_canvas.create_text(
            EDIT_PREV_W // 2, EDIT_PREV_H // 2,
            text="Send a clip from\nTab 1 to start",
            fill=CLR_DIM, font=("Segoe UI", 10), justify="center",
        )

    def _read_edit_controls(self) -> dict:
        """Read control widget values into a state dict (excludes text_x/y and blur_boxes).

        blur_boxes are managed directly in state by the draw-mode interaction,
        so they are intentionally omitted here to prevent accidental overwrites.
        """
        _fn = {
            "Impact": "impact", "Arial Bold": "arialbd", "Arial": "arial",
            "Segoe UI Bold": "segoeuib", "Calibri Bold": "calibrib",
            "Verdana Bold": "verdanab", "Comic Sans": "comicbd",
            "Trebuchet Bold": "trebucbd",
        }
        return {
            "font_name":       _fn.get(self._edit_font_var.get(), "impact"),
            "font_size":       self._edit_font_size.get(),
            "text_color":      self._edit_color_var.get(),
            "text_bg":         self._edit_textbg_var.get(),
            "box_mode":        self._edit_box_mode.get(),
            "box_radius":      self._edit_box_radius.get(),
            "box_pad_x":       self._edit_box_pad_x.get(),
            "box_pad_y":       self._edit_box_pad_y.get(),
            "box_bg_color":     self._edit_box_bg_color.get(),
            "box_bg_color_hex": self._edit_box_bg_color_hex.get(),
            "box_opacity":     self._edit_box_opacity.get(),
            "font_bold":       bool(self._edit_font_bold.get()),
            "text_align":      self._edit_align_var.get(),
            "video_y":         self._edit_video_y.get(),
            "video_w_scale":   self._edit_video_w_scale.get(),
            "video_h_scale":   self._edit_video_h_scale.get(),
            "color_grade":     self._opt_color_grade.get(),
            "subtitles":       self._opt_subtitles.get(),
            "sub_style":       self._sub_style.get(),
            "sub_highlight_color": self._sub_highlight_color.get(),
            "sub_dim_color":    self._sub_dim_color.get(),
            "sub_font_size":   self._sub_font_size.get(),
            "source_mask_top":    self._edit_source_mask.get(),
            "source_mask_bottom": self._edit_source_mask_bottom.get(),
            "mask_position":      self._edit_mask_position.get(),
            "title_wrap_pct":  self._edit_title_wrap_pct.get(),
            # Title position — drag-managed but included so Sync All propagates them
            "text_x": float(self._edit_queue[self._edit_sel_idx]["state"].get("text_x", 0))
                      if self._edit_sel_idx >= 0 else 0,
            "text_y": float(self._edit_queue[self._edit_sel_idx]["state"].get("text_y", 60))
                      if self._edit_sel_idx >= 0 else 60,
            # box_x1_pct / box_x2_pct are drag-managed (no widget); read from live state.
            # We intentionally pass them through so sync-all preserves them.
            "box_x1_pct":      float(self._edit_queue[self._edit_sel_idx]["state"].get("box_x1_pct", -1.0))
                               if self._edit_sel_idx >= 0 else -1.0,
            "box_x2_pct":      float(self._edit_queue[self._edit_sel_idx]["state"].get("box_x2_pct", -1.0))
                               if self._edit_sel_idx >= 0 else -1.0,
            # OpenCut typography
            "letter_spacing":  self._edit_letter_spacing.get(),
            "line_height":     self._edit_line_height.get(),
            "font_italic":     bool(self._edit_font_italic.get()),
            "text_decoration": self._edit_text_decoration.get(),
            "text_opacity":    self._edit_text_opacity.get(),
            "text_rotation":   self._edit_text_rotation.get(),
            "text_color_hex":  self._edit_color_hex_var.get(),
            # Text stroke / border
            "stroke_width":    self._edit_stroke_width.get(),
            "stroke_color_hex": self._edit_stroke_color_hex.get(),
            # Copyright evasion
            "bg_type":          self._ev_bg_type.get(),
            "bg_image_path":    self._ev_bg_image_var.get(),
            "bg_video_path":    self._ev_bg_video_var.get(),
            "hue_shift":        self._ev_hue_shift.get(),
            "saturation":       self._ev_saturation.get(),
            "flip_h":           bool(self._ev_flip_h.get()),
            "flip_v":           bool(self._ev_flip_v.get()),
            "watermark_text":   self._ev_wm_text.get(),
            "watermark_pos":    self._ev_wm_pos.get(),
            "watermark_opacity": self._ev_wm_opacity.get(),
            "watermark_size":   self._ev_wm_size.get(),
            "watermark_color":  self._ev_wm_color.get(),
            "add_grain":        bool(self._ev_add_grain.get()),
            "grain_strength":   self._ev_grain_strength.get(),
            "speed_tweak":      bool(self._ev_speed_tweak.get()),
            "sub_margin_v":     self._sub_margin_v.get(),
        }

    def _regen_edit_preview(self, *_):
        """Sync controls → state dict and rebuild the editor canvas."""
        if self._edit_sel_idx < 0 or not PIL_AVAILABLE:
            return
        # Suppress intermediate calls fired by tk.Scale.command during item load
        if getattr(self, "_loading_item", False):
            return
        ctrl = self._read_edit_controls()

        if getattr(self, "_edit_sync_all", None) and self._edit_sync_all.get():
            # Propagate visual settings to every item in the queue
            self._global_edit_state.update(ctrl)
            for _item in self._edit_queue:
                _item["state"].update(ctrl)   # blur_boxes/text_x/y untouched
            n = len(self._edit_queue)
            self._sync_status_lbl.config(
                text=f"Syncing {n} video{'s' if n != 1 else ''}")
        else:
            self._edit_queue[self._edit_sel_idx]["state"].update(ctrl)

        item = self._edit_queue[self._edit_sel_idx]
        try:
            img  = self._build_edit_image(
                item["clip_path"], item["title"], item["state"])
            if img:
                self._display_edit_preview(img)
        except Exception:
            import traceback
            traceback.print_exc()

    def _on_sync_mode_toggle(self):
        """Handle mode switch between Per Video and Sync All."""
        if self._edit_sync_all.get():
            # Switching TO Sync All — treat current item as the global template
            if self._edit_sel_idx >= 0:
                ctrl = self._read_edit_controls()
                self._global_edit_state.update(ctrl)
                for _item in self._edit_queue:
                    _item["state"].update(ctrl)
            n = len(self._edit_queue)
            self._sync_status_lbl.config(
                text=f"Syncing {n} video{'s' if n != 1 else ''}")
        else:
            # Switching TO Per Video — clear status and reload the item’s own state
            self._sync_status_lbl.config(text="")
            if self._edit_sel_idx >= 0:
                self._on_edit_select()   # reloads item’s independent state
                return
        self._regen_edit_preview()

    def _extract_first_frame_pil(self, clip: Path):
        """Extract first frame at t=0.5 s via FFmpeg → temp JPEG → PIL Image."""
        try:
            tmp = Path(tempfile.mktemp(suffix="_edit_frame.jpg"))
            subprocess.run(
                [FFMPEG, "-loglevel", "quiet",
                 "-ss", "0.5", "-i", str(clip),
                 "-frames:v", "1", "-q:v", "3", str(tmp)],
                capture_output=True, timeout=10,
            )
            if not tmp.exists():
                return None
            from PIL import Image
            img = Image.open(tmp).convert("RGB")
            img.load()
            try:
                tmp.unlink()
            except Exception:
                pass
            return img
        except Exception:
            return None

    def _build_edit_image(self, clip: Path, title: str, state: dict):
        """PIL-only composite at preview scale (378×672). Background and first frame are cached."""
        if not PIL_AVAILABLE:
            return None
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
        import textwrap

        W, H = EDIT_PREV_W, EDIT_PREV_H

        # Get / cache first frame
        src_key = str(clip)
        if src_key not in self._frame_cache:
            src = self._extract_first_frame_pil(clip)
            if src is None:
                return None
            self._frame_cache[src_key] = src
        src = self._frame_cache[src_key]

        # ── Background layer ────────────────────────────────────────────────────
        # Cached per (bg_type, bg_path, clip, source_mask_top).
        bg_type  = state.get("bg_type", "blur")
        bg_img_p = state.get("bg_image_path", "")
        bg_vid_p = state.get("bg_video_path", "")
        cpt = max(0.0, min(0.29, float(state.get("source_mask_top", 0.0))))
        bg_cache_key = (bg_type, bg_img_p, bg_vid_p, src_key, cpt)

        if bg_cache_key not in self._edit_bg_cache:
            bg_src = None

            _v_exts = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".ts", ".m4v"}
            if bg_type == "image" and bg_img_p:
                if Path(bg_img_p).suffix.lower() in _v_exts:
                    bg_key_v = f"__bgvid__{bg_img_p}"
                    if bg_key_v not in self._frame_cache:
                        self._frame_cache[bg_key_v] = self._extract_first_frame_pil(Path(bg_img_p))
                    bg_src = self._frame_cache[bg_key_v]
                else:
                    try:
                        bg_src = Image.open(bg_img_p).convert("RGB")
                    except Exception:
                        bg_src = None

            elif bg_type == "video" and bg_vid_p:
                # Extract first frame from background video for preview
                bg_key_v = f"__bgvid__{bg_vid_p}"
                if bg_key_v not in self._frame_cache:
                    self._frame_cache[bg_key_v] = self._extract_first_frame_pil(
                        Path(bg_vid_p))
                bg_src = self._frame_cache[bg_key_v]

            if bg_src is None:
                # Fallback: blurred clip frame (default "blur" behaviour)
                src_for_bg = src
                if cpt > 0:
                    crop_top_px = int(src.height * cpt)
                    src_for_bg = src.crop((0, crop_top_px, src.width, src.height))
                bg_src = src_for_bg

            # Scale-and-crop bg_src to fill W×H
            r  = bg_src.width / bg_src.height
            tr = W / H
            s  = H / bg_src.height if r > tr else W / bg_src.width
            bw, bh = int(bg_src.width * s), int(bg_src.height * s)
            bg = bg_src.resize((bw, bh), Image.LANCZOS)
            cx, cy = (bw - W) // 2, (bh - H) // 2
            bg = bg.crop((cx, cy, cx + W, cy + H))
            # Only blur when in blur mode
            if bg_type not in ("image", "video"):
                bg = bg.filter(ImageFilter.GaussianBlur(radius=14))
            self._edit_bg_cache[bg_cache_key] = bg

        bg_layer = self._edit_bg_cache[bg_cache_key]

        # Foreground scaling on-the-fly (uses video_w_scale and video_h_scale)
        vw_scale = float(state.get("video_w_scale", 1.0))
        vh_scale = float(state.get("video_h_scale", 1.0))
        fg_w = int(W * vw_scale)
        fg_h = int(W * (src.height / src.width) * vh_scale)
        fg_w = max(10, fg_w)
        fg_h = max(10, fg_h)
        fg   = src.resize((fg_w, fg_h), Image.LANCZOS)
        fg_h_orig = fg_h  # save before crop for vy calculation

        # ── Source mask: crop top and/or bottom of fg ────────────────────────────
        cpb_prev = max(0.0, min(0.29, float(state.get("source_mask_bottom", 0.0))))
        _rem = max(0.01, 1.0 - cpt - cpb_prev)
        if cpt > 0 or cpb_prev > 0:
            crop_top_px = int(fg_h_orig * cpt)
            crop_bot_px = int(fg_h_orig * cpb_prev)
            fg = fg.crop((0, crop_top_px, fg_w, fg_h_orig - crop_bot_px))

        # Composite coordinates — unified formula mirrors FFmpeg overlay expression
        vx    = (W - fg_w) // 2
        vy_px = int(state.get("video_y", 0) * EDIT_PREV_SCALE)
        # overlay_y = (H - h/remain)/2 + cpt*h/remain  (h = cropped fg height)
        _fgh  = fg.height
        vy    = int((H - _fgh / _rem) / 2 + vy_px + cpt * _fgh / _rem)

        # ── Copyright evasion: apply transforms to fg before compositing ────────
        if state.get("flip_h", False):
            fg = fg.transpose(Image.FLIP_LEFT_RIGHT)
        if state.get("flip_v", False):
            fg = fg.transpose(Image.FLIP_TOP_BOTTOM)

        # Hue shift + saturation in PIL — use ImageEnhance for saturation (fast),
        # and a vectorized point-table hue shift (avoids slow per-pixel Python loop).
        hue_shift = int(state.get("hue_shift", 0))
        sat_mult  = float(state.get("saturation", 1.0))
        if hue_shift != 0 or abs(sat_mult - 1.0) > 0.01:
            from PIL import ImageEnhance
            if abs(sat_mult - 1.0) > 0.01:
                fg = ImageEnhance.Color(fg).enhance(sat_mult)
            if hue_shift != 0:
                # Hue shift via HSV: convert to RGB bytes, rotate hue channel
                import colorsys
                fg_rgb = fg.convert("RGB")
                h_shift = hue_shift / 360.0
                # Build lookup table: for each possible (r,g,b) → shifted (r,g,b)
                # Operate per-pixel but only on unique values via putdata is still slow;
                # use numpy if available, else fall back to per-pixel colorsys
                try:
                    import numpy as np
                    arr = np.array(fg_rgb, dtype=np.float32) / 255.0
                    r, g, b = arr[...,0], arr[...,1], arr[...,2]
                    maxc  = np.maximum(np.maximum(r, g), b)
                    minc  = np.minimum(np.minimum(r, g), b)
                    delta = maxc - minc
                    valid = maxc > 1e-7   # mask: skip pure black/grey pixels
                    v = maxc

                    # np.divide with where= avoids evaluating division on invalid pixels,
                    # unlike np.where which always computes both branches first.
                    s = np.divide(delta, maxc,
                                  out=np.zeros_like(maxc), where=valid)
                    safe_d = np.where(delta > 1e-7, delta, 1.0)  # avoid /0 in h calc
                    h = np.where(maxc == r, (g - b) / safe_d % 6,
                        np.where(maxc == g, (b - r) / safe_d + 2,
                                            (r - g) / safe_d + 4)) / 6.0
                    h = (h + h_shift) % 1.0
                    # HSV → RGB vectorized
                    i = (h * 6).astype(np.int32) % 6
                    f = h * 6 - i
                    p = v * (1 - s); q = v * (1 - f*s); t_ = v * (1 - (1-f)*s)
                    idx = i
                    rgb_out = np.stack([
                        np.where(idx==0,v, np.where(idx==1,q, np.where(idx==2,p,
                          np.where(idx==3,p, np.where(idx==4,t_,v))))),
                        np.where(idx==0,t_,np.where(idx==1,v, np.where(idx==2,v,
                          np.where(idx==3,q, np.where(idx==4,p,p))))),
                        np.where(idx==0,p, np.where(idx==1,p, np.where(idx==2,t_,
                          np.where(idx==3,v, np.where(idx==4,v,q))))),
                    ], axis=-1)
                    fg = Image.fromarray((rgb_out * 255).clip(0,255).astype(np.uint8), "RGB")
                except ImportError:
                    # numpy not available — skip hue shift in preview (still applied on export)
                    pass

        canvas_img = bg_layer.copy()
        canvas_img.paste(fg, (vx, vy))

        # ── Apply blur boxes (watermark / logo concealment) ───────────────────────
        # Each box is cropped, heavily blurred, then pasted back into the canvas.
        # This is a visual approximation of the FFmpeg boxblur applied on export.
        for _box in state.get("blur_boxes", []):
            if _box.get("tracked"):
                _bx_c, _by_c, _bw_c, _bh_c = map_tracked_box_to_canvas(_box, src.width, src.height, state)
                _bx = int(_bx_c * EDIT_PREV_SCALE)
                _by = int(_by_c * EDIT_PREV_SCALE)
                _bw = max(4, int(_bw_c * EDIT_PREV_SCALE))
                _bh = max(4, int(_bh_c * EDIT_PREV_SCALE))
            else:
                _bx = int(_box["x"] * EDIT_PREV_SCALE)
                _by = int(_box["y"] * EDIT_PREV_SCALE)
                _bw = max(4, int(_box["w"] * EDIT_PREV_SCALE))
                _bh = max(4, int(_box["h"] * EDIT_PREV_SCALE))
            _bx2, _by2 = min(_bx + _bw, W), min(_by + _bh, H)
            if _bx >= W or _by >= H or _bx2 <= 0 or _by2 <= 0:
                continue
            _region = canvas_img.crop((_bx, _by, _bx2, _by2))
            _region = _region.filter(ImageFilter.GaussianBlur(radius=9))
            canvas_img.paste(_region, (_bx, _by))

        # Draw title text
        draw = ImageDraw.Draw(canvas_img)
        _fp = {
            "impact":    "C:/Windows/Fonts/impact.ttf",
            "arialbd":   "C:/Windows/Fonts/arialbd.ttf",
            "arial":     "C:/Windows/Fonts/arial.ttf",
            "segoeuib":  "C:/Windows/Fonts/segoeuib.ttf",
            "calibrib":  "C:/Windows/Fonts/calibrib.ttf",
            "verdanab":  "C:/Windows/Fonts/verdanab.ttf",
            "comicbd":   "C:/Windows/Fonts/comicbd.ttf",
            "trebucbd":  "C:/Windows/Fonts/trebucbd.ttf",
        }
        fsz = max(8, int(state.get("font_size", 52) * EDIT_PREV_SCALE))
        _fp_italic = {
            "arial":    "C:/Windows/Fonts/ariali.ttf",
            "arialbd":  "C:/Windows/Fonts/arialbi.ttf",
            "calibrib": "C:/Windows/Fonts/calibriz.ttf",
            "verdanab": "C:/Windows/Fonts/verdanai.ttf",
            "trebucbd": "C:/Windows/Fonts/trebucit.ttf",
        }
        _fn   = state.get("font_name", "impact")
        _is_italic = bool(state.get("font_italic", False))
        _font_path = ((_fp_italic if _is_italic else {}).get(_fn)
                      or _fp.get(_fn, _fp["impact"]))
        try:
            font = ImageFont.truetype(_font_path, fsz)
        except Exception:
            font = ImageFont.load_default()

        clean = re.sub(r"[^\x00-\x7F\u00C0-\u024F]", "", title).strip()

        # Compute tx first so we can derive the exact pixel width available for text.
        # wrap_pct drives both the bounding box right edge and text wrapping,
        # so they stay in sync.
        tx = int(state.get("text_x", 40) * EDIT_PREV_SCALE)
        ty = int(state.get("text_y", 60) * EDIT_PREV_SCALE)
        wrap_pct  = max(0.3, min(1.0, float(state.get("title_wrap_pct", 1.0))))

        max_line_w = max(30, int(EDIT_PREV_W * wrap_pct) - tx)
        try:
            sample    = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
            avg_char_w = max(1.0, font.getlength(sample) / len(sample))
            chars     = max(5, int(max_line_w / avg_char_w))
        except Exception:
            chars = max(10, int(30 * 52 / max(state.get("font_size", 52), 1) * wrap_pct))

        lines = textwrap.wrap(clean, width=chars) or [clean[:chars]]
        multiline_str = "\n".join(lines)

        align = state.get("text_align", "left")

        # CapCut-style alignment: anchor text to the appropriate edge of the text box.
        # rx = right edge of text box in preview pixels.
        rx = min(int(EDIT_PREV_W * wrap_pct), EDIT_PREV_W - 1)
        _ANC = {"left": ("la", tx), "center": ("ma", (tx + rx) // 2), "right": ("ra", rx)}
        pil_anchor, anchor_x = _ANC.get(align, ("la", tx))

        _hex = state.get("text_color_hex", "")
        if _hex and len(_hex) == 7 and _hex.startswith("#"):
            try:
                color = (int(_hex[1:3], 16), int(_hex[3:5], 16), int(_hex[5:7], 16))
            except ValueError:
                color = (255, 255, 255)
        else:
            color = {"white": (255,255,255), "yellow": (255,240,0),
                     "black": (0,0,0)}.get(state.get("text_color", "white"), (255,255,255))
        bg_mode = state.get("text_bg", "none")

        try:
            bb = draw.multiline_textbbox(
                (anchor_x, ty), multiline_str, font=font,
                align=align, anchor=pil_anchor)
            # Cache precise bb so _draw_title_handles can draw tight CapCut-style frame.
            self._title_bb_cache = bb
            if bg_mode == "box":
                _brad  = int(state.get("box_radius", 0))
                _bmode = state.get("box_mode", "frame")
                _pad_x = max(1, int(state.get("box_pad_x", 30) * EDIT_PREV_SCALE))
                _pad_y = max(1, int(state.get("box_pad_y", 20) * EDIT_PREV_SCALE))
                # Resolve fill — mirrors export renderer
                _BG_RGB = {"black":(0,0,0), "darkgray":(30,30,30),
                           "gray":(90,90,90), "white":(255,255,255)}
                _box_clr = state.get("box_bg_color", "black")
                if _box_clr == "custom":
                    _ch = state.get("box_bg_color_hex", "#222222").lstrip("#")
                    try:
                        _rgb = (int(_ch[0:2],16), int(_ch[2:4],16), int(_ch[4:6],16))
                    except Exception:
                        _rgb = (0, 0, 0)
                else:
                    _rgb = _BG_RGB.get(_box_clr, (0, 0, 0))
                _alpha = max(0, min(255, int(state.get("box_opacity", 90) * 2.55)))
                _fill  = (*_rgb, _alpha)
                # Resolve x1/x2 overrides (same sentinel logic as export)
                _x1p = float(state.get("box_x1_pct", -1.0))
                _x2p = float(state.get("box_x2_pct", -1.0))
                _bx1 = int(EDIT_PREV_W * _x1p) if _x1p >= 0 else (bb[0] - _pad_x)
                _bx2 = int(EDIT_PREV_W * _x2p) if _x2p >= 0 else (bb[2] + _pad_x)
                if _bmode == "per_line" and len(lines) > 0:
                    try:
                        ascent, descent = font.getmetrics()
                        line_h  = ascent + descent
                        pil_spc = 4
                        curr_y  = ty
                        for single_line in lines:
                            lbb = draw.textbbox(
                                (anchor_x, curr_y), single_line,
                                font=font, anchor=pil_anchor)
                            _lx1 = int(EDIT_PREV_W * _x1p) if _x1p >= 0 else lbb[0] - _pad_x
                            _lx2 = int(EDIT_PREV_W * _x2p) if _x2p >= 0 else lbb[2] + _pad_x
                            _c = [_lx1, lbb[1] - _pad_y, _lx2, lbb[3] + _pad_y]
                            if _brad > 0:
                                draw.rounded_rectangle(_c, radius=min(_brad, _pad_y + line_h // 2), fill=_fill)
                            else:
                                draw.rectangle(_c, fill=_fill)
                            curr_y += line_h + pil_spc
                    except Exception:
                        draw.rectangle([_bx1, bb[1]-_pad_y, _bx2, bb[3]+_pad_y], fill=_fill)
                else:
                    _bcoords = [_bx1, bb[1] - _pad_y, _bx2, bb[3] + _pad_y]
                    if _brad > 0:
                        draw.rounded_rectangle(_bcoords, radius=_brad, fill=_fill)
                    else:
                        draw.rectangle(_bcoords, fill=_fill)
            elif bg_mode == "outline":
                draw.rounded_rectangle(
                    [bb[0] - 8, bb[1] - 6, bb[2] + 8, bb[3] + 6],
                    radius=10,
                    fill=(0, 0, 0, 140),
                    outline=(255, 255, 255, 230),
                    width=2,
                )
        except Exception:
            pass

        # ── Line metrics (shared by box + text draw) ───────────────────────────
        try:
            _asc, _des = font.getmetrics()
        except Exception:
            _asc, _des = int(fsz * 0.8), int(fsz * 0.2)
        _nlh        = _asc + _des
        _pil_spc    = max(0, int(_nlh * (float(state.get("line_height", 1.2)) - 1.0)))
        _total_lh   = _nlh + _pil_spc
        _letter_spc = int(state.get("letter_spacing", 0))
        _dec        = state.get("text_decoration", "none")
        _dec_thick  = max(1, int(fsz * 0.055))
        _t_opacity  = int(state.get("text_opacity", 100))
        _t_rotation = float(state.get("text_rotation", 0.0))

        if bg_mode == "none":
            for ox, oy in [(-1,-1),(1,-1),(-1,1),(1,1),(0,2)]:
                draw.multiline_text(
                    (anchor_x+ox, ty+oy), multiline_str,
                    font=font, fill=(0,0,0,200), align=align,
                    anchor=pil_anchor, spacing=_pil_spc)

        # Text stroke: bold adds 1px synthetic stroke; user stroke_width overrides
        _user_sw   = int(state.get("stroke_width", 0))
        _sc_hex    = state.get("stroke_color_hex", "#000000")
        try:
            _stroke_fill = (int(_sc_hex[1:3],16), int(_sc_hex[3:5],16), int(_sc_hex[5:7],16))
        except Exception:
            _stroke_fill = (0, 0, 0)
        _stroke = max(1 if state.get("font_bold", False) else 0, _user_sw)

        if _letter_spc != 0:
            _curr_y = ty
            for _ln in lines:
                _lw = sum(font.getlength(c) for c in _ln) + _letter_spc * max(0, len(_ln)-1)
                _lx = (int(anchor_x - _lw/2) if align == "center"
                       else int(anchor_x - _lw) if align == "right"
                       else anchor_x)
                _cx = _lx
                for _ch in _ln:
                    draw.text((_cx, _curr_y), _ch, font=font, fill=color,
                              stroke_width=_stroke, stroke_fill=color)
                    _cx += int(font.getlength(_ch)) + _letter_spc
                if _dec != "none":
                    _dy = (_curr_y + _des + 1 if _dec == "underline"
                           else _curr_y - _asc + int(_nlh * 0.35))
                    draw.line([(_lx, _dy), (int(_lx+_lw), _dy)],
                              fill=color, width=_dec_thick)
                _curr_y += _total_lh
        else:
            draw.multiline_text(
                (anchor_x, ty), multiline_str,
                font=font, fill=color, align=align, anchor=pil_anchor,
                stroke_width=_stroke, stroke_fill=_stroke_fill, spacing=_pil_spc)
            if _dec != "none":
                _curr_y = ty
                for _ln in lines:
                    _lbb = draw.textbbox((anchor_x, _curr_y), _ln, font=font, anchor=pil_anchor)
                    _dy  = (_lbb[3]+1 if _dec == "underline"
                            else _lbb[1]+int((_lbb[3]-_lbb[1])*0.35))
                    draw.line([(_lbb[0], _dy), (_lbb[2], _dy)],
                              fill=color, width=_dec_thick)
                    _curr_y += _total_lh

        # Opacity & rotation applied to the entire canvas_img layer
        if _t_opacity < 100:
            _r2, _g2, _b2, _a2 = canvas_img.split()
            _a2 = _a2.point(lambda v: int(v * _t_opacity / 100))
            canvas_img = Image.merge("RGBA", (_r2, _g2, _b2, _a2))
        if abs(_t_rotation) > 0.5:
            _bb = getattr(self, "_title_bb_cache", None)
            if _bb:
                _rcx = (_bb[0] + _bb[2]) / 2
                _rcy = (_bb[1] + _bb[3]) / 2
                canvas_img = canvas_img.rotate(-_t_rotation, center=(_rcx, _rcy), expand=False)

        # ── Watermark preview ─────────────────────────────────────────────────────────
        _wm_txt = state.get("watermark_text", "").strip()
        if _wm_txt:
            # Ensure canvas is RGBA so alpha blending works
            if canvas_img.mode != "RGBA":
                canvas_img = canvas_img.convert("RGBA")
            _wm_draw  = ImageDraw.Draw(canvas_img)
            _wm_sz    = max(8, int(state.get("watermark_size", 28) * EDIT_PREV_SCALE))
            _wm_alpha = max(5, min(100, int(state.get("watermark_opacity", 50))))
            _wm_hex   = state.get("watermark_color", "#FFFFFF").lstrip("#")
            try:
                _wm_r = int(_wm_hex[0:2], 16)
                _wm_g = int(_wm_hex[2:4], 16)
                _wm_b = int(_wm_hex[4:6], 16)
            except Exception:
                _wm_r, _wm_g, _wm_b = 255, 255, 255
            _wm_fill = (_wm_r, _wm_g, _wm_b, int(_wm_alpha * 2.55))
            _WM_PAD   = int(30 * EDIT_PREV_SCALE)
            _wm_pos_map = {
                "TL": (_WM_PAD, _WM_PAD),
                "TC": (W // 2, _WM_PAD),
                "TR": (W - _WM_PAD, _WM_PAD),
                "ML": (_WM_PAD, H // 2),
                "MC": (W // 2, H // 2),
                "MR": (W - _WM_PAD, H // 2),
                "BL": (_WM_PAD, H - _WM_PAD),
                "BC": (W // 2, H - _WM_PAD),
                "BR": (W - _WM_PAD, H - _WM_PAD),
            }
            _wm_anchor_map = {
                "TL": "la", "TC": "ma", "TR": "ra",
                "ML": "lm", "MC": "mm", "MR": "rm",
                "BL": "ld", "BC": "md", "BR": "rd",
            }
            _wm_pos_code = state.get("watermark_pos", "BR")
            _wmx, _wmy   = _wm_pos_map.get(_wm_pos_code, (W - _WM_PAD, H - _WM_PAD))
            _wm_anch     = _wm_anchor_map.get(_wm_pos_code, "rd")
            try:
                _wm_font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", _wm_sz)
            except Exception:
                _wm_font = ImageFont.load_default()
            # Outline for readability
            _wm_shadow = (0, 0, 0, int(_wm_alpha * 2.55 * 0.7))
            for _ox, _oy in [(-1,-1),(1,-1),(-1,1),(1,1)]:
                _wm_draw.text((_wmx+_ox, _wmy+_oy), _wm_txt,
                              font=_wm_font, fill=_wm_shadow, anchor=_wm_anch)
            _wm_draw.text((_wmx, _wmy), _wm_txt,
                          font=_wm_font, fill=_wm_fill, anchor=_wm_anch)

        # ── Subtitle preview (placeholder line at adjustable position) ──────────
        _sub_on = state.get("subtitles", False)
        if _sub_on:
            if canvas_img.mode != "RGBA":
                canvas_img = canvas_img.convert("RGBA")
            _sub_draw  = ImageDraw.Draw(canvas_img)
            _sub_sz    = max(8, int(24 * EDIT_PREV_SCALE))
            _sub_margin_v = int(state.get("sub_margin_v", 200) * EDIT_PREV_SCALE)
            _sub_y     = H - _sub_margin_v
            try:
                _sub_font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", _sub_sz)
            except Exception:
                _sub_font = ImageFont.load_default()
            _sub_txt   = "[subtitle preview]"
            # Semi-transparent pill background
            _sub_bb    = _sub_draw.textbbox((W//2, _sub_y), _sub_txt,
                                            font=_sub_font, anchor="mm")
            _sub_draw.rectangle(
                [_sub_bb[0]-8, _sub_bb[1]-4, _sub_bb[2]+8, _sub_bb[3]+4],
                fill=(0, 0, 0, 140))
            for _ox, _oy in [(-1,0),(1,0),(0,-1),(0,1)]:
                _sub_draw.text((W//2+_ox, _sub_y+_oy), _sub_txt,
                               font=_sub_font, fill=(0,0,0,180), anchor="mm")
            _sub_draw.text((W//2, _sub_y), _sub_txt,
                           font=_sub_font, fill=(255,255,255,230), anchor="mm")

        return canvas_img

    # ── Shared helper: box edge positions in preview px ─────────────────────
    def _compute_box_x_edges(self, st: dict) -> tuple:
        """Return (box_left_px, box_right_px) in preview coordinates.

        Uses box_x1_pct / box_x2_pct overrides when set; falls back to
        text-bounding-box + pad_x (the 'auto' / default behaviour).
        """
        bb = getattr(self, "_title_bb_cache", None)
        _pad_x = max(1, int(st.get("box_pad_x", 30) * EDIT_PREV_SCALE))
        x1p = float(st.get("box_x1_pct", -1.0))
        x2p = float(st.get("box_x2_pct", -1.0))
        bx1 = int(EDIT_PREV_W * x1p) if x1p >= 0 else ((bb[0] - _pad_x) if bb else 0)
        bx2 = int(EDIT_PREV_W * x2p) if x2p >= 0 else ((bb[2] + _pad_x) if bb else EDIT_PREV_W)
        return max(0, bx1), min(EDIT_PREV_W, bx2)

    def _display_edit_preview(self, img):
        from PIL import ImageTk
        ref = ImageTk.PhotoImage(img)
        self._edit_photo_ref = ref          # keep reference alive
        self._edit_canvas.delete("all")
        self._edit_canvas.create_image(0, 0, image=ref, anchor="nw")
        # Overlay interactive title handles on top of the PIL image
        if self._edit_sel_idx >= 0 and not self._edit_draw_mode:
            self._draw_title_handles()

    def _draw_title_handles(self):
        """Draw CapCut-style tight bounding box + handles using cached PIL text bb."""
        import textwrap, re as _re
        if self._edit_sel_idx < 0:
            return
        st    = self._edit_queue[self._edit_sel_idx]["state"]
        title = self._edit_queue[self._edit_sel_idx]["title"]

        tx       = int(st.get("text_x", 40) * EDIT_PREV_SCALE)
        ty       = int(st.get("text_y", 60) * EDIT_PREV_SCALE)
        wrap_pct = max(0.3, min(1.0, float(st.get("title_wrap_pct", 1.0))))
        font_size = st.get("font_size", 52)
        # rx_wrap = right edge of the WRAP BOUNDARY (where resize handle lives)
        rx_wrap  = min(int(EDIT_PREV_W * wrap_pct), EDIT_PREV_W - 4)

        # Use cached PIL bounding box (computed in _build_edit_image) for tight fit.
        # Fallback to rough estimate if cache is stale or missing.
        bb = getattr(self, "_title_bb_cache", None)
        if bb is None:
            clean = _re.sub(r"[^\x00-\x7F\u00C0-\u024F]", "", title).strip()
            chars = max(10, int(30 * 52 / max(font_size, 1) * wrap_pct))
            lines = textwrap.wrap(clean, width=chars) or [clean[:chars]]
            fsz   = max(8, int(font_size * EDIT_PREV_SCALE))
            est_h = int(len(lines) * fsz * 1.35)
            bb    = (tx, ty, rx_wrap, ty + est_h)

        PAD = 5
        bx1, by1 = bb[0] - PAD, bb[1] - PAD
        bx2, by2 = bb[2] + PAD, bb[3] + PAD

        # Dashed selection rectangle — tight around actual text pixels
        self._edit_canvas.create_rectangle(
            bx1, by1, bx2, by2,
            outline="#22d3ee", width=1, dash=(4, 2), tags="title_box",
        )
        # Corner circles (CapCut style — 4 corners)
        for cx, cy in [(bx1, by1), (bx2, by1), (bx1, by2), (bx2, by2)]:
            self._edit_canvas.create_oval(
                cx - 5, cy - 5, cx + 5, cy + 5,
                fill="#22d3ee", outline="white", width=1, tags="title_box",
            )
        # Right-edge resize handle (square) — always at the WRAP BOUNDARY (rx_wrap),
        # NOT the text content edge, so detection in _on_edit_drag_start matches exactly.
        mid_y = (by1 + by2) // 2
        self._edit_canvas.create_rectangle(
            rx_wrap - 6, mid_y - 6, rx_wrap + 6, mid_y + 6,
            fill="#22d3ee", outline="white", width=1, tags="title_box",
        )
        # Dashed vertical line at wrap boundary so user can see the wrap limit
        self._edit_canvas.create_line(
            rx_wrap, by1, rx_wrap, by2,
            fill="#22d3ee", dash=(2, 4), width=1, tags="title_box",
        )

        # Box left/right edge handles — amber arrows, visible only when text_bg=="box".
        # These let the user drag the dark box edge independently from the text.
        if st.get("text_bg") == "box":
            bx1, bx2 = self._compute_box_x_edges(st)
            mid_y = (by1 + by2) // 2
            hs = 10  # half-size of arrow triangle
            # ◀ left arrow handle
            self._edit_canvas.create_polygon(
                bx1 + hs, mid_y - hs,
                bx1,      mid_y,
                bx1 + hs, mid_y + hs,
                fill="#f59e0b", outline="white", width=1, tags="title_box",
            )
            # ▶ right arrow handle
            self._edit_canvas.create_polygon(
                bx2 - hs, mid_y - hs,
                bx2,      mid_y,
                bx2 - hs, mid_y + hs,
                fill="#f59e0b", outline="white", width=1, tags="title_box",
            )

    def _on_edit_motion(self, event):
        """Update cursor based on which handle the pointer is near."""
        if self._edit_draw_mode or self._edit_sel_idx < 0:
            return
        st = self._edit_queue[self._edit_sel_idx]["state"]
        wrap_pct = float(st.get("title_wrap_pct", 1.0))
        rx = min(int(EDIT_PREV_W * wrap_pct), EDIT_PREV_W - 4)
        HIT = 18
        if abs(event.x - rx) < HIT:
            self._edit_canvas.config(cursor="sb_h_double_arrow")
        elif st.get("text_bg") == "box":
            bx1, bx2 = self._compute_box_x_edges(st)
            if abs(event.x - bx1) < HIT or abs(event.x - bx2) < HIT:
                self._edit_canvas.config(cursor="sb_h_double_arrow")
            else:
                self._edit_canvas.config(cursor="fleur")
        else:
            self._edit_canvas.config(cursor="fleur")

    def _on_edit_drag_start(self, event):
        self._edit_drag_origin  = (event.x, event.y)
        self._edit_resize_mode  = False
        self._edit_box_l_mode   = False   # dragging box LEFT edge
        self._edit_box_r_mode   = False   # dragging box RIGHT edge

        if self._edit_draw_mode or self._edit_sel_idx < 0:
            return

        st = self._edit_queue[self._edit_sel_idx]["state"]
        wrap_pct = float(st.get("title_wrap_pct", 1.0))
        rx  = min(int(EDIT_PREV_W * wrap_pct), EDIT_PREV_W - 4)
        HIT = 18

        if abs(event.x - rx) < HIT:
            self._edit_resize_mode  = True
            self._drag_wrap_origin  = wrap_pct
            self._drag_wrap_start_x = event.x
        elif st.get("text_bg") == "box":
            bx1, bx2 = self._compute_box_x_edges(st)
            if abs(event.x - bx1) < HIT:
                self._edit_box_l_mode    = True
                self._drag_box_start_x   = event.x
                self._drag_box_x1_origin = bx1 / EDIT_PREV_W
            elif abs(event.x - bx2) < HIT:
                self._edit_box_r_mode    = True
                self._drag_box_start_x   = event.x
                self._drag_box_x2_origin = bx2 / EDIT_PREV_W
            else:
                self._drag_text_origin = (st["text_x"], st["text_y"])
        else:
            self._drag_text_origin = (st["text_x"], st["text_y"])

    def _on_edit_drag(self, event):
        if self._edit_sel_idx < 0:
            return
        if self._edit_draw_mode:
            x0, y0 = self._edit_drag_origin
            self._edit_canvas.delete("rubber_band")
            self._edit_canvas.create_rectangle(
                x0, y0, event.x, event.y,
                outline="#22d3ee", width=2, dash=(4, 2),
                tags="rubber_band",
            )
            return

        st = self._edit_queue[self._edit_sel_idx]["state"]

        def _regen():
            img = self._build_edit_image(
                self._edit_queue[self._edit_sel_idx]["clip_path"],
                self._edit_queue[self._edit_sel_idx]["title"], st)
            if img:
                self._display_edit_preview(img)

        if self._edit_resize_mode:
            # Text wrap width handle (cyan square)
            dx_pct = (event.x - self._drag_wrap_start_x) / EDIT_PREV_W
            new_pct = max(0.15, min(1.0, self._drag_wrap_origin + dx_pct))
            st["title_wrap_pct"] = new_pct
            self._edit_title_wrap_pct.set(new_pct)
            _regen()
            return

        if getattr(self, "_edit_box_l_mode", False):
            # Box LEFT edge handle (amber ◀) — drag changes box_x1_pct
            dx_pct = (event.x - self._drag_box_start_x) / EDIT_PREV_W
            x2_max = float(st.get("box_x2_pct", -1.0))
            if x2_max < 0:  # auto right — treat as current right edge in pct
                _, bx2 = self._compute_box_x_edges(st)
                x2_max = bx2 / EDIT_PREV_W
            new_pct = max(0.0, min(x2_max - 0.05, self._drag_box_x1_origin + dx_pct))
            st["box_x1_pct"] = new_pct
            _regen()
            return

        if getattr(self, "_edit_box_r_mode", False):
            # Box RIGHT edge handle (amber ▶) — drag changes box_x2_pct
            dx_pct = (event.x - self._drag_box_start_x) / EDIT_PREV_W
            x1_min = float(st.get("box_x1_pct", -1.0))
            if x1_min < 0:
                bx1, _ = self._compute_box_x_edges(st)
                x1_min = bx1 / EDIT_PREV_W
            new_pct = min(1.0, max(x1_min + 0.05, self._drag_box_x2_origin + dx_pct))
            st["box_x2_pct"] = new_pct
            _regen()
            return

        # Normal mode: move the title text
        dx = int((event.x - self._edit_drag_origin[0]) / EDIT_PREV_SCALE)
        dy = int((event.y - self._edit_drag_origin[1]) / EDIT_PREV_SCALE)
        st["text_x"] = max(0, min(980, self._drag_text_origin[0] + dx))
        st["text_y"] = max(0, min(1820, self._drag_text_origin[1] + dy))
        _regen()

    def _on_edit_drag_end(self, event):
        if self._edit_draw_mode and self._edit_sel_idx >= 0:
            self._edit_canvas.delete("rubber_band")
            x0, y0 = self._edit_drag_origin
            x1, y1 = event.x, event.y
            rw, rh = abs(x1 - x0), abs(y1 - y0)
            if rw < 5 or rh < 5:
                return  # ignore accidental micro-clicks
            box = {
                "x": int(min(x0, x1) / EDIT_PREV_SCALE),
                "y": int(min(y0, y1) / EDIT_PREV_SCALE),
                "w": int(rw / EDIT_PREV_SCALE),
                "h": int(rh / EDIT_PREV_SCALE),
            }
            boxes = self._edit_queue[self._edit_sel_idx]["state"]["blur_boxes"]
            boxes.append(box)
            n = len(boxes)
            self._blur_listbox.insert(
                END, f"Box {n}: ({box['x']},{box['y']})  {box['w']}×{box['h']} px")
            self._regen_edit_preview()

    # ── Blur-region / cover-banner helpers ──────────────────────────────────

    def _pick_box_bg_color(self):
        """Open color picker for text background box; persists selection to config."""
        from tkinter.colorchooser import askcolor
        current = self._edit_box_bg_color_hex.get() or "#222222"
        result = askcolor(color=current, title="Text Background Color", parent=self)
        if result and result[1]:
            hex_val = result[1]
            self._edit_box_bg_color_hex.set(hex_val)
            # Determine readable label fg
            fg_col = "white" if hex_val.lower() < "#888888" else "black"
            self._box_custom_swatch.config(bg=hex_val, fg=fg_col)
            # Switch radio to "custom"
            self._edit_box_bg_color.set("custom")
            # Persist to config so next session restores the color
            self._cfg["box_bg_custom_hex"] = hex_val
            self._save_config()
            self._regen_edit_preview()

    def _toggle_draw_mode(self):
        """Switch between title-drag mode and blur-box drawing mode."""
        self._edit_draw_mode = not self._edit_draw_mode
        self._draw_mode_on   = self._edit_draw_mode      # used by _on_escape
        if self._edit_draw_mode:
            self._btn_draw_mode.config(text="✏  Draw Mode: ON",
                                       bg="#0a2a1e", fg=CLR_SUCCESS,
                                       activebackground="#0f3d2a")
            self._edit_canvas.config(cursor="crosshair")
        else:
            self._btn_draw_mode.config(text="✏  Draw Mode: OFF",
                                       bg="#0f1e3d", fg="#60a5fa",
                                       activebackground="#172d5c")
            self._edit_canvas.config(cursor="fleur")

    def _clear_blur_boxes(self):
        """Remove all blur boxes from the current queue item."""
        if self._edit_sel_idx < 0:
            return
        self._edit_queue[self._edit_sel_idx]["state"]["blur_boxes"] = []
        self._blur_listbox.delete(0, END)
        self._regen_edit_preview()

    def _refresh_blur_listbox(self):
        """Rebuild the blur listbox with mode icons and start_time info."""
        self._blur_listbox.delete(0, END)
        if self._edit_sel_idx < 0:
            return
        boxes = self._edit_queue[self._edit_sel_idx]["state"].get("blur_boxes", [])
        for _i, _b in enumerate(boxes):
            if _b.get("tracked"):
                label = f"🎯 Tracked {_i+1}"
            else:
                _icon = "🔍" if _b.get("mode") == "delogo" else "🫧"
                _st   = _b.get("start_time", 0.0) or 0.0
                _info = f" @{_st:.1f}s" if _st > 0.05 else ""
                label = f"{_icon} Box {_i+1}: ({_b['x']},{_b['y']}) {_b['w']}×{_b['h']}px{_info}"
            self._blur_listbox.insert(END, label)

    def _remove_selected_blur_box(self):
        """Remove the blur box selected in the listbox."""
        if self._edit_sel_idx < 0:
            return
        sel = self._blur_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        boxes = self._edit_queue[self._edit_sel_idx]["state"]["blur_boxes"]
        if 0 <= idx < len(boxes):
            boxes.pop(idx)
            self._refresh_blur_listbox()
            self._regen_edit_preview()

    # ── Object Tracking ────────────────────────────────────────────────────────

    def _open_track_popup(self):
        """ROI picker with time-seek slider → run CSRT tracker from chosen frame."""
        if self._edit_sel_idx < 0:
            messagebox.showwarning("No clip", "Select a clip first.")
            return

        try:
            import cv2 as _cv2  # noqa
        except ImportError:
            messagebox.showerror(
                "OpenCV Required",
                "Install opencv-contrib-python to use object tracking:\n\n"
                "  pip install opencv-contrib-python\n\nThen restart the app."
            )
            return

        clip = Path(self._edit_queue[self._edit_sel_idx]["clip_path"])
        if not clip.exists():
            messagebox.showerror("File not found", str(clip))
            return

        dur     = get_video_duration(clip) or 10.0
        orig_vw = get_video_width(clip)
        orig_vh = get_video_height(clip)

        # Max display: 600 wide OR 440 tall (keeps popup on screen)
        MAX_W, MAX_H = 580, 340
        scale = min(MAX_W / orig_vw, MAX_H / orig_vh, 1.0)
        disp_w = max(1, int(orig_vw * scale))
        disp_h = max(1, int(orig_vh * scale))
        disp_scale_x = orig_vw / disp_w
        disp_scale_y = orig_vh / disp_h

        import tempfile as _tmp
        from PIL import Image as _PI, ImageTk as _PITk

        frame_png = Path(_tmp.gettempdir()) / f"_track_frame_{clip.stem[:30]}.png"

        def _extract_frame(t_sec: float) -> bool:
            """Extract frame at t_sec → frame_png. Returns True on success."""
            r = subprocess.run(
                [FFMPEG, "-y", "-ss", f"{t_sec:.3f}", "-i", str(clip),
                 "-vframes", "1",
                 "-vf", f"scale={disp_w}:{disp_h}",
                 str(frame_png)],
                capture_output=True, timeout=30,
            )
            return r.returncode == 0 and frame_png.exists() and frame_png.stat().st_size > 0

        # Extract first frame to start
        if not _extract_frame(0.0):
            messagebox.showerror("Frame extract failed",
                                 "Could not extract frame from clip.")
            return

        # ── Build popup ────────────────────────────────────────────────────────
        popup = tk.Toplevel(self)
        popup.title("🎯 Track Object — Seek to where object appears, then draw box")
        popup.configure(bg=CLR_BG)
        popup.grab_set()
        popup.resizable(False, False)

        tk.Label(popup,
                 text="① Drag the time slider to where the object first appears\n"
                      "② Click & drag on the frame to draw a box around it\n"
                      "③ Click Confirm & Track",
                 bg=CLR_BG, fg=CLR_FG, font=("Segoe UI", 9),
                 justify=LEFT).pack(pady=(10, 4), padx=12, anchor=W)

        # ── Canvas ────────────────────────────────────────────────────────────
        canvas = tk.Canvas(popup, width=disp_w, height=disp_h,
                           cursor="crosshair", bg="#111",
                           highlightthickness=2, highlightbackground="#334155")
        canvas.pack(padx=12, pady=(0, 4))

        _img_ref: list = [None]   # mutable cell to hold PhotoImage ref

        def _show_frame_on_canvas():
            try:
                pil = _PI.open(frame_png).convert("RGB")
                tk_img = _PITk.PhotoImage(pil)
                _img_ref[0] = tk_img       # prevent GC
                canvas.delete("all")
                canvas.create_image(0, 0, anchor=NW, image=tk_img)
                # Redraw ROI if already drawn
                if _roi["rect"]:
                    _roi["rect"] = canvas.create_rectangle(
                        _roi["x0"], _roi["y0"], _roi["x1"], _roi["y1"],
                        outline="#4ade80", width=2, dash=(4, 2)
                    )
            except Exception as e:
                pass

        _show_frame_on_canvas()

        # ── Time seek slider ───────────────────────────────────────────────────
        seek_row = tk.Frame(popup, bg=CLR_BG)
        seek_row.pack(fill=X, padx=12, pady=(0, 2))
        tk.Label(seek_row, text="Seek:", bg=CLR_BG, fg=CLR_DIM,
                 font=("Segoe UI", 8)).pack(side=LEFT)

        _seek_var = tk.DoubleVar(value=0.0)
        _seek_lbl = tk.Label(seek_row, text="0.0s", bg=CLR_BG, fg=CLR_FG2,
                             font=("Consolas", 8), width=6)
        _seek_lbl.pack(side=RIGHT)

        def _on_seek_change(v):
            t = float(v)
            _seek_lbl.config(text=f"{t:.1f}s")

        def _on_seek_release(event=None):
            t = _seek_var.get()
            popup.config(cursor="watch")
            popup.update()
            # Re-extract frame at this time
            _extract_frame(t)
            _roi["rect"] = None   # clear old ROI on frame change
            _show_frame_on_canvas()
            popup.config(cursor="")

        seek_scale = tk.Scale(
            seek_row, variable=_seek_var,
            from_=0, to=dur, resolution=0.1,
            orient=HORIZONTAL, length=disp_w - 70,
            bg=CLR_BG, fg=CLR_FG, troughcolor=CLR_SURFACE,
            highlightthickness=0, bd=0, sliderrelief=FLAT,
            command=_on_seek_change, showvalue=False,
        )
        seek_scale.pack(side=LEFT, fill=X, expand=True, padx=(4, 4))
        seek_scale.bind("<ButtonRelease-1>", _on_seek_release)

        # ── ROI drag ──────────────────────────────────────────────────────────
        _roi = {"x0": 0, "y0": 0, "x1": 0, "y1": 0, "rect": None}

        def _on_press(ev):
            _roi["x0"] = ev.x; _roi["y0"] = ev.y
            if _roi["rect"]:
                canvas.delete(_roi["rect"])
                _roi["rect"] = None

        def _on_drag(ev):
            _roi["x1"] = ev.x; _roi["y1"] = ev.y
            if _roi["rect"]:
                canvas.delete(_roi["rect"])
            _roi["rect"] = canvas.create_rectangle(
                _roi["x0"], _roi["y0"], ev.x, ev.y,
                outline="#4ade80", width=2, dash=(4, 2)
            )

        def _on_release(ev):
            _roi["x1"] = ev.x; _roi["y1"] = ev.y

        canvas.bind("<ButtonPress-1>",   _on_press)
        canvas.bind("<B1-Motion>",       _on_drag)
        canvas.bind("<ButtonRelease-1>", _on_release)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = tk.Frame(popup, bg=CLR_BG)
        btn_row.pack(pady=(4, 12), padx=12, fill=X)

        def _confirm():
            x0 = min(_roi["x0"], _roi["x1"])
            y0 = min(_roi["y0"], _roi["y1"])
            x1 = max(_roi["x0"], _roi["x1"])
            y1 = max(_roi["y0"], _roi["y1"])
            if (x1 - x0) < 10 or (y1 - y0) < 10:
                messagebox.showwarning("Too small",
                                       "Draw a larger box around the object.", parent=popup)
                return
            seek_t = _seek_var.get()
            popup.destroy()

            # Convert display coords → original video coords
            roi_video = (
                int(x0 * disp_scale_x), int(y0 * disp_scale_y),
                int((x1 - x0) * disp_scale_x), int((y1 - y0) * disp_scale_y),
            )
            self._logger.info(
                f"🎯 Starting CSRT tracker on {clip.name} from {seek_t:.1f}s…")
            threading.Thread(
                target=self._run_tracker,
                args=(clip, roi_video, self._edit_sel_idx, seek_t),
                daemon=True,
            ).start()

        tk.Button(
            btn_row, text="✅  Confirm & Track",
            bg=CLR_ACCENT, fg="white",
            activebackground=CLR_ACCENT_D, activeforeground="white",
            font=("Segoe UI", 9, "bold"), relief=FLAT,
            cursor="hand2", padx=12, pady=6,
            command=_confirm,
        ).pack(side=LEFT, fill=X, expand=True)
        SecondaryButton(btn_row, text="Cancel",
                        command=popup.destroy).pack(side=RIGHT, padx=(8, 0))

    def _run_tracker(self, clip: Path, roi: tuple, item_idx: int,
                     seek_time: float = 0.0):
        """Background thread: CSRT-track roi starting from seek_time, save .track.json."""
        try:
            import cv2 as cv2

            cap = cv2.VideoCapture(str(clip))
            if not cap.isOpened():
                self.after(0, lambda: self._logger.error("Tracker: could not open clip."))
                return

            fps   = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            vw    = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            vh    = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            # Seek to chosen frame
            start_frame = max(0, int(seek_time * fps))
            if start_frame > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

            ok, frame = cap.read()
            if not ok:
                self.after(0, lambda: self._logger.error("Tracker: could not read frame."))
                return

            # Create CSRT tracker — API changed between OpenCV 4 and 5
            if hasattr(cv2, "TrackerCSRT_create"):
                tracker = cv2.TrackerCSRT_create()
            elif hasattr(cv2, "tracking") and hasattr(cv2.tracking, "TrackerCSRT_create"):
                tracker = cv2.tracking.TrackerCSRT_create()
            elif hasattr(cv2, "legacy") and hasattr(cv2.legacy, "TrackerCSRT_create"):
                tracker = cv2.legacy.TrackerCSRT_create()
            else:
                self.after(0, lambda: self._logger.error(
                    "TrackerCSRT not available — install opencv-contrib-python"))
                cap.release()
                return

            tracker.init(frame, roi)

            frames_data: list[dict] = []
            frame_idx = start_frame  # absolute frame index

            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                frame_idx += 1
                success, bbox = tracker.update(frame)
                if success:
                    x, y, w, h = [int(v) for v in bbox]
                    # Clamp to valid frame region
                    x = max(0, min(x, vw - 1)); w = min(w, vw - x)
                    y = max(0, min(y, vh - 1)); h = min(h, vh - y)
                    # Only record this frame if the box is meaningfully inside the frame.
                    # Skipping out-of-frame frames lets CSRT naturally re-acquire
                    # when the object re-enters instead of holding a stale edge position.
                    if w > 4 and h > 4:
                        frames_data.append({"frame": frame_idx, "t": frame_idx / fps,
                                            "x": x, "y": y, "w": w, "h": h})
                # On tracker failure (object fully out of frame) we intentionally
                # skip adding a frame entry so no blur is drawn on those frames.

                if frame_idx % 30 == 0:
                    pct = frame_idx / max(total, 1) * 100
                    self.after(0, lambda p=pct: self._logger.dim(f"   Tracking… {p:.0f}%"))

            cap.release()

            # Save .track.json
            track_p = clip.with_suffix(".track.json")
            import json as _json
            _json.dump({"fps": fps, "width": vw, "height": vh,
                        "seek_time": seek_time,
                        "frames": frames_data},
                       open(track_p, "w"), indent=2)

            def _add_tracked():
                if item_idx < len(self._edit_queue):
                    st    = self._edit_queue[item_idx]["state"]
                    boxes = st.setdefault("blur_boxes", [])
                    boxes.append({
                        "x": roi[0], "y": roi[1], "w": roi[2], "h": roi[3],
                        "tracked": True, "track_file": str(track_p),
                    })
                    n = sum(1 for b in boxes if b.get("tracked"))
                    self._blur_listbox.insert(END, f"🎯 Tracked {n}  (from {seek_time:.1f}s)")
                    self._logger.ok(
                        f"🎯 Tracking complete — {len(frames_data)} frames"
                        f"  (start={seek_time:.1f}s) → {track_p.name}")
                    self._regen_edit_preview()

            self.after(0, _add_tracked)

        except Exception as exc:
            self.after(0, lambda: self._logger.error(f"Tracker failed: {exc}"))


    # ── Bulk export ───────────────────────────────────────────────────────────

    def _start_export_all(self):
        """Export all queued clips sequentially in a background thread."""
        if not self._edit_queue:
            return
        self._btn_export_one.config(state=DISABLED)
        self._btn_export_all.config(state=DISABLED, text="Exporting…")
        self._set_status("Rendering all clips (9:16)…", CLR_WARN)

        # Show progress bar
        self._render_progress_var.set(0.0)
        self._render_progress_lbl.config(text="0%")
        self._render_progress_frame.pack(fill=X, pady=(0, 4), before=self._btn_export_one)

        threading.Thread(target=self._export_all_worker, daemon=True).start()

    def _export_all_worker(self):
        import concurrent.futures
        total = len(self._edit_queue)
        render_cfg = self._get_render_cfg()
        is_gpu = render_cfg.get("vcodec") in {"h264_nvenc", "hevc_nvenc", "h264_qsv", "hevc_qsv", "h264_amf", "hevc_amf"}
        user_threads = self._export_threads_var.get()
        max_workers = max(1, min(3 if is_gpu else 4, user_threads))
        # Shared counters (GIL-safe for simple int reads within after())
        done_count = [0]
        failed_count = [0]
        retry_items = []
        retry_lock = threading.Lock()

        def _export_one(idx_item, is_retry=False):
            i, item = idx_item
            clip  = item["clip_path"]
            title = item["title"]
            state = dict(item["state"])  # copy so concurrent jobs don't stomp each other
            state.update({
                "color_grade": self._opt_color_grade.get(),
                "subtitles":   self._opt_subtitles.get(),
            })
            out_dir = Path(self._output_var.get())
            video_dir = out_dir / "video"
            video_dir.mkdir(parents=True, exist_ok=True)
            dst = video_dir / (clip.stem + "_reup.mp4")

            def _on_progress(frac: float, _i=i):
                pct = max(0.0, min(100.0, frac * 100))
                self.after(0, lambda p=pct: (
                    self._render_progress_var.set(p),
                    self._render_progress_lbl.config(
                        text=f"[{_i+1}/{total}] {p:.0f}%"),
                ))

            try:
                srt = None
                if state["subtitles"]:
                    client, sdk = None, None
                    for k in self._get_all_keys():
                        if k.strip():
                            try:
                                client, sdk = build_client(k.strip())
                                break
                            except Exception:
                                pass
                    _sub_engine = state.get("sub_engine", "gemini_fallback")
                    _sub_style  = state.get("sub_style", "Normal")
                    _word_lvl   = True
                    # Use a fresh Event so a previous "Stop analysis" signal
                    # doesn't immediately abort subtitle transcription.
                    _sub_stop   = threading.Event()
                    if _sub_engine == "whisper":
                        if WHISPER_AVAILABLE:
                            srt = _whisper_transcribe(clip, self._logger, word_level=True, edit_state=state)
                        if srt is None and client and sdk:
                            self._logger.warn("Whisper unavailable or failed — falling back to Gemini")
                            srt = _gemini_transcribe(clip, client, sdk,
                                                     self._logger, _sub_stop,
                                                     word_level=_word_lvl,
                                                     model_name=self._get_model_name(),
                                                     edit_state=state)
                    elif _sub_engine == "gemini":
                        if client and sdk:
                            srt = _gemini_transcribe(clip, client, sdk,
                                                     self._logger, _sub_stop,
                                                     word_level=_word_lvl,
                                                     model_name=self._get_model_name(),
                                                     edit_state=state)
                    else:  # "gemini_fallback"
                        if client and sdk:
                            srt = _gemini_transcribe(clip, client, sdk,
                                                     self._logger, _sub_stop,
                                                     word_level=_word_lvl,
                                                     model_name=self._get_model_name(),
                                                     edit_state=state)
                        if srt is None and WHISPER_AVAILABLE:
                            srt = _whisper_transcribe(clip, self._logger, word_level=True, edit_state=state)

                render_reup(clip, dst, title,
                            state["color_grade"], srt, self._logger,
                            edit_state=state,
                            render_cfg=render_cfg,
                            progress_cb=_on_progress)

                # Organize outputs
                import shutil
                if srt and srt.exists():
                    srt_dir = out_dir / "srt"
                    srt_dir.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy(srt, srt_dir / (clip.stem + "_reup.srt"))
                        srt.unlink(missing_ok=True)
                    except Exception as e:
                        self._logger.warn(f"Could not copy SRT: {e}")

                words_json = clip.with_suffix(".words.json")
                if words_json.exists():
                    json_dir = out_dir / "json"
                    json_dir.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy(words_json, json_dir / (clip.stem + "_reup.json"))
                        words_json.unlink(missing_ok=True)
                    except Exception as e:
                        self._logger.warn(f"Could not copy JSON: {e}")

                done_count[0] += 1
                self._logger.ok(f"[{i+1}/{total}] {dst.name}")

            except Exception as exc:
                is_mem_err = any(err_sig in str(exc).lower() for err_sig in [
                    "cannot allocate memory", "-12", "4294967284", "out of memory",
                    "resource temporarily unavailable", "conversion failed", "oom"
                ])
                if not is_retry and is_mem_err:
                    self._logger.warn(f"[{i+1}/{total}] Quá tải bộ nhớ VRAM: xếp vào hàng đợi tự động thử lại...")
                    with retry_lock:
                        retry_items.append(idx_item)
                    return

                failed_count[0] += 1
                self._logger.error(f"[{i+1}/{total}] Failed: {exc}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            pool.map(_export_one, enumerate(self._edit_queue))

        if retry_items:
            self._logger.info(f"🔄 Đang tự động thử lại (Auto-Retry) {len(retry_items)} video ở chế độ giải phóng VRAM...")
            import time
            time.sleep(1.2)
            for r_item in retry_items:
                _export_one(r_item, is_retry=True)

        self.after(0, lambda: (
            self._btn_export_one.config(state=NORMAL),
            self._btn_export_all.config(state=NORMAL, text="📦  Export All"),
            self._render_progress_frame.pack_forget(),
            self._set_status(
                f"Export complete — {done_count[0]} ok, {failed_count[0]} failed",
                CLR_SUCCESS if not failed_count[0] else CLR_WARN),
        ))


    # ── Dynamic key rows ───────────────────────────────────────────────────

    def _add_key_row(self, value: str = ""):
        container = self._keys_container
        num = len(self._key_rows) + 1

        row_frame = ttk.Frame(container, style="Panel.TFrame")
        row_frame.pack(fill=X, pady=2)

        num_lbl = ttk.Label(row_frame, text=f"#{num}", style="Panel.TLabel",
                            width=3, anchor=E)
        num_lbl.pack(side=LEFT, padx=(0, 4))

        var = tk.StringVar(value=value)
        entry = ttk.Entry(row_frame, textvariable=var, show="●", width=26)
        entry.pack(side=LEFT, fill=X, expand=True)

        row_dict = {
            "frame":   row_frame,
            "var":     var,
            "entry":   entry,
            "label":   num_lbl,
            "visible": False,
        }

        vis_btn = tk.Button(
            row_frame, text="👁", bg=CLR_PANEL, fg=CLR_DIM,
            font=("Segoe UI", 9), relief=FLAT, width=2,
            command=lambda rd=row_dict: self._toggle_key_vis(rd),
        )
        vis_btn.pack(side=LEFT, padx=(3, 0))
        row_dict["vis_btn"] = vis_btn

        del_btn = tk.Button(
            row_frame, text="✕", bg=CLR_PANEL, fg=CLR_ERROR,
            font=("Segoe UI", 9), relief=FLAT, width=2,
            command=lambda rd=row_dict: self._remove_key_row(rd),
        )
        del_btn.pack(side=LEFT, padx=(2, 0))

        self._key_rows.append(row_dict)

        # When called by the user (value=""), scroll the left panel to reveal
        # the new row and focus the entry so they can type immediately.
        # Skip this for config-restore calls (value is a non-empty saved key).
        if not value:
            def _scroll_and_focus():
                self.update_idletasks()
                if hasattr(self, "_left_canvas"):
                    self._left_canvas.yview_moveto(1.0)
                entry.focus_set()
            self.after(30, _scroll_and_focus)

        return row_dict

    def _remove_key_row(self, rd: dict):
        if len(self._key_rows) <= 1:
            messagebox.showinfo("Info", "At least one API key row is required.")
            return
        rd["frame"].destroy()
        self._key_rows.remove(rd)
        self._renumber_key_rows()

    def _toggle_key_vis(self, rd: dict):
        rd["visible"] = not rd["visible"]
        rd["entry"].config(show="" if rd["visible"] else "●")
        rd["vis_btn"].config(fg=CLR_FG if rd["visible"] else CLR_DIM)

    def _renumber_key_rows(self):
        for i, rd in enumerate(self._key_rows):
            rd["label"].config(text=f"#{i+1}")

    def _get_all_keys(self) -> list[str]:
        return [rd["var"].get().strip() for rd in self._key_rows
                if rd["var"].get().strip()]

    # ── File helpers ────────────────────────────────────────────────────────

    def _pick_video_files(self):
        files = filedialog.askopenfilenames(
            title="Select Bodycam Video Files",
            filetypes=[("Video files", "*.mp4 *.mkv *.MP4 *.MKV"),
                       ("All files", "*.*")],
        )
        if files:
            self._video_files = [Path(f) for f in files]
            self._refresh_file_listbox()

    def _clear_video_files(self):
        self._video_files = []
        self._file_listbox.delete(0, END)
        self._file_count_lbl.config(text="No files selected.")

    def _remove_selected_files(self):
        """Remove the currently selected files from the list (Delete hotkey)."""
        selected = list(self._file_listbox.curselection())
        if not selected:
            return
        # Remove in reverse order so indices don't shift
        for idx in reversed(selected):
            self._file_listbox.delete(idx)
            del self._video_files[idx]
        n = len(self._video_files)
        self._file_count_lbl.config(
            text=f"{n} file{'s' if n != 1 else ''} selected." if n else "No files selected."
        )

    def _refresh_file_listbox(self):
        self._file_listbox.delete(0, END)
        for p in self._video_files:
            self._file_listbox.insert(END, p.name)
        n = len(self._video_files)
        self._file_count_lbl.config(text=f"{n} file{'s' if n != 1 else ''} selected.")

    def _pick_folder(self, var: tk.StringVar):
        folder = filedialog.askdirectory()
        if folder:
            var.set(folder)

    # ── Queue Treeview ──────────────────────────────────────────────────────

    def _queue_init(self, videos: list[Path]):
        """Populate queue with all selected videos at status=queued."""
        for item in self._queue.get_children():
            self._queue.delete(item)
        for vid in videos:
            self._queue.insert("", END, iid=str(vid),
                               values=("🕐", vid.name, "Queued"),
                               tags=(ST_QUEUED,))

    def _queue_update(self, path: Path, status: str, info: str = ""):
        """Update a row in the queue. Called via self.after() from threads."""
        iid = str(path)
        if not self._queue.exists(iid):
            return
        icons = {
            ST_QUEUED:    "🕐",
            ST_UPLOADING: "⬆️",
            ST_ANALYZING: "🔍",
            ST_DONE:      "✅",
            ST_ERROR:     "❌",
        }
        icon = icons.get(status, "")
        self._queue.item(iid, values=(icon, path.name, info), tags=(status,))

    def _on_queue_select(self, _event=None):
        sel = self._queue.selection()
        if not sel:
            return
        path = Path(sel[0])
        res  = self._video_results.get(str(path), {})
        if res.get("status") == ST_DONE:
            self._selected_video = path
            self._show_results(path, res.get("candidates", []))
        else:
            # Not done yet — clear results panel
            self._clear_results_panel(path.name, res.get("status", ""))

    def _update_video_status(self, path: Path, status: str,
                             candidates: Optional[list] = None,
                             error: str = ""):
        """Thread-safe: update _video_results and refresh queue row + progress."""
        def _on_main():
            self._video_results[str(path)] = {
                "status": status,
                "candidates": candidates or [],
                "error": error,
            }
            err_str = str(error)
            if "errno 2" in err_str.lower() or "no such file" in err_str.lower():
                err_lbl = "File not found"
            else:
                err_lbl = f"Error: {err_str[:40]}"
            label_map = {
                ST_QUEUED:    "Queued",
                ST_UPLOADING: "Uploading…",
                ST_ANALYZING: "Analyzing…",
                ST_DONE:      f"{len(candidates or [])} clips found",
                ST_ERROR:     err_lbl,
            }
            self._queue_update(path, status, label_map.get(status, status))
            self._refresh_progress()

        self.after(0, _on_main)

    def _refresh_progress(self):
        total  = len(self._video_files)
        done   = sum(1 for r in self._video_results.values()
                     if r["status"] in (ST_DONE, ST_ERROR))
        errors = sum(1 for r in self._video_results.values()
                     if r["status"] == ST_ERROR)
        pct    = (done / total * 100) if total else 0
        self._prog_var.set(pct)
        self._prog_lbl.config(
            text=f"{done}/{total} analyzed"
                 + (f"  •  {errors} error(s)" if errors else ""))
        if done == total and total > 0:
            self.after(0, self._all_done)

    def _all_done(self):
        success = sum(1 for r in self._video_results.values()
                      if r["status"] == ST_DONE)
        errors  = sum(1 for r in self._video_results.values()
                      if r["status"] == ST_ERROR)
        self._set_status(f"Done — {success}/{len(self._video_files)} succeeded",
                         CLR_SUCCESS)
        self._btn_analyze.config(state=NORMAL, text="▶  ANALYZE ALL",
                                 bg=CLR_ACCENT)
        self._btn_stop.config(state=DISABLED)
        # Enable retry only when there are failed videos
        self._btn_retry.config(state=NORMAL if errors > 0 else DISABLED)
        self._logger.ok(
            f"All videos analyzed! "
            + (f" {errors} failed — click 🔄 RETRY ERRORS to re-run them." if errors else "")
        )

    # ── Results panel ───────────────────────────────────────────────────────

    def _clear_results_panel(self, name: str = "", status: str = ""):
        self._player.stop()
        self._results_video_lbl.config(
            text=f"{name} — {ST_LABEL.get(status, 'not done yet')}")
        self._cand_box["values"] = []
        self._cand_var.set("—")
        self._reason_txt.configure(state=NORMAL)
        self._reason_txt.delete("1.0", END)
        self._reason_txt.configure(state=DISABLED)
        for btn in self._title_btns:
            btn.config(text="—", command=lambda: None)
        self._btn_cut.config(state=DISABLED)
        self._btn_play.config(state=DISABLED, text="▶  Play Preview", bg="#1e40af")
        self._draw_preview_placeholder()

    def _show_results(self, path: Path, candidates: list[dict]):
        self._results_video_lbl.config(text=path.name, foreground=CLR_FG)
        labels = [
            f"#{c.get('id', i+1)}  —  {c.get('start_time')} → {c.get('end_time')}"
            for i, c in enumerate(candidates)
        ]
        self._cand_box["values"] = labels
        if labels:
            self._cand_box.current(0)
            self._refresh_candidate_ui(path, candidates, 0)
        self._btn_cut.config(state=NORMAL if candidates else DISABLED)

    def _on_candidate_selected(self, _event=None):
        if not self._selected_video:
            return
        res = self._video_results.get(str(self._selected_video), {})
        candidates = res.get("candidates", [])
        idx = self._cand_box.current()
        if 0 <= idx < len(candidates):
            self._refresh_candidate_ui(self._selected_video, candidates, idx)

    def _refresh_candidate_ui(self, path: Path, candidates: list, idx: int):
        c = candidates[idx]
        # Reason
        self._reason_txt.configure(state=NORMAL)
        self._reason_txt.delete("1.0", END)
        self._reason_txt.insert(END, c.get("reason", ""))
        self._reason_txt.configure(state=DISABLED)
        # Titles
        titles = c.get("suggested_titles", [])
        for i, btn in enumerate(self._title_btns):
            title = titles[i] if i < len(titles) else ""
            btn.config(
                text=f"{i+1}. {title}" if title else f"{i+1}. —",
                command=(lambda t=title: self._copy_title(t)) if title else lambda: None,
            )
        # Reset reup title selection when candidate changes
        self._selected_title_for_reup = titles[0] if titles else ""
        if hasattr(self, "_reup_title_lbl"):
            hint = "Click a title above to select it for reup" if self._last_cut_path \
                   else "— cut a clip first —"
            self._reup_title_lbl.config(text=hint, foreground=CLR_DIM)
        # Preview
        start_ts = c.get("start_time", "00:00:00")
        self._trigger_preview(path, start_ts)

    def _copy_title(self, text: str):
        copy_to_clipboard(self, text)
        # Remember this title for the reup renderer
        self._selected_title_for_reup = text
        if hasattr(self, "_reup_title_lbl") and self._last_cut_path:
            short = text[:80] + "…" if len(text) > 80 else text
            self._reup_title_lbl.config(text=f"✓ {short}", foreground=CLR_FG)
        orig = self._status_lbl.cget("text")
        self._set_status("Copied!", CLR_ACCENT)
        self.after(1500, lambda: self._status_lbl.config(text=orig))

    # ── Preview player ───────────────────────────────────────────────────────

    def _draw_preview_placeholder(self):
        self._preview_canvas.delete("all")
        self._preview_canvas.create_rectangle(
            0, 0, PREVIEW_W, PREVIEW_H, fill="#0d0d1a", outline="")
        self._preview_canvas.create_text(
            PREVIEW_W // 2, PREVIEW_H // 2,
            text="📽  Select a completed video",
            fill=CLR_DIM, font=("Segoe UI", 10),
        )

    # Store pending video/timestamp for play button
    _pending_video:  Optional[Path] = None
    _pending_start:  float          = 0.0
    _preview_gen:    int            = 0   # incremented per request; stale threads bail early
    # Track running preview FFmpeg proc so we can kill it on next click
    _preview_proc:   Optional[subprocess.Popen] = None
    _preview_proc_lock: threading.Lock = None   # initialised in __init__

    def _trigger_preview(self, video: Path, timestamp: str):
        """Stop current playback, store target segment, show first frame."""
        self._player.stop()
        self._pending_video = video
        self._pending_start = ts_to_seconds(timestamp)
        self._btn_play.config(
            state=NORMAL,
            text="▶  Play Preview",
            bg="#1e40af",
        )
        self._prev_lbl.config(
            text=f"{timestamp}  (+{CLIP_DURATION}s)",
            foreground=CLR_FG,
        )

        # Kill any in-flight preview FFmpeg process immediately so rapid
        # video-switching never piles up concurrent FFmpeg extract processes.
        with self._preview_proc_lock:
            old_proc, self._preview_proc = self._preview_proc, None
        if old_proc and old_proc.poll() is None:
            try:
                old_proc.kill()
            except Exception:
                pass

        # Show first frame as thumbnail while stopped
        if not PIL_AVAILABLE:
            return
        self._preview_canvas.delete("all")
        self._preview_canvas.create_text(
            PREVIEW_W // 2, PREVIEW_H // 2,
            text="⏳  Loading first frame…", fill=CLR_DIM, font=("Segoe UI", 10))

        # Bump generation so any previously-queued _grab_first_frame exits early
        self._preview_gen += 1
        my_gen = self._preview_gen
        # Capture now — self._pending_start may change on the next click
        start_sec = self._pending_start

        def _grab_first_frame():
            """Extract first frame as JPEG; proc is tracked so it can be killed."""
            if my_gen != self._preview_gen:
                return

            fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
            stderr_data = b""
            proc = None
            try:
                cmd = [
                    FFMPEG, "-y", "-loglevel", "error",
                    "-ss", str(start_sec),        # local capture, not self._pending_start
                    "-i",  str(video),
                    "-frames:v", "1", "-q:v", "3",
                    "-vf", (
                        f"scale={PREVIEW_W}:{PREVIEW_H}:"
                        "force_original_aspect_ratio=decrease,"
                        f"pad={PREVIEW_W}:{PREVIEW_H}:"
                        "(ow-iw)/2:(oh-ih)/2:color=black,"
                        "format=yuvj420p"   # full-range YUV required by JPEG
                    ),
                    tmp_path,
                ]
                # Popen (not run) so _trigger_preview can kill this proc on next click
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.DEVNULL,
                )
                with self._preview_proc_lock:
                    self._preview_proc = proc

                try:
                    _, stderr_data = proc.communicate(timeout=60)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    _, stderr_data = proc.communicate()
                    if my_gen == self._preview_gen:
                        def _show_timeout(g=my_gen):
                            if g != self._preview_gen:
                                return
                            self._preview_canvas.delete("all")
                            self._preview_canvas.create_text(
                                PREVIEW_W // 2, PREVIEW_H // 2,
                                text="⚠️  Frame extraction timed out",
                                fill=CLR_WARN, font=("Segoe UI", 10),
                            )
                        self._preview_canvas.after(0, _show_timeout)
                    return
                finally:
                    with self._preview_proc_lock:
                        if self._preview_proc is proc:
                            self._preview_proc = None

                if my_gen != self._preview_gen:
                    return

                if (proc.returncode == 0
                        and os.path.exists(tmp_path)
                        and os.path.getsize(tmp_path) > 0):
                    img = Image.open(tmp_path).convert("RGB")
                    def _show(i=img, g=my_gen):
                        if g != self._preview_gen:
                            return
                        photo = ImageTk.PhotoImage(i)   # ← main thread ✓
                        self._player._photo_ref = photo
                        self._preview_canvas.delete("all")
                        self._preview_canvas.create_image(
                            PREVIEW_W // 2, PREVIEW_H // 2,
                            image=photo, anchor="center",
                        )
                    self._preview_canvas.after(0, _show)
                else:
                    err_raw = (stderr_data or b"").decode("utf-8", errors="replace").strip()
                    hint = err_raw.split("\n")[0][:90] if err_raw else "Seek beyond video end?"
                    def _show_err(h=hint, g=my_gen):
                        if g != self._preview_gen:
                            return
                        self._preview_canvas.delete("all")
                        self._preview_canvas.create_text(
                            PREVIEW_W // 2, PREVIEW_H // 2 - 12,
                            text="⚠️  Preview unavailable",
                            fill=CLR_WARN, font=("Segoe UI", 10, "bold"),
                        )
                        self._preview_canvas.create_text(
                            PREVIEW_W // 2, PREVIEW_H // 2 + 14,
                            text=h, fill=CLR_DIM, font=("Segoe UI", 8),
                            width=PREVIEW_W - 24,
                        )
                    self._preview_canvas.after(0, _show_err)

            except Exception:
                if my_gen == self._preview_gen:
                    self._preview_canvas.after(0, self._draw_preview_placeholder)
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        threading.Thread(target=_grab_first_frame, daemon=True).start()



    def _toggle_preview_playback(self):
        if self._player.is_playing:
            self._player.stop()
        else:
            if self._pending_video:
                self._player.play(
                    self._pending_video,
                    self._pending_start,
                    CLIP_DURATION,
                )

    def _on_player_state_change(self, playing: bool):
        """Called on main thread when player starts / stops."""
        if playing:
            self._btn_play.config(text="⏹  Stop Preview", bg="#7c3aed")
        else:
            self._btn_play.config(text="▶  Play Preview", bg="#1e40af")

    # ── Status / progress ────────────────────────────────────────

    def _set_status(self, text: str, color: str = CLR_SUCCESS):
        self._status_lbl.config(text=f"● {text}", foreground=color)

    def _check_deps(self):
        if not check_ffmpeg():
            messagebox.showwarning(
                "FFmpeg Missing",
                "FFmpeg not found on PATH.\n\n"
                "Install:  winget install --id Gyan.FFmpeg -e\n\nThen restart.",
            )
            self._logger.warn("FFmpeg not found — install before cutting clips.")
        else:
            self._logger.ok("FFmpeg detected on PATH.")
        if not PIL_AVAILABLE:
            self._logger.warn("Pillow missing — preview disabled.  pip install Pillow")
        self._logger.info(f"Model: {MODEL_NAME}  |  Clip: exactly {CLIP_DURATION}s")
        self._logger.info("Add API keys, select videos, then click ANALYZE ALL.")

    def _save_config(self):
        keys = self._get_all_keys()
        save_config({
            "api_keys":      keys,
            "api_key":       keys[0] if keys else "",
            "output_folder": self._output_var.get(),
            "video_files":   [str(p) for p in self._video_files],
            "render_cfg":    self._get_render_cfg(),
            "model_name":    self._get_model_name(),
            "include_cta":   self._cta_var.get() if hasattr(self, "_cta_var") else False,
        })

    def _get_model_name(self) -> str:
        """Return the currently selected model ID from the UI combobox."""
        if not hasattr(self, "_model_var"):
            return MODEL_NAME
        lbl = self._model_var.get()
        return getattr(self, "_model_label_to_id", {}).get(lbl, MODEL_NAME)

    def _get_render_cfg(self) -> dict:
        """Read Export Settings widgets → return a render_cfg dict for render_reup."""
        if not hasattr(self, "_export_res_var"):
            return {}   # UI not yet built
        _res_map = {
            "1080×1920 (Full HD)": (1080, 1920),
            "720×1280 (HD)":        (720,  1280),
            "540×960 (SD)":         (540,   960),
        }
        w, h = _res_map.get(self._export_res_var.get(), (1080, 1920))
        enc_lbl = self._export_enc_var.get()
        vcodec  = getattr(self, "_enc_to_id", {}).get(enc_lbl, "libx264")
        fps_str = self._export_fps_var.get()
        fps     = None if fps_str == "Original" else int(fps_str)
        return {
            "width":  w,
            "height": h,
            "vcodec": vcodec,
            "acodec": "aac",
            "crf":    self._export_crf_var.get(),
            "preset": self._export_preset_var.get(),
            "fps":    fps,
        }

    # ── Analyze ────────────────────────────────────────────

    def _start_analyze(self):
        keys   = self._get_all_keys()
        videos = self._video_files

        if not keys:
            messagebox.showerror("Missing", "Please enter at least one API key.")
            return
        if not videos:
            messagebox.showerror("Missing", "Please select video files first.")
            return
        missing = [v for v in videos if not v.exists()]
        if len(missing) == len(videos):
            messagebox.showerror(
                "Files Not Found",
                "None of the selected video files exist on disk!\n\n"
                "Please check if the video files were moved, deleted, or if the drive is disconnected.\n"
                "Reselect your video files in 'Input Videos'."
            )
            return
        if not self._output_var.get().strip():
            messagebox.showerror("Missing", "Please select an Output Folder.")
            return

        self._save_config()
        self._stop.clear()
        self._video_results = {}
        self._selected_video = None
        self._clear_results_panel()
        self._prog_var.set(0)
        self._prog_lbl.config(text="")
        self._draw_preview_placeholder()

        self._queue_init(videos)

        n = len(videos)
        max_concurrent = min(3, n)
        sem = threading.Semaphore(max_concurrent)

        self._btn_analyze.config(state=DISABLED, text="ANALYZING…", bg="#4f4f4f")
        self._btn_stop.config(state=NORMAL)
        self._btn_retry.config(state=DISABLED)
        self._btn_cut.config(state=DISABLED)
        self._set_status(
            f"Analyzing {n} video(s)  —  up to {max_concurrent} at a time…",
            CLR_WARN,
        )
        self._logger.header("=" * 50)
        self._logger.header(
            f"  Bulk analysis: {n} video(s), {len(keys)} key(s), "
            f"max {max_concurrent} concurrent"
        )
        self._logger.header("=" * 50)

        self._active_threads = []
        rotator = KeyRotator(keys)   # shared across all worker threads
        for video_path in videos:
            t = threading.Thread(
                target=self._analyze_one_video,
                args=(video_path, rotator, sem),
                daemon=True,
            )
            self._active_threads.append(t)
            t.start()
        self._toast(f"Analyzing {n} video(s)…", kind="info")

    def _analyze_one_video(self, video_path: Path,
                           rotator: "KeyRotator",
                           sem: threading.Semaphore):
        """Worker thread — runs concurrently, bounded by sem."""
        log = self._logger

        # Wait for a slot (max 3 running at once)
        sem.acquire()
        try:
            self._run_analysis(video_path, rotator, log)
        finally:
            sem.release()

    def _run_analysis(self, video_path: Path, rotator: "KeyRotator",
                      log: ToolLogger):

        if not video_path.exists():
            log.error(f"[{video_path.name}] File not found on disk: {video_path}")
            self._update_video_status(video_path, ST_ERROR, error="File not found")
            return

        self._update_video_status(video_path, ST_UPLOADING)
        result       = None
        last_exc     = None
        vid_dur_hint: Optional[float] = None   # set once, reused on key retries

        # Budget: try every key at most once before giving up.
        n_keys = len(rotator)

        # ── Encode proxy/timelapse ONCE before retry loop ──────────────────
        # Moving this outside the loop prevents re-encoding on every key rotation.
        vid_dur_hint = get_video_duration(video_path)
        if vid_dur_hint is not None:
            log.dim(
                f"[{video_path.name}] Duration: "
                f"{int(vid_dur_hint//60):02d}m{int(vid_dur_hint%60):02d}s"
            )
        ds_path, ds_cleanup, ds_speedup = _downsample_for_upload(video_path, log)

        try:
          for attempt in range(n_keys):
            if self._stop.is_set():
                self._update_video_status(video_path, ST_ERROR, error="Stopped")
                return

            key    = rotator.acquire()   # Least Connections: fewest-active, non-cooled key
            remote = None
            client = None
            sdk    = None

            try:
                client, sdk = build_client(key)

                self._update_video_status(video_path, ST_UPLOADING)
                remote = upload_video(client, sdk, ds_path, log, self._stop)

                self._update_video_status(video_path, ST_ANALYZING)
                # Pass the scaled duration so analyze_video gives Gemini accurate
                # timestamp bounds for the sped-up video it actually sees.
                scaled_dur = (vid_dur_hint / ds_speedup) if vid_dur_hint else None
                result = analyze_video(client, sdk, remote,
                                       video_path.name, log, self._stop,
                                       vid_duration=scaled_dur,
                                       model_name=self._get_model_name(),
                                       include_cta=self._cta_var.get() if hasattr(self, "_cta_var") else False)

                # Convert timestamps from sped-up timeline back to original.
                if ds_speedup != 1.0 and result and result.get("candidates"):
                    for cand in result["candidates"]:
                        raw_ts = ts_to_seconds(cand.get("start_time", "00:00:00"))
                        orig_s = raw_ts * ds_speedup
                        h = int(orig_s // 3600)
                        m = int((orig_s % 3600) // 60)
                        s = int(orig_s % 60)
                        cand["start_time"] = f"{h:02d}:{m:02d}:{s:02d}"
                    log.dim(
                        f"[{video_path.name}] Timestamps scaled back "
                        f"{ds_speedup:.2f}x to original timeline."
                    )

                # Correction loop: reuse the live remote file to retry when
                # all timestamps are invalid. Avoids re-upload cost.
                # Before each correction call, try MM:SS re-interpretation first
                # (Gemini sometimes writes 02:30:00 meaning 2min30sec for short videos).
                MAX_CORRECTIONS = 3
                for corr_attempt in range(MAX_CORRECTIONS):
                    raw_candidates = result.get("candidates", [])
                    # Clamp max_t to ≥0 so range never inverts for short clips.
                    # Lower bound is 0.0: 00:00:00 is valid for clips shorter than
                    # CLIP_DURATION (the whole clip IS the highlight).
                    max_t = max(0.0, (vid_dur_hint or float("inf")) - CLIP_DURATION)

                    invalid_cands = [
                        c for c in raw_candidates
                        if not (0.0 <= ts_to_seconds(c.get("start_time", "99:00:00")) <= max_t)
                    ]

                    if len(invalid_cands) < len(raw_candidates):
                        break   # at least some candidates are already valid

                    # All invalid — try MM:SS re-interpretation before burning an API call
                    if vid_dur_hint is not None:
                        rescued = _reinterpret_mmss(raw_candidates, vid_dur_hint)
                        if rescued:
                            log.dim(
                                f"[{video_path.name}] Re-interpreted "
                                f"{len(rescued)} timestamp(s) as MM:SS format."
                            )
                            break   # rescued candidates are now valid

                    if self._stop.is_set():
                        raise InterruptedError("Stopped by user.")

                    rejected = [c.get("start_time", "??") for c in invalid_cands]
                    log.warn(
                        f"[{video_path.name}] Correction {corr_attempt + 1}/{MAX_CORRECTIONS}: "
                        f"timestamps {rejected} invalid — re-analyzing with feedback…"
                    )
                    self._update_video_status(video_path, ST_ANALYZING)
                    result = analyze_video(
                        client, sdk, remote,
                        video_path.name, log, self._stop,
                        vid_duration=vid_dur_hint,
                        rejected_timestamps=rejected,
                        include_cta=self._cta_var.get() if hasattr(self, "_cta_var") else False,
                    )

            except InterruptedError:
                self._update_video_status(video_path, ST_ERROR, error="Stopped")
                return

            except Exception as exc:
                last_exc  = exc
                exc_str   = str(exc)
                exc_lower = exc_str.lower()
                is_quota  = any(kw in exc_lower for kw in (
                    "quota", "429", "rate limit",
                    "resource_exhausted", "too many requests",
                ))
                is_tcp = "10053" in exc_str or "10054" in exc_str

                # Apply cooldown so acquire() steers away from the failing key.
                if is_quota:
                    rotator.penalize(key, KeyRotator.COOLDOWN_RATE_LIMIT)
                    label = f"quota ({KeyRotator.COOLDOWN_RATE_LIMIT:.0f}s cooldown)"
                elif is_tcp:
                    rotator.penalize(key, KeyRotator.COOLDOWN_TCP)
                    label = f"TCP error ({KeyRotator.COOLDOWN_TCP:.0f}s cooldown)"
                else:
                    rotator.penalize(key, KeyRotator.COOLDOWN_GENERIC)
                    label = "error"

                if attempt < n_keys - 1:
                    log.warn(
                        f"[{video_path.name}] Attempt {attempt+1}/{n_keys} failed [{label}]: "
                        f"{exc_str[:60]} — trying next key…"
                    )
                    time.sleep(0.5)   # brief pause; cooldown handles which key is next
                else:
                    log.error(f"[{video_path.name}] {exc}")
                    self._update_video_status(
                        video_path, ST_ERROR, error=str(exc)[:80])
                    return

            else:
                break   # try succeeded — exit key-retry loop

            finally:
                rotator.release(key)   # always decrement active counter
                if remote is not None and client is not None and sdk is not None:
                    try:
                        delete_remote(client, sdk, remote, log)
                    except Exception:
                        pass

        finally:
            # Clean up proxy/timelapse temp file after all retries finish.
            if ds_cleanup:
                try:
                    ds_path.unlink(missing_ok=True)
                except Exception:
                    pass


        if result:
            candidates = result.get("candidates", [])

            # Validate timestamps against actual video duration.
            # Gemini can hallucinate timestamps beyond the video's end,
            # or pick the intro (00:00:00) which is never a dramatic moment.
            vid_dur = get_video_duration(video_path)
            if vid_dur is not None and candidates:
                # For clips shorter than CLIP_DURATION, 00:00:00 is the only possible
                # (and entirely valid) start — accept anything in [0, vid_dur).
                _max_valid = max(0.0, vid_dur - CLIP_DURATION)

                def _is_valid(c: dict) -> bool:
                    t = ts_to_seconds(c.get("start_time", "99:00:00"))
                    return 0.0 <= t <= _max_valid

                valid = [c for c in candidates if _is_valid(c)]

                # Rescue candidates where Gemini used MM:SS format instead of HH:MM:SS
                if len(valid) < len(candidates):
                    mmss_rescued = _reinterpret_mmss(
                        [c for c in candidates if not _is_valid(c)], vid_dur
                    )
                    if mmss_rescued:
                        log.dim(
                            f"[{video_path.name}] Re-interpreted "
                            f"{len(mmss_rescued)} timestamp(s) from MM:SS to HH:MM:SS."
                        )
                    valid = valid + mmss_rescued

                # Last-resort for very short clips: if still empty, accept 00:00:00
                # unconditionally (Gemini correctly identified start-of-clip as highlight).
                if not valid and vid_dur <= CLIP_DURATION + 2:
                    log.dim(
                        f"[{video_path.name}] Short clip ({vid_dur:.0f}s ≤ clip length) — "
                        "accepting 00:00:00 as valid start."
                    )
                    valid = candidates  # all returned candidates accepted as-is

                invalid = len(candidates) - len(valid)
                if invalid > 0:
                    dur_h = int(vid_dur // 3600)
                    dur_m = int((vid_dur % 3600) // 60)
                    dur_s = int(vid_dur % 60)
                    log.warn(
                        f"[{video_path.name}] {invalid} candidate(s) had invalid "
                        f"timestamps (video length: "
                        f"{dur_h:02d}:{dur_m:02d}:{dur_s:02d}) — filtered out"
                    )
                candidates = valid


            if not candidates:
                log.error(
                    f"[{video_path.name}] All Gemini timestamps still invalid after "
                    "correction attempts. Re-run analysis to try again."
                )
                self._update_video_status(
                    video_path, ST_ERROR,
                    error="All timestamps invalid -- retry analysis"
                )
                return

            log.ok(f"[{video_path.name}] {len(candidates)} valid candidate(s) ready.")
            self._update_video_status(video_path, ST_DONE, candidates=candidates)

        elif last_exc:
            self._update_video_status(
                video_path, ST_ERROR, error=str(last_exc)[:80])

    # ── Cut ─────────────────────────────────────────────────────────────────

    def _start_cut(self):
        if not self._selected_video:
            messagebox.showwarning("No Video", "Select a completed video in the queue first.")
            return
        res = self._video_results.get(str(self._selected_video), {})
        candidates = res.get("candidates", [])
        idx = self._cand_box.current()
        if idx < 0 or idx >= len(candidates):
            messagebox.showwarning("No Candidate", "Please select a candidate first.")
            return

        chosen    = candidates[idx]
        start_ts  = chosen.get("start_time", "00:00:00")
        start_sec = ts_to_seconds(start_ts)

        # Guard: validate that start timestamp is within the actual video duration.
        # Gemini occasionally hallucinates timestamps beyond the video length.
        vid_duration = get_video_duration(self._selected_video)
        if vid_duration is not None and start_sec >= vid_duration:
            dur_h = int(vid_duration // 3600)
            dur_m = int((vid_duration % 3600) // 60)
            dur_s = int(vid_duration % 60)
            messagebox.showerror(
                "Invalid Timestamp",
                f"Candidate timestamp {start_ts} is BEYOND the video duration.\n"
                f"Video length : {dur_h:02d}:{dur_m:02d}:{dur_s:02d}\n"
                f"Requested    : {start_ts}\n\n"
                "Gemini returned an incorrect timestamp for this candidate.\n"
                "Please choose a different candidate or re-run the analysis."
            )
            self._set_status(f"Timestamp {start_ts} beyond video end — skipped", CLR_ERROR)
            return

        out_dir  = Path(self._output_var.get())
        stem     = sanitize(self._selected_video.stem)
        out_name = (
            f"{stem}_clip{chosen.get('id', idx+1)}"
            f"_{start_ts.replace(':', '-')}.mp4"
        )
        dst = out_dir / out_name

        self._btn_cut.config(state=DISABLED, text="Cutting…")
        self._set_status("Cutting exact 16s clip…", CLR_WARN)

        threading.Thread(
            target=self._cut_worker,
            args=(self._selected_video, start_ts, dst),
            daemon=True,
        ).start()


    def _cut_worker(self, src: Path, start_ts: str, dst: Path):
        try:
            cut_clip_exact(src, start_ts, dst, self._logger)
            self.after(0, lambda: self._on_cut_done(dst))
        except Exception as exc:
            # Surface a concise reason — take the last non-empty line from the error
            lines = [l.strip() for l in str(exc).splitlines() if l.strip()]
            short = lines[-1][:160] if lines else str(exc)[:160]
            self._logger.error(f"Cut failed: {short}")
            self.after(0, lambda: self._btn_cut.config(
                state=NORMAL, text="✂  CUT SELECTED CLIP  (exact 16s)"))
            self.after(0, lambda: self._set_status("Cut failed", CLR_ERROR))


    def _on_cut_done(self, dst: Path):
        self._btn_cut.config(state=NORMAL, text="✂  CUT SELECTED CLIP  (exact 16s)")
        self._set_status(f"Saved: {dst.name}", CLR_SUCCESS)
        self._logger.ok(f"Clip → {dst}")

        self._last_cut_path = dst
        # Enable the "Send to Edit Tab" button so the user can send the clip to Tab 2
        self._btn_send_edit.config(state=NORMAL)
        short = (self._selected_title_for_reup[:70] + "…"
                 if len(self._selected_title_for_reup) > 70
                 else self._selected_title_for_reup)
        self._reup_title_lbl.config(
            text=(f"✓ {short}" if short else "Click a title above, then -> Send to Edit Tab"),
            fg=CLR_FG if short else CLR_DIM,
        )

        self._toast(f"Clip saved: {dst.name}", kind="success")

        if messagebox.askyesno("Clip Ready!", f"Saved:\n{dst}\n\nOpen output folder?"):
            os.startfile(str(dst.parent))

    # ── Reup Render (Tab 2) ──────────────────────────────────────────────────

    def _start_reup(self):
        """Export the currently selected Tab-2 queue item."""
        if self._edit_sel_idx < 0 or self._edit_sel_idx >= len(self._edit_queue):
            messagebox.showwarning("No Selection",
                "Select a clip in the Edit & Export queue first.")
            return

        item  = self._edit_queue[self._edit_sel_idx]
        clip  = item["clip_path"]
        title = item["title"]

        # Sync GUI controls → state dictionary
        item["state"].update(self._read_edit_controls())
        state = item["state"]

        if not clip.exists():
            messagebox.showerror("File Missing", f"Clip not found:\n{clip}")
            return

        out_dir = Path(self._output_var.get())
        video_dir = out_dir / "video"
        video_dir.mkdir(parents=True, exist_ok=True)
        dst = video_dir / (clip.stem + "_reup.mp4")
        # Gemini transcription is always available; WHISPER is optional fallback.
        use_sub = bool(state["subtitles"])

        self._btn_export_one.config(state=DISABLED, text="Rendering…")
        self._btn_export_all.config(state=DISABLED)
        self._set_status("Rendering reup (9:16)…", CLR_WARN)

        # Show progress bar
        self._render_progress_var.set(0.0)
        self._render_progress_lbl.config(text="0%")
        self._render_progress_frame.pack(fill=X, pady=(0, 4), before=self._btn_export_one)

        threading.Thread(
            target=self._reup_worker,
            args=(clip, dst, title, state["color_grade"], use_sub, state),
            daemon=True,
        ).start()

    def _reup_worker(self, clip: Path, dst: Path, title: str,
                     color_grade: bool, use_subtitles: bool,
                     edit_state: Optional[dict] = None):

        def _on_progress(frac: float):
            pct = max(0.0, min(100.0, frac * 100))
            self.after(0, lambda p=pct: (
                self._render_progress_var.set(p),
                self._render_progress_lbl.config(text=f"{p:.0f}%"),
            ))

        try:
            srt = None
            if use_subtitles:
                # Prefer Gemini (no local model, more accurate on short clips).
                # Falls back to Whisper if Gemini fails or API key is missing.
                client, sdk = None, None
                for k in self._get_all_keys():
                    if k.strip():
                        try:
                            client, sdk = build_client(k.strip())
                            break
                        except Exception:
                            pass
                _sub_engine = (edit_state or {}).get("sub_engine", "gemini_fallback")
                _sub_style  = edit_state.get("sub_style", "Normal") if edit_state else "Normal"
                _word_lvl   = True
                _sub_stop   = threading.Event()  # fresh event — analysis stop must not poison export
                if _sub_engine == "whisper":
                    if WHISPER_AVAILABLE:
                        srt = _whisper_transcribe(clip, self._logger, word_level=True, edit_state=edit_state)
                    if srt is None and client and sdk:
                        self._logger.warn("Whisper unavailable or failed — falling back to Gemini")
                        srt = _gemini_transcribe(clip, client, sdk,
                                                 self._logger, _sub_stop,
                                                 word_level=_word_lvl,
                                                 model_name=self._get_model_name(),
                                                 edit_state=edit_state)
                elif _sub_engine == "gemini":
                    if client and sdk:
                        srt = _gemini_transcribe(clip, client, sdk,
                                                 self._logger, _sub_stop,
                                                 word_level=_word_lvl,
                                                 model_name=self._get_model_name(),
                                                 edit_state=edit_state)
                else:  # "gemini_fallback"
                    if client and sdk:
                        srt = _gemini_transcribe(clip, client, sdk,
                                                 self._logger, _sub_stop,
                                                 word_level=_word_lvl,
                                                 model_name=self._get_model_name(),
                                                 edit_state=edit_state)
                    if srt is None and WHISPER_AVAILABLE:
                        srt = _whisper_transcribe(clip, self._logger, word_level=True, edit_state=edit_state)


            render_reup(clip, dst, title, color_grade, srt, self._logger,
                        edit_state=edit_state,
                        render_cfg=self._get_render_cfg(),
                        progress_cb=_on_progress)

            # Organize outputs: move srt and json to separate folders
            out_dir = Path(self._output_var.get())
            if srt and srt.exists():
                srt_dir = out_dir / "srt"
                srt_dir.mkdir(parents=True, exist_ok=True)
                final_srt = srt_dir / (clip.stem + "_reup.srt")
                import shutil
                try:
                    shutil.copy(srt, final_srt)
                    srt.unlink(missing_ok=True)
                except Exception as copy_err:
                    self._logger.warn(f"Could not copy SRT: {copy_err}")

            words_json = clip.with_suffix(".words.json")
            if words_json.exists():
                json_dir = out_dir / "json"
                json_dir.mkdir(parents=True, exist_ok=True)
                final_json = json_dir / (clip.stem + "_reup.json")
                import shutil
                try:
                    shutil.copy(words_json, final_json)
                    words_json.unlink(missing_ok=True)
                except Exception as copy_err:
                    self._logger.warn(f"Could not copy JSON: {copy_err}")

            self.after(0, lambda: self._on_reup_done(dst))
        except Exception as exc:
            lines = [l.strip() for l in str(exc).splitlines() if l.strip()]
            short = " | ".join(lines[-6:])[:400] if lines else str(exc)[:400]
            self._logger.error(f"Reup failed: {short}")
            self.after(0, lambda: (
                self._btn_export_one.config(state=NORMAL, text="📱  Export Current"),
                self._btn_export_all.config(state=NORMAL),
                self._render_progress_frame.pack_forget(),
                self._set_status("Reup render failed", CLR_ERROR),
            ))

    def _on_reup_done(self, dst: Path):
        self._btn_export_one.config(state=NORMAL, text="📱  Export Current")
        self._btn_export_all.config(state=NORMAL)
        self._render_progress_frame.pack_forget()  # hide progress bar
        self._set_status(f"Reup saved: {dst.name}", CLR_SUCCESS)
        self._toast(f"Export done: {dst.name}", kind="success", duration=5000)
        if messagebox.askyesno("Reup Ready!",
                f"Portrait 9:16 video saved:\n{dst}\n\nOpen output folder?"):
            os.startfile(str(dst.parent))

    # ── Stop ────────────────────────────────────────────────────────────────

    def _stop_work(self):
        self._stop.set()
        self._set_status("Stopping…", CLR_WARN)
        self._btn_stop.config(state=DISABLED)
        self._btn_retry.config(state=DISABLED)
        self._logger.warn("Stop requested — all threads will finish current step and exit.")
        self._toast("Stop requested — finishing current steps…", kind="warning")


    # ── Retry Errors ────────────────────────────────────────────────────────

    def _retry_errors(self):
        """Re-run analysis only for videos that previously failed."""
        keys = self._get_all_keys()
        if not keys:
            messagebox.showerror("Missing", "Please enter at least one API key.")
            return

        # Collect the failed videos
        failed = [
            p for p in self._video_files
            if self._video_results.get(str(p), {}).get("status") == ST_ERROR
        ]
        if not failed:
            return

        self._stop.clear()

        # Reset each failed video to queued in state + queue display
        for p in failed:
            self._video_results[str(p)] = {"status": ST_QUEUED, "candidates": []}
            self._queue_update(p, ST_QUEUED, "Queued")

        n = len(failed)
        max_concurrent = min(3, n)
        sem = threading.Semaphore(max_concurrent)

        self._btn_analyze.config(state=DISABLED, text="ANALYZING…", bg="#4f4f4f")
        self._btn_stop.config(state=NORMAL)
        self._btn_retry.config(state=DISABLED)
        self._prog_var.set(0)
        self._set_status(
            f"Retrying {n} failed video(s)  —  up to {max_concurrent} at a time…",
            CLR_WARN,
        )
        self._logger.header("=" * 50)
        self._logger.header(f"  Retry: {n} failed video(s), {len(keys)} key(s)")
        self._logger.header("=" * 50)

        self._active_threads = []
        rotator = KeyRotator(keys)   # shared round-robin distributor
        for video_path in failed:
            t = threading.Thread(
                target=self._analyze_one_video,
                args=(video_path, rotator, sem),
                daemon=True,
            )
            self._active_threads.append(t)
            t.start()


    # ── Update Checking ──────────────────────────────────────────────────────

    def _check_for_updates(self):
        """Fetch version info in a background thread and show banner on mismatch."""
        try:
            import requests
            r = requests.get(UPDATE_CHECK_URL, timeout=4)
            if r.status_code == 200:
                data = r.json()
                latest = data.get("latest_version")
                download_url = data.get("download_url")
                # Strip leading 'v' if present for comparison
                local_ver = APP_VERSION.lstrip("v")
                latest_ver = latest.lstrip("v") if latest else ""
                if latest_ver and latest_ver != local_ver:
                    self.after(0, lambda: self._show_update_banner(latest, download_url))
        except Exception:
            pass  # fail silently to keep startup uninterrupted

    def _show_update_banner(self, latest: str, url: str):
        """Build and slide in a beautiful update notification banner."""
        banner = self._update_banner
        banner.pack(side=TOP, fill=X, padx=20, pady=(0, 8))

        # Vibrant alert background styling
        lbl = ttk.Label(
            banner, text=f"🔔  A new version ({latest}) is available!",
            foreground="#fbbf24", font=("Segoe UI", 9, "bold"),
            background=CLR_PANEL,
        )
        lbl.pack(side=LEFT, padx=12, pady=6)

        btn = tk.Button(
            banner, text="Download Update", bg="#d97706", fg="white",
            font=("Segoe UI", 8, "bold"), relief=FLAT, padx=10, pady=2,
            activebackground="#b45309", cursor="hand2",
            command=lambda: os.startfile(url),
        )
        btn.pack(side=LEFT, padx=10)

        dismiss = tk.Button(
            banner, text="✕", bg=CLR_PANEL, fg=CLR_DIM,
            font=("Segoe UI", 9, "bold"), relief=FLAT, cursor="hand2",
            activebackground=CLR_PANEL, activeforeground=CLR_FG,
            command=banner.pack_forget,
        )
        dismiss.pack(side=RIGHT, padx=12)

    # ── Drag and Drop + 16s Clip Import ──────────────────────────────────────

    def _setup_drag_and_drop(self):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes

            WM_DROPFILES = 0x0233
            GWL_WNDPROC = -4

            hwnd = self.winfo_id()
            ctypes.windll.shell32.DragAcceptFiles(hwnd, True)

            # Explicitly declare ctypes for Shell32 DragQueryFileW and DragFinish to avoid pointer truncating
            ctypes.windll.shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]
            ctypes.windll.shell32.DragQueryFileW.restype = ctypes.c_uint
            ctypes.windll.shell32.DragFinish.argtypes = [ctypes.c_void_p]
            ctypes.windll.shell32.DragFinish.restype = None

            if ctypes.sizeof(ctypes.c_void_p) == 8:
                SetWindowLongPtr = ctypes.windll.user32.SetWindowLongPtrW
                GetWindowLongPtr = ctypes.windll.user32.GetWindowLongPtrW
                WNDPROC_TYPE = ctypes.WINFUNCTYPE(
                    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p
                )
            else:
                SetWindowLongPtr = ctypes.windll.user32.SetWindowLongW
                GetWindowLongPtr = ctypes.windll.user32.GetWindowLongW
                WNDPROC_TYPE = ctypes.WINFUNCTYPE(
                    ctypes.c_int32, ctypes.c_int32, ctypes.c_uint, ctypes.c_int32, ctypes.c_int32
                )

            SetWindowLongPtr.restype = ctypes.c_void_p
            SetWindowLongPtr.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
            GetWindowLongPtr.restype = ctypes.c_void_p
            GetWindowLongPtr.argtypes = [ctypes.c_void_p, ctypes.c_int]

            CallWindowProc = ctypes.windll.user32.CallWindowProcW
            CallWindowProc.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
            CallWindowProc.restype = ctypes.c_void_p

            self._old_wndproc = GetWindowLongPtr(hwnd, GWL_WNDPROC)

            def wndproc(hwnd_val, msg, wparam, lparam):
                if msg == WM_DROPFILES:
                    try:
                        hdrop = wparam
                        num_files = ctypes.windll.shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
                        files = []
                        for i in range(num_files):
                            buf_len = ctypes.windll.shell32.DragQueryFileW(hdrop, i, None, 0) + 1
                            buf = ctypes.create_unicode_buffer(buf_len)
                            ctypes.windll.shell32.DragQueryFileW(hdrop, i, buf, buf_len)
                            files.append(Path(buf.value))
                        ctypes.windll.shell32.DragFinish(hdrop)
                        self.after(0, lambda: self._on_files_dropped(files))
                    except Exception as e:
                        print(f"Error handling dropped files: {e}")
                    return 0
                return CallWindowProc(self._old_wndproc, hwnd_val, msg, wparam, lparam)

            self._wndproc_cb = WNDPROC_TYPE(wndproc)
            SetWindowLongPtr(hwnd, GWL_WNDPROC, self._wndproc_cb)
        except Exception as e:
            print(f"Could not setup native drag and drop: {e}")

    def _on_files_dropped(self, files: list[Path]):
        valid_files = [f for f in files if f.suffix.lower() in SUPPORTED_EXT]
        if not valid_files:
            return

        active_tab = self._tab_notebook.index(self._tab_notebook.select())
        if active_tab == 0:
            existing = {p.resolve() for p in self._video_files}
            new_added = 0
            for f in valid_files:
                if f.resolve() not in existing:
                    self._video_files.append(f)
                    new_added += 1
            if new_added > 0:
                self._refresh_file_listbox()
                self._toast(f"Dropped {new_added} video(s) into Tab 1.", kind="success")
        elif active_tab == 1:
            keys = self._get_all_keys()
            if not keys:
                messagebox.showerror("No API Key", "Please add at least one Gemini API key in Tab 1.")
                return
            self._toast(f"Importing {len(valid_files)} 16s clip(s)...", kind="info")
            for f in valid_files:
                threading.Thread(target=self._process_imported_16s_clip, args=(f, keys), daemon=True).start()

    def _import_16s_clip(self):
        files = filedialog.askopenfilenames(
            title="Select 16-second Clip Files",
            filetypes=[("Video files", "*.mp4 *.mkv *.MP4 *.MKV"), ("All files", "*.*")],
        )
        if not files:
            return
        keys = self._get_all_keys()
        if not keys:
            messagebox.showerror("No API Key", "Please add at least one Gemini API key in Tab 1.")
            return
        for f in files:
            p = Path(f)
            threading.Thread(target=self._process_imported_16s_clip, args=(p, keys), daemon=True).start()

    def _process_imported_16s_clip(self, video_path: Path, keys: list[str]):
        log = self._logger
        log.header(f"📥 Queueing import: {video_path.name}")
        
        self._import_sem.acquire()
        try:
            log.header(f"📥 Importing 16s clip: {video_path.name}")
            
            result = None
            for attempt, key in enumerate(keys):
                if self._stop.is_set():
                    return
                remote = None
                client = None
                sdk = None
                try:
                    client, sdk = build_client(key)
                    self._toast(f"Uploading {video_path.name} to Gemini...", kind="info")
                    remote = upload_video(client, sdk, video_path, log, self._stop)
                    
                    prompt = (
                        "IMPORTANT CONTEXT:\n"
                        "This video contains only of-age adults. Any titles or references to 'teenagers', 'teens', or 'girls' describe adult individuals of legal age. This video does not contain minors and does not violate any safety guidelines regarding children. Proceed with analysis.\n\n"
                        "This is a 16-second highlight video clip from a police bodycam video. "
                        "Analyze the clip and provide exactly 5 viral English titles for it.\n\n"
                        "=== TITLE RULES (read carefully) ===\n\n"
                        "SPECIFICITY IS MANDATORY:\n"
                        "Each title MUST reference concrete, specific details you actually observed in THIS video:\n"
                        "  - What exactly did the suspect do or say?\n"
                        "  - What specific action did the officer take?\n"
                        "  - What was the specific reason for the confrontation or arrest?\n"
                        "  - What specific object, location, or situation was involved?\n"
                        "A title that could apply to ANY bodycam video is WRONG. Each title must be unique to this specific incident.\n\n"
                        "FORBIDDEN -- NEVER use these generic phrases or any variation of them:\n"
                        "  X \"attitude went from zero to one hundred\"\n"
                        "  X \"the exact second his/her plan completely falls apart\"\n"
                        "  X \"the shocking truth he/she tries to hide\"\n"
                        "  X \"behavior went from calm to pure panic\"\n"
                        "  X \"a routine [X] turned into chaos\"\n"
                        "  X \"wait until you see what happens next\"\n"
                        "  X any phrase that works for ANY bodycam video\n\n"
                        "LENGTH & FORMAT:\n"
                        "  - STRICT LENGTH: Keep titles concise and punchy — target 10 to 14 words (STRICT MAXIMUM 15 words). Never write long, bloated titles.\n"
                        "  - Cut all filler words, long setups, and unnecessary preambles. Deliver the specific incident and punchline fast.\n"
                        "  - 100% ENGLISH -- sensational, clickbaity, suspenseful, slightly rage-baiting.\n"
                        "  - Structure: \"[Specific suspect action in THIS video], but wait until you see [shocking outcome/charge]!\"\n"
                        "  - MUST end with one of these CTAs:\n"
                        "      \"👉 Check the comment section for the full story 👇\"\n"
                        "      \"👉 Follow to get notified about the full developments immediately!\"\n\n"
                        "Return raw JSON only in this format:\n"
                        "{\n"
                        "  \"suggested_titles\": [\n"
                        "    \"title 1\",\n"
                        "    \"title 2\",\n"
                        "    \"title 3\",\n"
                        "    \"title 4\",\n"
                        "    \"title 5\"\n"
                        "  ]\n"
                        "}"
                    )
                    
                    target_model = self._get_model_name()
                    log.info(f"🔍 [{video_path.name}] Generating titles via {target_model}...")
                    self._toast(f"Generating titles for {video_path.name}...", kind="info")
                    if sdk == "new":
                        from google.genai import types as _gt
                        safety = [
                            _gt.SafetySetting(
                                category=_gt.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                                threshold=_gt.HarmBlockThreshold.BLOCK_NONE,
                            ),
                            _gt.SafetySetting(
                                category=_gt.HarmCategory.HARM_CATEGORY_HARASSMENT,
                                threshold=_gt.HarmBlockThreshold.BLOCK_NONE,
                            ),
                            _gt.SafetySetting(
                                category=_gt.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                                threshold=_gt.HarmBlockThreshold.BLOCK_NONE,
                            ),
                            _gt.SafetySetting(
                                category=_gt.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                                threshold=_gt.HarmBlockThreshold.BLOCK_NONE,
                            ),
                        ]
                        resp = client.models.generate_content(
                            model=target_model,
                            contents=[remote, prompt],
                            config=_gt.GenerateContentConfig(
                                temperature=0.4, max_output_tokens=1024,
                                safety_settings=safety,
                            ),
                        )
                        raw = resp.text
                    else:
                        safety_old = [
                            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                        ]
                        model = client.GenerativeModel(
                            target_model,
                            generation_config={"temperature": 0.4, "max_output_tokens": 1024},
                        )
                        raw = model.generate_content(
                            [remote, prompt],
                            safety_settings=safety_old,
                        ).text
                    
                    raw = (raw or "").strip()
                    parsed = extract_json(raw)
                    if parsed and parsed.get("suggested_titles"):
                        # Strip any preamble Gemini added inside the title strings
                        result = [_clean_title_str(t) for t in parsed.get("suggested_titles") if t]
                        result = [t for t in result if t]  # drop empties after cleanup
                        break
                    else:
                        snippet = (raw[:300] if raw else "None")
                        raise ValueError(f"No suggested_titles in Gemini response:\n{snippet}")
                except Exception as e:
                    log.warn(f"[{video_path.name}] Error with key #{attempt+1}: {e}")
                    if attempt == len(keys) - 1:
                        log.error(f"[{video_path.name}] Failed to generate titles: {e}")
                        self.after(0, lambda: self._toast(f"Failed to generate titles for {video_path.name}.", kind="error"))
                        return
                finally:
                    if remote and client and sdk:
                        try:
                            delete_remote(client, sdk, remote, log)
                        except Exception:
                            pass

            if result:
                def _add_to_queue():
                    first_title = result[0]
                    item = {
                        "clip_path": video_path,
                        "title":     first_title,
                        "suggested_titles": result,
                        "state":     _default_edit_state(),
                    }
                    # Apply global template if Sync All is active
                    if getattr(self, "_edit_sync_all", None) and self._edit_sync_all.get():
                        item["state"].update(self._global_edit_state)
                    self._edit_queue.append(item)
                    self._edit_listbox.insert(END, video_path.stem)
                    self._update_queue_count_label()

                    # Automatically select the newly added item
                    idx = len(self._edit_queue) - 1
                    self._edit_listbox.selection_clear(0, END)
                    self._edit_listbox.selection_set(idx)
                    self._edit_sel_idx = idx
                    
                    self._btn_export_one.config(state=NORMAL)
                    self._btn_export_all.config(state=NORMAL)
                    self._tab_notebook.select(1)  # Switch to Tab 2
                    self._on_edit_select()
                    log.ok(f"📥 Successfully imported {video_path.name} to Edit Queue.")
                    self._toast(f"Imported {video_path.name}!", kind="success")

                self.after(0, _add_to_queue)
        finally:
            self._import_sem.release()

    def _refresh_edit_suggestions_ui(self):
        for widget in self._edit_suggestions_frame.winfo_children():
            widget.destroy()

        if self._edit_sel_idx < 0 or self._edit_sel_idx >= len(self._edit_queue):
            return

        item = self._edit_queue[self._edit_sel_idx]
        suggested = item.get("suggested_titles", [])
        if not suggested:
            return

        tk.Label(
            self._edit_suggestions_frame, text="Suggested Titles:",
            bg=CLR_SURFACE, fg=CLR_DIM, font=("Segoe UI", 8, "bold")
        ).pack(anchor=W, pady=(2, 2))

        for idx, t in enumerate(suggested):
            def _set_title(title_text=t):
                self._edit_title_text_var.set(title_text)

            btn = tk.Button(
                self._edit_suggestions_frame,
                text=f"{idx+1}. {t}",
                anchor=W, justify=LEFT, bg=CLR_INPUT_BG, fg=CLR_FG,
                activebackground=CLR_SURFACE, activeforeground=CLR_FG,
                font=("Segoe UI", 8), relief=FLAT, bd=0,
                padx=6, pady=4, cursor="hand2", wraplength=320
            )
            btn.config(command=_set_title)
            btn.pack(fill=X, pady=1)


