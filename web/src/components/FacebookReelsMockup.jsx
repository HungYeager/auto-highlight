import React from 'react';

/**
 * Deep Module: FacebookReelsMockup.jsx
 * Renders a non-interactive (pointer-events-none) Facebook Reels / Watch Mobile UI overlay
 * on top of the 9:16 preview stage (324x576) so editors can align CTA text boxes and
 * pointing hand emojis ("check the comments to watch part 2" + "👉") directly at the
 * mobile Comment button. Never included in video export.
 */
export default function FacebookReelsMockup({
  enabled = false,
  mode = 'vector', // 'vector' | 'image'
  opacity = 85,
  customImageUrl = '',
  showTargetGuide = true,
}) {
  if (!enabled) return null;

  const alpha = Math.max(0.1, Math.min(1, opacity / 100));

  if (mode === 'image') {
    return (
      <div
        className="absolute inset-0 pointer-events-none select-none z-40 overflow-hidden rounded-2xl"
        style={{ opacity: alpha }}
      >
        <img
          src={customImageUrl || '/fb_reels_reference.jpg'}
          alt="Facebook UI Reference"
          draggable={false}
          className="w-full h-full object-fill pointer-events-none"
        />
        {showTargetGuide && (
          <div
            className="absolute right-[7px] w-9 h-9 rounded-full border-2 border-dashed border-amber-400/90 shadow-[0_0_12px_rgba(251,191,36,0.8)] flex items-center justify-center"
            style={{ top: '67.8%', transform: 'translateY(-50%)' }}
          />
        )}
      </div>
    );
  }

  return (
    <div
      className="absolute inset-0 pointer-events-none select-none z-40 overflow-hidden rounded-2xl font-sans text-white"
      style={{ opacity: alpha }}
    >
      {/* Top & Bottom subtle dark gradients matching Facebook Reels mobile player */}
      <div
        className="absolute inset-x-0 top-0 h-20 pointer-events-none"
        style={{
          background: 'linear-gradient(180deg, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0) 100%)',
        }}
      />
      <div
        className="absolute inset-x-0 bottom-0 h-56 pointer-events-none"
        style={{
          background:
            'linear-gradient(0deg, rgba(0,0,0,0.92) 0%, rgba(0,0,0,0.72) 55%, rgba(0,0,0,0) 100%)',
        }}
      />

      {/* 1. iOS Status Bar */}
      <div className="absolute top-1.5 inset-x-3 flex items-center justify-between text-[9px] font-semibold tracking-tight drop-shadow">
        <div className="flex items-center gap-1">
          <span>09:59</span>
          <span className="text-[7px] text-white/80 font-normal ml-0.5">◄ Zalo</span>
        </div>
        <div className="flex items-center gap-1">
          {/* Signal bars */}
          <svg className="w-3 h-2.5 fill-current" viewBox="0 0 16 12">
            <rect x="1" y="8" width="2" height="3" rx="0.5" />
            <rect x="4.5" y="6" width="2" height="5" rx="0.5" />
            <rect x="8" y="3.5" width="2" height="7.5" rx="0.5" />
            <rect x="11.5" y="1" width="2" height="10" rx="0.5" opacity="0.4" />
          </svg>
          {/* WiFi */}
          <svg className="w-3 h-2.5 fill-current" viewBox="0 0 16 12">
            <path d="M8 9.5a1.5 1.5 0 100 3 1.5 1.5 0 000-3zm-3.6-1.8a5.5 5.5 0 017.2 0l1.1-1.1a7 7 0 00-9.4 0l1.1 1.1zm-2.5-2.5a9 9 0 0112.2 0l1.1-1.1a10.5 10.5 0 00-14.4 0l1.1 1.1z" />
          </svg>
          {/* Battery */}
          <span className="bg-white text-black text-[7px] font-extrabold px-1 py-0.2 rounded-[3px] leading-none">
            93
          </span>
        </div>
      </div>

      {/* 2. Facebook Reels Top Bar (< , Search, More) */}
      <div className="absolute top-[34px] inset-x-3 flex items-center justify-between">
        <svg className="w-4 h-4 stroke-white fill-none drop-shadow" strokeWidth="2.4" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        <div className="flex items-center gap-2.5">
          <svg className="w-4 h-4 stroke-white fill-none drop-shadow" strokeWidth="2.2" viewBox="0 0 24 24">
            <circle cx="11" cy="11" r="7" />
            <path strokeLinecap="round" d="M20 20l-3.5-3.5" />
          </svg>
          <div className="w-4 h-4 rounded-full border-[1.8px] border-white flex items-center justify-center gap-0.5 drop-shadow">
            <span className="w-0.5 h-0.5 bg-white rounded-full" />
            <span className="w-0.5 h-0.5 bg-white rounded-full" />
            <span className="w-0.5 h-0.5 bg-white rounded-full" />
          </div>
        </div>
      </div>

      {/* 3. Right Side Action Column (Like, Comment, Share, Save, More) */}
      {/* Like Button (~60.2% Y) */}
      <div
        className="absolute right-2.5 flex flex-col items-center gap-0.5"
        style={{ top: '60.2%', transform: 'translateY(-50%)' }}
      >
        <svg className="w-5 h-5 stroke-white fill-none drop-shadow" strokeWidth="2" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3zM7 22H4a2 2 0 01-2-2v-7a2 2 0 012-2h3"
          />
        </svg>
        <span className="text-[8px] font-semibold drop-shadow">3</span>
      </div>

      {/* 💬 COMMENT BUTTON (~67.8% Y = ~1300px in 1080x1920) — Target for CTA "check the comments" + "👉" */}
      <div
        className="absolute right-2.5 flex flex-col items-center"
        style={{ top: '67.8%', transform: 'translateY(-50%)' }}
      >
        <div
          className={`relative w-7 h-7 rounded-full flex items-center justify-center ${
            showTargetGuide
              ? 'ring-2 ring-amber-400 bg-amber-500/20 shadow-[0_0_12px_rgba(251,191,36,0.9)]'
              : ''
          }`}
        >
          {showTargetGuide && (
            <span className="absolute -top-3.5 right-0 bg-amber-400 text-black text-[6.5px] font-extrabold px-1 rounded shadow whitespace-nowrap">
              🎯 Nút Comment
            </span>
          )}
          <svg className="w-5 h-5 stroke-white fill-none drop-shadow" strokeWidth="2.2" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.38 8.38 0 01-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.38 8.38 0 013.8-.9h.5a8.48 8.48 0 018 8v.5z"
            />
          </svg>
        </div>
      </div>

      {/* Share Button (~74.5% Y) */}
      <div
        className="absolute right-2.5 flex flex-col items-center"
        style={{ top: '74.5%', transform: 'translateY(-50%)' }}
      >
        <svg className="w-5 h-5 stroke-white fill-none drop-shadow" strokeWidth="2" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 14l5-5-5-5" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M20 9H9.5A5.5 5.5 0 004 14.5v0A5.5 5.5 0 009.5 20H13" />
        </svg>
      </div>

      {/* Save / Bookmark Button (~81.2% Y) */}
      <div
        className="absolute right-2.5 flex flex-col items-center"
        style={{ top: '81.2%', transform: 'translateY(-50%)' }}
      >
        <svg className="w-4 h-4 stroke-white fill-none drop-shadow" strokeWidth="2" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z" />
        </svg>
      </div>

      {/* Three Dots Menu (~87.5% Y) */}
      <div
        className="absolute right-3 flex items-center gap-0.5"
        style={{ top: '87.5%', transform: 'translateY(-50%)' }}
      >
        <span className="w-1 h-1 bg-white rounded-full" />
        <span className="w-1 h-1 bg-white rounded-full" />
        <span className="w-1 h-1 bg-white rounded-full" />
      </div>

      {/* 4. Bottom Left Page Info, Caption & Search Pill */}
      <div className="absolute left-2.5 right-11" style={{ top: '72.2%' }}>
        {/* Page Avatar + Name + Follow */}
        <div className="flex items-center gap-1.5 mb-1.5">
          <div className="w-6 h-6 rounded-full bg-gradient-to-br from-blue-600 to-indigo-900 border border-white/60 flex items-center justify-center text-[7px] font-bold shrink-0 shadow">
            👮
          </div>
          <div className="leading-tight min-w-0">
            <div className="flex items-center gap-1">
              <span className="text-[8.5px] font-bold truncate">Midnight Road Files</span>
              <span className="w-2.5 h-2.5 rounded-full bg-white text-black text-[6px] flex items-center justify-center font-bold">
                ✓
              </span>
              <span className="border border-white/70 bg-black/30 rounded px-1.5 py-0.2 text-[7.5px] font-semibold ml-0.5">
                Theo dõi
              </span>
            </div>
            <div className="text-[7px] text-gray-300">14 giờ trước</div>
          </div>
        </div>

        {/* Post Caption */}
        <p className="text-[8px] text-white/95 leading-snug truncate mb-0.5">
          Bằng chứng bỏ bê trẻ em bên trong x... <span className="text-gray-300 font-semibold">xem thêm</span>
        </p>
        <p className="text-[7px] text-gray-400 mb-2">Hiển thị bản gốc</p>

        {/* Search Suggestion Pill */}
        <div className="w-full bg-white/15 backdrop-blur-sm rounded-full px-2.5 py-1 flex items-center gap-1.5 text-[7.5px] text-gray-100">
          <svg className="w-2.5 h-2.5 stroke-current fill-none shrink-0" strokeWidth="2.2" viewBox="0 0 24 24">
            <circle cx="11" cy="11" r="7" />
            <path strokeLinecap="round" d="M20 20l-3.5-3.5" />
          </svg>
          <span className="truncate font-medium">Disturbing RV discovery part 2</span>
        </div>
      </div>

      {/* 5. Bottom Comment Input Bar ("Bình luận...") */}
      <div className="absolute bottom-3 inset-x-2.5 bg-white/15 backdrop-blur-md rounded-full px-3 py-1.5 flex items-center justify-between text-[8px] text-gray-300">
        <span>Bình luận</span>
        <div className="flex items-center gap-1.5 text-white/90">
          <span className="text-[10px] leading-none">😊</span>
          <span className="border border-white/80 rounded px-0.5 text-[6px] font-extrabold leading-tight">
            GIF
          </span>
        </div>
      </div>

      {/* iOS Home Bar */}
      <div className="absolute bottom-1 left-1/2 -translate-x-1/2 w-24 h-1 bg-white/90 rounded-full" />
    </div>
  );
}

