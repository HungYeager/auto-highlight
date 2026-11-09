import React, { useState } from 'react';
import {
  Film, Download, Trash2, Plus, Sparkles, CheckCircle2, AlertCircle,
  RefreshCw, Terminal, FolderOpen, Scissors, Square, Settings,
  Shield, Droplets, Zap, AlignLeft, AlignCenter, AlignRight,
  FlipHorizontal, FlipVertical, Image, Move, MessageSquare, Key,
  ChevronRight, Type, Layers, Palette, Copy, Eye, ChevronDown, Send, RotateCw,
  Volume2, VolumeX, Music, Crop, Mic, Loader2, Youtube, ExternalLink, Link2, X,
  Play, Clipboard, Search
} from 'lucide-react';

export default function YouTubeModal(props) {
  const {
    showYtModal, setShowYtModal, ytCookiesStatus, handleQuickPasteCookiesFromClipboard,
    setShowCookiePasteModal, ytCookieFileInputRef, handleDeleteCookies, handleUploadCookieFile,
    showCookieGuide, setShowCookieGuide, ytBatchTab, setYtBatchTab, ytHistoryList,
    ytCodePrefix, handleUpdatePrefix, parseYtUrls, ytUrl, setYtUrl, ytDupCheck,
    copyAssetCode, ytCopiedAssetCode, ytMode, setYtMode,
    ytStatus, handleAnalyzeYouTube, ytBatchText,
    setYtBatchText, ytBatchBusy, handleBatchAddYouTube, ytHistorySearch, setYtHistorySearch,
    ytHistoryMeta, fetchYtHistory, ytHistoryLoading, ytCopiedCode, setYtCopiedCode,
    ytError, ytInfo, ytCandidates, ytDownloadAllBusy, handleDownloadAllYtCandidates,
    ytDownloadedSet, ytDownloadingMap, ytDownloadErrors, handleDownloadYtCandidate,
    showCookiePasteModal, cookieInputText, setCookieInputText, handleSaveCookieText
  } = props;
  const [batchLookupCopiedTag, setBatchLookupCopiedTag] = useState('');
    if (!showYtModal) return null;
    return (
      <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-200">
        <div className="bg-[#0f111c] border border-gray-800 rounded-2xl w-full max-w-3xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
          {/* Header */}
          <div className="px-5 py-4 border-b border-gray-800/80 flex items-center justify-between bg-gradient-to-r from-red-950/30 to-indigo-950/20">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-xl bg-red-600/20 border border-red-500/30 flex items-center justify-center">
                <Youtube className="w-4 h-4 text-red-500" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  Phân Tích Video YouTube Trực Tiếp
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">Gemini Visual AI</span>
                </h3>
                <p className="text-[11px] text-gray-400 mt-0.5">
                  Không cần tải video về máy — Gemini soi trực tiếp hình ảnh &amp; âm thanh trên Google Cloud, chỉ tải lát cắt hay vào Studio
                </p>
              </div>
            </div>
            <button
              onClick={() => setShowYtModal(false)}
              className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800/60 transition"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Body */}
          <div className="p-5 flex-1 overflow-y-auto space-y-4">
            {/* Cookie Status & Bypass Section */}
            {ytCookiesStatus.has_cookies ? (
              <div className="px-3.5 py-2.5 bg-emerald-950/30 border border-emerald-800/40 rounded-xl flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  <span className="text-emerald-300 font-semibold">Cookie YouTube: Đã kết nối</span>
                  <span className="text-[11px] text-gray-400">({ytCookiesStatus.filename || 'cookies.txt'} · {(ytCookiesStatus.size / 1024).toFixed(1)} KB)</span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-900/50 text-emerald-200 border border-emerald-700/50">Tải được video 18+ &amp; chống bot</span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleQuickPasteCookiesFromClipboard}
                    className="text-[11px] text-emerald-400 hover:text-emerald-200 underline font-semibold flex items-center gap-1"
                    title="Dán đè Cookie mới trực tiếp từ Clipboard"
                  >
                    <Clipboard className="w-3 h-3" />
                    <span>Dán mới từ Clipboard</span>
                  </button>
                  <span className="text-gray-600">|</span>
                  <button
                    onClick={() => ytCookieFileInputRef.current?.click()}
                    className="text-[11px] text-indigo-400 hover:text-indigo-300 underline"
                    title="Cập nhật file cookie mới"
                  >
                    Đổi file
                  </button>
                  <span className="text-gray-600">|</span>
                  <button
                    onClick={handleDeleteCookies}
                    className="text-[11px] text-red-400 hover:text-red-300"
                    title="Xóa cookies đã lưu"
                  >
                    Xóa
                  </button>
                </div>
              </div>
            ) : (
              <div className="p-3 bg-amber-950/25 border border-amber-800/40 rounded-xl space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-start gap-2">
                    <span className="text-amber-400 text-sm mt-0.5">🍪</span>
                    <div>
                      <p className="text-xs font-bold text-amber-200">
                        Chưa nạp Cookie YouTube (Khuyên dùng để chống chặn bot &amp; tải video 18+)
                      </p>
                      <p className="text-[11px] text-amber-300/80 mt-0.5">
                        YouTube thường bắt xác minh bot hoặc đăng nhập với các video phóng sự, bodycam nhạy cảm. Nạp cookie giúp tải mọi video 100% mượt mà.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2 pt-0.5">
                  <button
                    type="button"
                    onClick={handleQuickPasteCookiesFromClipboard}
                    className="px-3 py-1.5 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-black text-xs font-bold rounded-lg flex items-center gap-1.5 transition shadow"
                    title="Dán ngay cookie bạn vừa copy từ trình duyệt mà không cần chỉnh sửa file"
                  >
                    <Clipboard className="w-3.5 h-3.5" />
                    <span>📋 Dán nhanh Cookie từ Clipboard (1-Click)</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowCookiePasteModal(true)}
                    className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-200 text-xs font-semibold rounded-lg transition"
                  >
                    📝 Mở ô Dán tay
                  </button>
                  <button
                    type="button"
                    onClick={() => ytCookieFileInputRef.current?.click()}
                    className="px-2.5 py-1.5 bg-gray-900 hover:bg-gray-800 text-gray-400 text-xs rounded-lg transition"
                  >
                    <span>📂 Nạp file .txt</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowCookieGuide(prev => !prev)}
                    className="text-xs text-amber-400 hover:text-amber-300 underline ml-auto"
                  >
                    {showCookieGuide ? 'Ẩn hướng dẫn ▲' : '❓ Cách lấy cookie (30s) ▼'}
                  </button>
                </div>

                {showCookieGuide && (
                  <div className="mt-2 pt-2 border-t border-amber-800/40 text-[11px] text-gray-300 space-y-1.5 bg-black/40 p-3 rounded-lg">
                    <p className="font-bold text-amber-300">3 bước đơn giản để lấy cookie:</p>
                    <ol className="list-decimal list-inside space-y-1 text-gray-300">
                      <li>
                        Cài tiện ích Chrome/Edge:&nbsp;
                        <a
                          href="https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc"
                          target="_blank"
                          rel="noreferrer"
                          className="text-indigo-400 hover:text-indigo-300 underline font-semibold"
                        >
                          Get cookies.txt LOCALLY (Bấm vào đây để mở trang cài đặt)
                        </a>
                      </li>
                      <li>Mở tab <span className="text-white font-mono">youtube.com</span> (đảm bảo đang đăng nhập).</li>
                      <li>Bấm vào biểu tượng tiện ích ở góc trình duyệt ➔ Chọn <strong>Copy</strong> (hoặc Export).</li>
                      <li>Quay lại đây bấm nút <strong>"📋 Dán nhanh Cookie từ Clipboard"</strong> ➔ Xong ngay, không cần sửa file!</li>
                    </ol>
                    <p className="text-[10px] text-gray-400 italic mt-1">
                      * File cookies được lưu cục bộ trên máy tính của bạn, hoàn toàn an toàn và bảo mật.
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Sub Navigation: Single vs Batch vs History/Lookup */}
            <div className="flex border-b border-gray-800 bg-black/30 rounded-xl p-1 gap-1">
              <button
                type="button"
                onClick={() => setYtBatchTab('single')}
                className={`flex-1 py-1.5 rounded-lg text-xs font-bold transition flex items-center justify-center gap-1.5 ${
                  ytBatchTab === 'single'
                    ? 'bg-red-950/60 text-white border border-red-800/60 shadow-sm'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                <Youtube className="w-3.5 h-3.5 text-red-500" />
                <span>Phân Tích 1 Video</span>
              </button>
              <button
                type="button"
                onClick={() => setYtBatchTab('batch')}
                className={`flex-1 py-1.5 rounded-lg text-xs font-bold transition flex items-center justify-center gap-1.5 ${
                  ytBatchTab === 'batch'
                    ? 'bg-indigo-950/60 text-white border border-indigo-800/60 shadow-sm'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                <Layers className="w-3.5 h-3.5 text-indigo-400" />
                <span>Nhập List Hàng Loạt</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setYtBatchTab('history');
                  fetchYtHistory('');
                }}
                className={`flex-1 py-1.5 rounded-lg text-xs font-bold transition flex items-center justify-center gap-1.5 ${
                  ytBatchTab === 'history'
                    ? 'bg-purple-950/70 text-white border border-purple-800/60 shadow-sm'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                <Search className="w-3.5 h-3.5 text-purple-400" />
                <span>🏷️ Lịch Sử &amp; Tra Cứu Mã</span>
              </button>
            </div>

            {ytBatchTab === 'batch' ? (
              /* ── Batch YouTube Import Tab ── */
              <div className="space-y-4 pt-1 animate-in fade-in duration-150">
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-gray-200 flex items-center gap-1.5">
                      <span>Dán danh sách link YouTube (Mỗi dòng 1 link hoặc cách nhau bằng dấu phẩy)</span>
                    </label>
                    <div className="flex items-center gap-2.5">
                      <div className="flex items-center gap-1.5 bg-black/40 border border-gray-700/80 px-2 py-0.5 rounded-lg">
                        <span className="text-[10px] text-gray-400 font-medium">Tiền tố mã:</span>
                        <input
                          type="text"
                          value={ytCodePrefix}
                          onChange={e => handleUpdatePrefix(e.target.value)}
                          placeholder="COP"
                          maxLength={8}
                          className="w-14 bg-black/60 border border-gray-600 rounded px-1.5 py-0.5 text-center font-mono font-bold text-indigo-300 text-[11px] uppercase focus:outline-none focus:border-indigo-400 transition"
                          title="Tùy chỉnh tiền tố mã định danh cho toàn bộ danh sách nhập (VD: COP, VID, CAM...)"
                        />
                      </div>
                      <button
                        type="button"
                        onClick={async () => {
                          try {
                            const text = await navigator.clipboard.readText();
                            if (text) {
                              setYtBatchText(prev => prev ? `${prev}\n${text}` : text);
                            }
                          } catch (err) {
                            alert('Trình duyệt chưa cấp quyền đọc Clipboard.');
                          }
                        }}
                        className="text-[11px] text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1"
                      >
                        <Clipboard className="w-3 h-3" />
                        <span>Dán link từ Clipboard</span>
                      </button>
                    </div>
                  </div>
                  <textarea
                    value={ytBatchText}
                    onChange={e => setYtBatchText(e.target.value)}
                    rows={6}
                    placeholder="https://www.youtube.com/watch?v=...&#10;https://youtu.be/...&#10;https://www.youtube.com/shorts/..."
                    className="w-full bg-black/60 border border-gray-700 rounded-xl p-3 text-xs font-mono text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500"
                  />
                  <div className="flex items-center justify-between text-[11px]">
                    {(() => {
                      const detected = parseYtUrls(ytBatchText);
                      return (
                        <span className={detected.length > 0 ? "text-emerald-400 font-semibold" : "text-gray-500"}>
                          ✓ Đã phát hiện {detected.length} link YouTube hợp lệ
                        </span>
                      );
                    })()}
                    {ytBatchText && (
                      <button
                        type="button"
                        onClick={() => setYtBatchText('')}
                        className="text-gray-500 hover:text-gray-300 text-[10px]"
                      >
                        Xóa danh sách
                      </button>
                    )}
                  </div>
                </div>

                {/* Mode selection for batch */}
                <div className="bg-gray-900/40 border border-gray-800 rounded-xl p-3 space-y-2">
                  <span className="text-[11px] font-semibold text-gray-300">Chế độ phân tích AI:</span>
                  <div className="grid grid-cols-2 gap-3">
                    <label
                      onClick={() => setYtMode('short')}
                      className={`cursor-pointer rounded-xl p-3 border transition flex flex-col gap-1 ${
                        ytMode === 'short'
                          ? 'bg-red-950/40 border-red-500/60 ring-1 ring-red-500/40'
                          : 'bg-gray-900/50 border-gray-800 hover:border-gray-700'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-white">⚡ Short Mode (16s)</span>
                        <input type="radio" checked={ytMode === 'short'} onChange={() => setYtMode('short')} className="accent-red-500" />
                      </div>
                      <p className="text-[10px] text-gray-400">Tìm các pha giật gân, hành động, cao trào 16s chuẩn TikTok / Reels.</p>
                    </label>
                    <label
                      onClick={() => setYtMode('story')}
                      className={`cursor-pointer rounded-xl p-3 border transition flex flex-col gap-1 ${
                        ytMode === 'story'
                          ? 'bg-red-950/40 border-red-500/60 ring-1 ring-red-500/40'
                          : 'bg-gray-900/50 border-gray-800 hover:border-gray-700'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-white">📖 Story Mode (90–120s / 1p30s–2p)</span>
                        <input type="radio" checked={ytMode === 'story'} onChange={() => setYtMode('story')} className="accent-red-500" />
                      </div>
                      <p className="text-[10px] text-gray-400">Trích xuất câu chuyện trọn vẹn, phóng sự có mở đầu - cao trào - kết thúc.</p>
                    </label>
                  </div>
                </div>

                {/* Batch action buttons */}
                <div className="flex items-center justify-end gap-2.5 pt-2">
                  <button
                    type="button"
                    disabled={ytBatchBusy || parseYtUrls(ytBatchText).length === 0}
                    onClick={() => handleBatchAddYouTube(false)}
                    className="px-4 py-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-gray-200 text-xs font-semibold rounded-xl transition flex items-center gap-1.5"
                  >
                    <Plus className="w-3.5 h-3.5 text-indigo-400" />
                    <span>Thêm vào hàng đợi Tab 1</span>
                  </button>
                  <button
                    type="button"
                    disabled={ytBatchBusy || parseYtUrls(ytBatchText).length === 0}
                    onClick={() => handleBatchAddYouTube(true)}
                    className="px-5 py-2 bg-red-600 hover:bg-red-500 disabled:opacity-40 text-white text-xs font-bold rounded-xl transition shadow-lg flex items-center gap-1.5"
                  >
                    {ytBatchBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5 fill-current" />}
                    <span>Thêm &amp; Phân tích hàng loạt ngay</span>
                  </button>
                </div>
              </div>
            ) : ytBatchTab === 'history' ? (
              /* ── History & Batch Asset Code Lookup Tab ── */
              <div className="space-y-3.5 pt-1 animate-in fade-in duration-150">
                {/* Batch / Single Search Box */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between px-0.5">
                    <span className="text-[11px] font-semibold text-gray-300 flex items-center gap-1.5">
                      <Search className="w-3.5 h-3.5 text-indigo-400" />
                      <span>Tra cứu 1 mã hoặc Hàng loạt (Mã Video, Mã Clip, Tên file .mp4, hoặc Link YouTube)</span>
                    </span>
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={async () => {
                          try {
                            const clipText = await navigator.clipboard.readText();
                            if (clipText && clipText.trim()) {
                              setYtHistorySearch(prev => (prev ? `${prev}\n${clipText.trim()}` : clipText.trim()));
                            }
                          } catch {}
                        }}
                        className="px-2.5 py-1 bg-indigo-950/70 hover:bg-indigo-900/90 border border-indigo-700/60 text-indigo-200 rounded-lg text-[10px] font-semibold flex items-center gap-1 transition cursor-pointer"
                        title="Dán danh sách mã cần tra cứu từ Clipboard"
                      >
                        <Clipboard className="w-3 h-3 text-indigo-400" />
                        <span>Dán hàng loạt từ Clipboard</span>
                      </button>
                      {ytHistorySearch && (
                        <button
                          type="button"
                          onClick={() => setYtHistorySearch('')}
                          className="px-2 py-1 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-[10px] font-semibold transition cursor-pointer"
                        >
                          ✕ Xóa trắng
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="relative">
                    <textarea
                      rows={ytHistorySearch.includes('\n') || ytHistorySearch.length > 55 ? 3 : 2}
                      value={ytHistorySearch}
                      onChange={e => setYtHistorySearch(e.target.value)}
                      placeholder="Nhập 1 hoặc nhiều mã cách nhau bởi dấu cách, dấu phẩy hoặc xuống dòng...&#10;VD: H281049, H311001, H31100201_Police Track Down.mp4, https://www.youtube.com/watch?v=..."
                      className="w-full bg-black/60 border border-gray-700 rounded-xl px-3.5 py-2 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 transition font-mono resize-y leading-relaxed"
                    />
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-gray-400 px-1 flex-wrap gap-2">
                    <span>
                      {ytHistoryLoading ? (
                        <span className="flex items-center gap-1 text-indigo-400">
                          <Loader2 className="w-3 h-3 animate-spin" /> Đang tra cứu...
                        </span>
                      ) : ytHistoryMeta?.isBatch ? (
                        <span className="text-emerald-300 font-semibold">
                          ✅ Tra cứu hàng loạt: Tìm thấy <strong>{ytHistoryList.length}</strong> video (từ{' '}
                          <strong>{ytHistoryMeta.queriedCount}</strong> mã nhập vào)
                        </span>
                      ) : (
                        `Tìm thấy ${ytHistoryList.length} video trong lịch sử`
                      )}
                    </span>
                    <span className="text-[10px] text-gray-500">
                      File Excel đồng bộ tự động tại: <code className="text-gray-400 font-mono">output_clips/danh_sach_youtube_goc.csv</code>
                    </span>
                  </div>

                  {/* Warning if some codes in batch lookup were not found */}
                  {ytHistoryMeta?.notFound?.length > 0 && (
                    <div className="p-2.5 bg-amber-950/40 border border-amber-700/50 rounded-xl flex items-center justify-between gap-2 text-[11px]">
                      <div className="text-amber-200 min-w-0 flex-1">
                        <span className="font-bold text-amber-400 mr-1.5">
                          ⚠️ Không tìm thấy ({ytHistoryMeta.notFound.length}):
                        </span>
                        <span className="font-mono text-amber-300/90 break-all">
                          {ytHistoryMeta.notFound.join(', ')}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          navigator.clipboard.writeText(ytHistoryMeta.notFound.join('\n'));
                          setBatchLookupCopiedTag('not_found');
                          setTimeout(() => setBatchLookupCopiedTag(''), 2000);
                        }}
                        className="px-2 py-1 bg-amber-900/60 hover:bg-amber-800/80 border border-amber-600/50 text-amber-200 rounded-lg text-[10px] font-semibold shrink-0 cursor-pointer"
                      >
                        {batchLookupCopiedTag === 'not_found' ? '✓ Đã chép mã lỗi' : 'Copy mã lỗi'}
                      </button>
                    </div>
                  )}

                  {/* Batch Action Toolbar when results exist */}
                  {ytHistoryList.length > 0 && ytHistorySearch.trim() !== '' && (
                    <div className="p-2 bg-indigo-950/30 border border-indigo-800/40 rounded-xl flex items-center justify-between gap-2 flex-wrap">
                      <span className="text-[10px] font-bold text-indigo-300 uppercase tracking-wider pl-1">
                        ⚡ Thao tác hàng loạt ({ytHistoryList.length} kết quả):
                      </span>
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <button
                          type="button"
                          onClick={() => {
                            const urls = ytHistoryList.map(r => r.url).filter(Boolean).join('\n');
                            navigator.clipboard.writeText(urls);
                            setBatchLookupCopiedTag('all_links');
                            setTimeout(() => setBatchLookupCopiedTag(''), 2000);
                          }}
                          className="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-[10px] font-bold flex items-center gap-1 shadow transition cursor-pointer"
                          title="Copy toàn bộ link YouTube gốc (mỗi link 1 dòng)"
                        >
                          <Copy className="w-3 h-3" />
                          <span>
                            {batchLookupCopiedTag === 'all_links'
                              ? '✓ Đã chép tất cả Link!'
                              : `Copy tất cả Link (${ytHistoryList.length})`}
                          </span>
                        </button>

                        <button
                          type="button"
                          onClick={() => {
                            const rows = ytHistoryList
                              .map(r => `${r.asset_code}\t${r.url}\t${r.title || ''}\t${r.date_added || ''}`)
                              .join('\n');
                            navigator.clipboard.writeText(rows);
                            setBatchLookupCopiedTag('excel_rows');
                            setTimeout(() => setBatchLookupCopiedTag(''), 2000);
                          }}
                          className="px-2.5 py-1 bg-emerald-800/80 hover:bg-emerald-700 border border-emerald-600/50 text-emerald-100 rounded-lg text-[10px] font-bold flex items-center gap-1 transition cursor-pointer"
                          title="Copy dạng bảng (Mã + Link + Tiêu đề + Ngày) để dán thẳng vào Excel hoặc Google Sheets"
                        >
                          <Clipboard className="w-3 h-3" />
                          <span>
                            {batchLookupCopiedTag === 'excel_rows'
                              ? '✓ Đã chép bảng Excel!'
                              : 'Copy Mã + Link (Excel)'}
                          </span>
                        </button>

                        <button
                          type="button"
                          onClick={() => {
                            const codes = ytHistoryList.map(r => r.asset_code).filter(Boolean).join('\n');
                            navigator.clipboard.writeText(codes);
                            setBatchLookupCopiedTag('all_codes');
                            setTimeout(() => setBatchLookupCopiedTag(''), 2000);
                          }}
                          className="px-2.5 py-1 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-200 rounded-lg text-[10px] font-semibold flex items-center gap-1 transition cursor-pointer"
                        >
                          <span>
                            {batchLookupCopiedTag === 'all_codes' ? '✓ Đã chép Mã!' : 'Copy tất cả Mã'}
                          </span>
                        </button>

                        <button
                          type="button"
                          onClick={() => {
                            const urls = ytHistoryList.map(r => r.url).filter(Boolean).join('\n');
                            setYtBatchText(urls);
                            setYtBatchTab('batch');
                          }}
                          className="px-2.5 py-1 bg-purple-900/70 hover:bg-purple-800 border border-purple-600/50 text-purple-200 rounded-lg text-[10px] font-bold flex items-center gap-1 transition cursor-pointer"
                          title="Đưa toàn bộ link tìm được sang tab Nhập List Hàng Loạt để phân tích/cắt lại"
                        >
                          <Zap className="w-3 h-3 text-amber-300" />
                          <span>Đưa sang Nhập List Hàng Loạt</span>
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                {/* List of history records */}
                <div className="space-y-2 max-h-[380px] overflow-y-auto pr-1">
                  {ytHistoryList.length === 0 ? (
                    <div className="text-center py-12 border border-dashed border-gray-800 rounded-xl">
                      <p className="text-xs text-gray-500">Chưa tìm thấy video YouTube nào phù hợp.</p>
                      <p className="text-[11px] text-gray-600 mt-1">Khi bạn dán link và cắt clip, mã quản lý sẽ tự động lưu vào đây.</p>
                    </div>
                  ) : (
                    ytHistoryList.map(rec => (
                      <div
                        key={rec.yt_id || rec.asset_code}
                        className="p-3 bg-gray-900/60 hover:bg-gray-900/90 border border-gray-800 hover:border-gray-700 rounded-xl flex items-center justify-between gap-3 transition group"
                      >
                        {/* Left: Code badge & Date */}
                        <div className="flex items-start gap-3 min-w-0">
                          <button
                            type="button"
                            onClick={() => copyAssetCode(rec.asset_code)}
                            className={`flex flex-col items-center justify-center px-2.5 py-1.5 rounded-lg shrink-0 border transition-all cursor-pointer group/badge relative select-none ${
                              ytCopiedAssetCode === rec.asset_code
                                ? 'bg-emerald-950/80 border-emerald-500/80 shadow-md shadow-emerald-950/50 scale-105'
                                : 'bg-gradient-to-br from-indigo-950/80 to-purple-950/80 border-indigo-700/50 hover:border-indigo-400 hover:from-indigo-900/90 hover:to-purple-900/90 hover:scale-105 active:scale-95'
                            }`}
                            title={`Click để sao chép mã: ${rec.asset_code}`}
                          >
                            <div className="flex items-center gap-1">
                              <span className={`text-xs font-mono font-extrabold tracking-wider ${
                                ytCopiedAssetCode === rec.asset_code ? 'text-emerald-300' : 'text-indigo-200'
                              }`}>
                                {rec.asset_code}
                              </span>
                              {ytCopiedAssetCode === rec.asset_code ? (
                                <CheckCircle2 className="w-3 h-3 text-emerald-400 animate-in zoom-in-50 duration-150" />
                              ) : (
                                <Copy className="w-2.5 h-2.5 text-indigo-400/60 group-hover/badge:text-indigo-300 transition" />
                              )}
                            </div>
                            <span className={`text-[9px] font-medium mt-0.5 ${
                              ytCopiedAssetCode === rec.asset_code ? 'text-emerald-400 font-bold' : 'text-indigo-400'
                            }`}>
                              {ytCopiedAssetCode === rec.asset_code ? 'Đã chép mã!' : (rec.date_added || 'Hôm nay')}
                            </span>
                          </button>

                          <div className="min-w-0">
                            <div className="flex items-center gap-1.5 min-w-0">
                              <h4 className="text-xs font-bold text-gray-100 truncate group-hover:text-white" title={rec.title}>
                                {rec.title || 'YouTube Video'}
                              </h4>
                              {rec.matched_query && rec.matched_query.toUpperCase() !== (rec.asset_code || '').toUpperCase() && (
                                <span className="px-1.5 py-0.2 rounded bg-cyan-950/70 border border-cyan-700/50 text-[9px] font-mono text-cyan-300 shrink-0">
                                  Khớp: {rec.matched_query}
                                </span>
                              )}
                            </div>
                            <div className="flex items-center gap-2 mt-1 text-[11px] text-gray-400">
                              <span className="font-mono text-gray-500 text-[10px] truncate max-w-xs">{rec.url}</span>
                              <span>·</span>
                              <span className="text-emerald-400 font-medium text-[10px]">{rec.clips_count || 0} clips đã cắt</span>
                            </div>
                          </div>
                        </div>

                        {/* Right: Actions */}
                        <div className="flex items-center gap-1.5 shrink-0">
                          <button
                            type="button"
                            onClick={() => copyAssetCode(rec.asset_code)}
                            className={`px-2.5 py-1.5 border rounded-lg text-xs font-semibold flex items-center gap-1 transition ${
                              ytCopiedAssetCode === rec.asset_code
                                ? 'bg-emerald-950/70 border-emerald-500/80 text-emerald-300 shadow-sm'
                                : 'bg-indigo-950/50 hover:bg-indigo-900/70 text-indigo-200 border-indigo-700/60 hover:border-indigo-500/80'
                            }`}
                            title={`Sao chép mã quản lý ${rec.asset_code}`}
                          >
                            {ytCopiedAssetCode === rec.asset_code ? (
                              <>
                                <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                                <span className="text-emerald-300">Đã chép mã!</span>
                              </>
                            ) : (
                              <>
                                <Copy className="w-3 h-3 text-indigo-300" />
                                <span>Copy Mã</span>
                              </>
                            )}
                          </button>

                          <button
                            type="button"
                            onClick={() => window.open(rec.url, '_blank')}
                            className="px-2.5 py-1.5 bg-red-950/40 hover:bg-red-900/60 text-red-300 border border-red-800/50 hover:border-red-600/60 rounded-lg text-xs font-semibold flex items-center gap-1 transition"
                            title="Mở video này trên YouTube"
                          >
                            <ExternalLink className="w-3 h-3 text-red-400" />
                            <span>Mở YouTube</span>
                          </button>

                          <button
                            type="button"
                            onClick={() => {
                              navigator.clipboard.writeText(rec.url);
                              setYtCopiedCode(rec.asset_code);
                              setTimeout(() => setYtCopiedCode(''), 2000);
                            }}
                            className="px-2.5 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700 rounded-lg text-xs font-semibold flex items-center gap-1 transition"
                            title="Sao chép link YouTube gốc"
                          >
                            {ytCopiedCode === rec.asset_code ? (
                              <>
                                <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                                <span className="text-emerald-400">Đã chép link!</span>
                              </>
                            ) : (
                              <>
                                <Copy className="w-3 h-3 text-gray-400" />
                                <span>Copy Link</span>
                              </>
                            )}
                          </button>

                          <button
                            type="button"
                            onClick={() => {
                              setYtUrl(rec.url);
                              setYtBatchTab('single');
                            }}
                            className="px-2.5 py-1.5 bg-indigo-950/50 hover:bg-indigo-900/70 text-indigo-300 border border-indigo-800/50 rounded-lg text-xs font-semibold flex items-center gap-1 transition"
                            title="Tải hoặc phân tích lại video này"
                          >
                            <Zap className="w-3 h-3 text-indigo-400" />
                            <span>Dùng lại</span>
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            ) : (
              /* ── Single Video Analysis Tab ── */
              <div className="space-y-4 pt-1 animate-in fade-in duration-150">
                {/* Input URL & Mode */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-[11px] font-medium text-gray-300 flex items-center gap-1.5">
                      <span>Dán link YouTube (Public hoặc Unlisted)</span>
                      <span className="text-[10px] text-gray-500">· Hỗ trợ link youtube.com hoặc youtu.be</span>
                    </label>
                    <div className="flex items-center gap-1.5 bg-black/40 border border-gray-700/80 px-2 py-0.5 rounded-lg">
                      <span className="text-[10px] text-gray-400 font-medium">Tiền tố mã:</span>
                      <input
                        type="text"
                        value={ytCodePrefix}
                        onChange={e => handleUpdatePrefix(e.target.value)}
                        placeholder="COP"
                        maxLength={8}
                        className="w-14 bg-black/60 border border-gray-600 rounded px-1.5 py-0.5 text-center font-mono font-bold text-indigo-300 text-[11px] uppercase focus:outline-none focus:border-indigo-400 transition"
                        title="Tùy chỉnh tiền tố mã định danh (VD: COP, VID, CAM...). Mặc định là COP"
                      />
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <div className="relative flex-1">
                      <input
                        type="text"
                        value={ytUrl}
                        onChange={e => setYtUrl(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter' && ytStatus !== 'analyzing') handleAnalyzeYouTube(); }}
                        placeholder="https://www.youtube.com/watch?v=..."
                        className="w-full bg-black/60 border border-gray-700 rounded-xl px-3.5 py-2 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-red-500 transition"
                      />
                      {ytUrl && (
                        <button
                          onClick={() => setYtUrl('')}
                          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 text-xs"
                        >
                          ✕
                        </button>
                      )}
                    </div>

                    {/* Mode Selector */}
                    <div className="flex bg-black/40 border border-gray-700/80 rounded-xl p-0.5 gap-0.5">
                      <button
                        type="button"
                        onClick={() => setYtMode('short')}
                        className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                          ytMode === 'short' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'
                        }`}
                      >
                        ⚡ Short (16s)
                      </button>
                      <button
                        type="button"
                        onClick={() => setYtMode('story')}
                        className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                          ytMode === 'story' ? 'bg-emerald-600 text-white' : 'text-gray-400 hover:text-white'
                        }`}
                      >
                        🎥 Story (90–120s / 1p30s–2p)
                      </button>
                    </div>

                    <button
                      onClick={handleAnalyzeYouTube}
                      disabled={ytStatus === 'analyzing' || !ytUrl.trim()}
                      className="px-4 py-2 bg-gradient-to-r from-red-600 to-indigo-600 hover:from-red-500 hover:to-indigo-500 disabled:opacity-40 text-white text-xs font-bold rounded-xl flex items-center gap-1.5 transition shadow-lg shrink-0"
                    >
                      {ytStatus === 'analyzing' ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          <span>Đang xem video...</span>
                        </>
                      ) : (
                        <>
                          <Sparkles className="w-3.5 h-3.5" />
                          <span>Soi Highlight</span>
                        </>
                      )}
                    </button>
                  </div>

                  {/* Real-time Duplicate Warning or Planned Asset Code */}
                  {ytDupCheck?.exists && (
                    <div className="p-3 bg-amber-950/40 border border-amber-600/50 rounded-xl flex items-center justify-between animate-in fade-in">
                      <div className="flex items-center gap-2.5">
                        <div className="w-8 h-8 rounded-lg bg-amber-500/20 border border-amber-500/30 flex items-center justify-center text-amber-400 font-bold shrink-0">
                          ⚠️
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-bold text-amber-200">Video này đã làm ngày {ytDupCheck.record?.date_added}!</span>
                            <button
                              type="button"
                              onClick={() => copyAssetCode(ytDupCheck.record?.asset_code)}
                              className={`px-2 py-0.5 rounded-full font-mono font-bold text-[11px] border transition flex items-center gap-1 cursor-pointer select-none ${
                                ytCopiedAssetCode === ytDupCheck.record?.asset_code
                                  ? 'bg-emerald-950/80 border-emerald-500 text-emerald-300'
                                  : 'bg-amber-500/20 text-amber-300 border-amber-500/40 hover:border-amber-400 hover:bg-amber-500/30 active:scale-95'
                              }`}
                              title="Click để copy mã này"
                            >
                              {ytCopiedAssetCode === ytDupCheck.record?.asset_code ? (
                                <>
                                  <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                                  <span>Đã chép mã!</span>
                                </>
                              ) : (
                                <>
                                  <span>{ytDupCheck.record?.asset_code}</span>
                                  <Copy className="w-2.5 h-2.5 opacity-70" />
                                </>
                              )}
                            </button>
                            <span className="text-[10px] text-gray-400">
                              ({ytDupCheck.record?.clips_count || 0} clips đã cắt)
                            </span>
                          </div>
                          <p className="text-[11px] text-amber-300/80 truncate max-w-lg mt-0.5">
                            {ytDupCheck.record?.title}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          type="button"
                          onClick={() => copyAssetCode(ytDupCheck.record?.asset_code)}
                          className={`px-2.5 py-1.5 border text-xs font-semibold rounded-lg flex items-center gap-1 transition ${
                            ytCopiedAssetCode === ytDupCheck.record?.asset_code
                              ? 'bg-emerald-950/70 border-emerald-500/80 text-emerald-300'
                              : 'bg-indigo-950/50 hover:bg-indigo-900/70 text-indigo-200 border-indigo-700/60 hover:border-indigo-500/80'
                          }`}
                          title="Sao chép mã quản lý"
                        >
                          {ytCopiedAssetCode === ytDupCheck.record?.asset_code ? (
                            <>
                              <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                              <span>Đã chép mã!</span>
                            </>
                          ) : (
                            <>
                              <Copy className="w-3 h-3 text-indigo-300" />
                              <span>Copy Mã</span>
                            </>
                          )}
                        </button>
                        <button
                          type="button"
                          onClick={() => window.open(ytDupCheck.record?.url, '_blank')}
                          className="px-2.5 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/30 text-xs font-semibold rounded-lg flex items-center gap-1 transition"
                        >
                          <ExternalLink className="w-3 h-3" />
                          <span>Mở YouTube gốc</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            navigator.clipboard.writeText(ytDupCheck.record?.url);
                            alert('✅ Đã copy link YouTube gốc!');
                          }}
                          className="px-2.5 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-200 text-xs font-semibold rounded-lg flex items-center gap-1 transition"
                        >
                          <Copy className="w-3 h-3" />
                          <span>Copy Link</span>
                        </button>
                      </div>
                    </div>
                  )}

                  {!ytDupCheck?.exists && ytDupCheck?.next_code && (
                    <div className="px-3 py-1.5 bg-indigo-950/30 border border-indigo-800/40 rounded-xl flex items-center justify-between text-[11px] animate-in fade-in">
                      <span className="text-gray-400 flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-indigo-400" />
                        Video mới — Mã quản lý tự động sẽ cấp:
                      </span>
                      <button
                        type="button"
                        onClick={() => copyAssetCode(ytDupCheck.next_code)}
                        className={`font-mono font-bold px-2.5 py-0.5 rounded-lg border transition flex items-center gap-1 cursor-pointer select-none ${
                          ytCopiedAssetCode === ytDupCheck.next_code
                            ? 'bg-emerald-950/80 border-emerald-500 text-emerald-300'
                            : 'text-indigo-300 bg-indigo-900/60 border-indigo-700/50 hover:border-indigo-400 hover:bg-indigo-800/60 active:scale-95'
                        }`}
                        title="Click để copy mã này"
                      >
                        {ytCopiedAssetCode === ytDupCheck.next_code ? (
                          <>
                            <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                            <span>Đã chép {ytDupCheck.next_code}!</span>
                          </>
                        ) : (
                          <>
                            <span>🏷️ {ytDupCheck.next_code}</span>
                            <Copy className="w-2.5 h-2.5 opacity-60 ml-0.5" />
                          </>
                        )}
                      </button>
                    </div>
                  )}
                </div>

                {/* Error banner */}
                {ytError && (
                  <div className="p-3 bg-red-950/40 border border-red-800/60 rounded-xl text-xs text-red-300 flex items-start gap-2">
                    <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <p className="font-semibold">Lỗi phân tích:</p>
                      <p className="text-[11px] text-red-400/90 mt-0.5">{ytError}</p>
                    </div>
                  </div>
                )}

                {/* Analyzing state */}
                {ytStatus === 'analyzing' && (
                  <div className="py-10 flex flex-col items-center justify-center text-center space-y-3">
                    <div className="relative">
                      <div className="w-14 h-14 rounded-full bg-red-600/20 border-2 border-red-500/40 flex items-center justify-center animate-pulse">
                        <Youtube className="w-7 h-7 text-red-500 animate-bounce" />
                      </div>
                      <div className="absolute inset-0 rounded-full border-2 border-indigo-500 animate-ping opacity-25" />
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-white">Gemini đang giải mã và xem video</h4>
                      <p className="text-xs text-gray-400 mt-1 max-w-md">
                        Google Cloud đang phân tích các khung hình hành động, cao trào và âm thanh trực tiếp từ YouTube. Quá trình mất khoảng 5–15 giây...
                      </p>
                    </div>
                  </div>
                )}

                {/* Results: Info + Highlights */}
                {ytStatus === 'done' && (
                  <div className="space-y-4 animate-in fade-in duration-300">
                    {/* YouTube Video Info Card */}
                    {ytInfo && (
                      <div className="p-3 bg-black/40 border border-gray-800 rounded-xl flex items-center gap-3.5">
                        {ytInfo.thumbnail ? (
                          <img
                            src={ytInfo.thumbnail}
                            alt="thumbnail"
                            className="w-24 h-14 object-cover rounded-lg border border-gray-800 shrink-0"
                          />
                        ) : (
                          <div className="w-24 h-14 bg-gray-900 rounded-lg flex items-center justify-center text-gray-600 shrink-0">
                            <Youtube className="w-6 h-6" />
                          </div>
                        )}
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-bold text-white truncate" title={ytInfo.title}>
                            {ytInfo.title}
                          </p>
                          <div className="flex items-center gap-3 text-[10px] text-gray-400 mt-1">
                            {ytInfo.uploader && <span>Kênh: <strong className="text-gray-300">{ytInfo.uploader}</strong></span>}
                            {ytInfo.duration > 0 && (
                              <span>Thời lượng: <strong className="text-emerald-400">{Math.floor(ytInfo.duration / 60)}m{Math.floor(ytInfo.duration % 60)}s</strong></span>
                            )}
                            <span className="text-indigo-400 font-medium">⚡ Đã tìm thấy {ytCandidates.length} highlight</span>
                          </div>
                        </div>
                        {ytCandidates.length > 1 && (
                          <button
                            onClick={handleDownloadAllYtCandidates}
                            disabled={ytDownloadAllBusy}
                            className="px-3 py-1.5 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 disabled:opacity-50 text-white text-xs font-semibold rounded-lg shrink-0 flex items-center gap-1.5 transition shadow"
                          >
                            {ytDownloadAllBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-200" /> : <Download className="w-3.5 h-3.5" />}
                            <span>{ytDownloadAllBusy ? 'Đang tải 3 luồng cùng lúc...' : `Tải tất cả (${ytCandidates.length}) - 3 luồng song song`}</span>
                          </button>
                        )}
                      </div>
                    )}

                    {/* Candidate List */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-[11px] text-gray-400 px-1">
                        <span className="font-semibold uppercase tracking-wider text-[10px] text-gray-500">Danh sách Highlight phát hiện bởi Gemini:</span>
                        <span>Tải cùng lúc 3 luồng song song vào Canvas</span>
                      </div>

                      {ytCandidates.length === 0 ? (
                        <div className="p-6 text-center text-gray-500 text-xs border border-dashed border-gray-800 rounded-xl">
                          Gemini không phát hiện khoảnh khắc nào thực sự kịch tính đạt tiêu chuẩn. Thử đổi sang chế độ Story hoặc link khác.
                        </div>
                      ) : (
                        ytCandidates.map((cand, idx) => {
                          const isDownloaded = ytDownloadedSet.has(idx);
                          const downloadInfo = ytDownloadingMap[idx];
                          const isDownloading = Boolean(downloadInfo);
                          return (
                            <div
                              key={idx}
                              className={`p-3.5 bg-gray-900/40 hover:bg-gray-900/70 border rounded-xl transition flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                                isDownloading
                                  ? 'border-indigo-500/70 bg-indigo-950/20 shadow-[0_0_15px_rgba(99,102,241,0.15)]'
                                  : isDownloaded
                                  ? 'border-emerald-800/40 bg-emerald-950/10'
                                  : 'border-gray-800/80 hover:border-gray-700'
                              }`}
                            >
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-1 flex-wrap">
                                  <span className="px-1.5 py-0.5 rounded bg-red-950 text-red-300 border border-red-800/50 text-[9px] font-bold font-mono">
                                    #{idx + 1}
                                  </span>
                                  <span className="px-2 py-0.5 rounded-full bg-emerald-950/60 text-emerald-300 border border-emerald-800/40 text-[9px] font-mono font-semibold">
                                    ⏱ {cand.start_time} ➔ {cand.end_time} ({cand.clip_duration || 16}s)
                                  </span>
                                  <span className={`px-2 py-0.5 rounded-full text-[9px] font-mono font-bold border ${
                                    (cand.viral_score ?? 7) >= 8.5
                                      ? 'bg-amber-950/70 text-amber-300 border-amber-600/50'
                                      : (cand.viral_score ?? 7) > 6
                                      ? 'bg-indigo-950/70 text-indigo-300 border-indigo-600/50'
                                      : 'bg-gray-800/60 text-gray-400 border-gray-700/40'
                                  }`}>
                                    ⭐ {cand.viral_score ?? 7}/10
                                  </span>
                                </div>
                                <h5 className="text-xs font-bold text-white text-left break-words">
                                  {cand.title}
                                </h5>
                                {cand.score_reason && (
                                  <p className="text-[10px] text-amber-300/90 mt-0.5 text-left italic">
                                    🎯 {cand.score_reason}
                                  </p>
                                )}
                                {cand.highlight_reason && (
                                  <p className="text-[11px] text-gray-400 mt-1 text-left line-clamp-2">
                                    💡 {cand.highlight_reason}
                                  </p>
                                )}

                                {/* Lỗi tải về hoặc mất mạng kèm nút thử lại */}
                                {ytDownloadErrors[idx] && (
                                  <div className="mt-2 p-2 rounded-xl bg-red-950/70 border border-red-800/80 text-[11px] text-red-300 flex items-center justify-between gap-2 animate-in fade-in">
                                    <span className="truncate flex-1">⚠️ {ytDownloadErrors[idx]}</span>
                                    <button
                                      type="button"
                                      onClick={() => handleDownloadYtCandidate(cand, idx)}
                                      className="px-2.5 py-1 rounded-lg bg-red-800 hover:bg-red-700 text-white font-bold text-[10px] shrink-0 transition shadow flex items-center gap-1"
                                    >
                                      <RefreshCw className="w-2.5 h-2.5" />
                                      <span>Thử lại</span>
                                    </button>
                                  </div>
                                )}

                                {/* Thanh tiến trình tải thời gian thực */}
                                {isDownloading && (
                                  <div className="mt-2.5 space-y-1">
                                    <div className="flex items-center justify-between text-[10px]">
                                      <span className="text-indigo-300 font-semibold flex items-center gap-1.5">
                                        <Loader2 className="w-3 h-3 animate-spin text-indigo-400" />
                                        {downloadInfo.statusText}
                                      </span>
                                      <span className="font-mono font-bold text-indigo-300">{downloadInfo.percent}%</span>
                                    </div>
                                    <div className="w-full bg-gray-800/80 rounded-full h-2 overflow-hidden border border-indigo-950/60 p-[1px]">
                                      <div
                                        className="bg-gradient-to-r from-indigo-500 via-purple-500 to-cyan-400 h-full rounded-full transition-all duration-300 ease-out shadow-sm"
                                        style={{ width: `${downloadInfo.percent}%` }}
                                      />
                                    </div>
                                  </div>
                                )}
                              </div>

                              <div className="shrink-0 flex items-center gap-2">
                                <button
                                  onClick={() => handleDownloadYtCandidate(cand, idx)}
                                  disabled={isDownloading || isDownloaded}
                                  className={`px-3 py-1.5 rounded-xl text-xs font-bold flex items-center gap-1.5 transition ${
                                    isDownloaded
                                      ? 'bg-emerald-900/40 border border-emerald-600/50 text-emerald-300 cursor-default'
                                      : isDownloading
                                      ? 'bg-indigo-950 border border-indigo-500/80 text-indigo-300 cursor-wait'
                                      : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-md'
                                  }`}
                                >
                                  {isDownloaded ? (
                                    <>
                                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                                      <span>Đã trong Studio</span>
                                    </>
                                  ) : isDownloading ? (
                                    <>
                                      <span className="w-2 h-2 rounded-full bg-indigo-400 animate-ping mr-0.5" />
                                      <span className="font-mono font-bold">{downloadInfo.percent}%</span>
                                    </>
                                  ) : (
                                    <>
                                      <Download className="w-3.5 h-3.5" />
                                      <span>Tải vào Studio</span>
                                    </>
                                  )}
                                </button>
                              </div>
                            </div>
                          );
                        })
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        <input
          ref={ytCookieFileInputRef}
          type="file"
          accept=".txt"
          className="hidden"
          onChange={handleUploadCookieFile}
        />

        {showCookiePasteModal && (
          <div className="fixed inset-0 z-[60] bg-black/80 flex items-center justify-center p-4 animate-in fade-in duration-150">
            <div className="bg-[#141724] border border-gray-700 rounded-2xl p-5 max-w-lg w-full space-y-3 shadow-2xl">
              <div className="flex items-center justify-between border-b border-gray-800 pb-2.5">
                <h4 className="text-xs font-bold text-white flex items-center gap-2">
                  <span>📋</span> Dán nội dung Cookie YouTube
                </h4>
                <button onClick={() => setShowCookiePasteModal(false)} className="text-gray-400 hover:text-white text-sm">✕</button>
              </div>
              <div className="flex items-center justify-between">
                <p className="text-[11px] text-gray-400">
                  Dán trực tiếp nội dung cookie từ tiện ích (định dạng Netscape):
                </p>
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      const text = await navigator.clipboard.readText();
                      if (text) setCookieInputText(text);
                    } catch {}
                  }}
                  className="text-[11px] text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1"
                >
                  <Clipboard className="w-3 h-3" />
                  <span>Dán từ Clipboard</span>
                </button>
              </div>
              <textarea
                value={cookieInputText}
                onChange={e => setCookieInputText(e.target.value)}
                rows={8}
                placeholder="# Netscape HTTP Cookie File&#10;.youtube.com&#9;TRUE&#9;/&#9;TRUE&#9;..."
                className="w-full bg-black/60 border border-gray-700 rounded-xl p-3 text-[11px] font-mono text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500"
              />
              <div className="flex justify-end gap-2 pt-1">
                <button
                  onClick={() => setShowCookiePasteModal(false)}
                  className="px-3.5 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs rounded-xl"
                >
                  Hủy
                </button>
                <button
                  onClick={handleSaveCookieText}
                  disabled={!cookieInputText.trim()}
                  className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-xs font-bold rounded-xl shadow"
                >
                  Lưu Cookie
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };
