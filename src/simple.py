"""
الوضع البسيط — SoundIsolator Simple.

أفلت الملف ← زر واحد ← خلّاط حيّ تتحكم فيه بمستوى الغناء والموسيقى
أثناء التشغيل المتزامن، ثم تحفظ المزيج الذي صنعته.

تشغيل:  run.bat        |  الوضع الكامل:  run-advanced.bat
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import urllib.parse
from pathlib import Path

import gradio as gr

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import (ROOT, Settings, mix_stems, pick_for_mode, probe,  # noqa: E402
                    resolve_device, separate_file, vram_gb)
from models import BY_KEY  # noqa: E402

OUTPUTS = ROOT / "outputs"

# ════════════════════════════════════════════════════════════════════
#  نظام التصميم — Dark Mode (OLED)
# ════════════════════════════════════════════════════════════════════
CSS = """
:root {
  --bg:        #0F0F23;
  --surface:   #17172E;
  --surface-2: #1F1F3A;
  --muted:     #27273B;
  --border:    #2E2E52;
  --fg:        #F8FAFC;
  --fg-dim:    #94A3B8;
  --accent:    #F97316;
  --vocals:    #818CF8;
  --music:     #34D399;
  --danger:    #EF4444;
  --r:         14px;
}
/* الخلفية تغطي المنفذ كله، لا حاوية Gradio وحدها */
html, body, gradio-app, .gradio-container, .app, .main {
  background: var(--bg) !important;
}
html, body {min-height: 100%;}

.gradio-container {
  direction: rtl;
  font-family: 'Inter', 'Segoe UI', Tahoma, sans-serif;
  /* توسيط صريح: بلا هذا يلتصق العنصر بحافة الشاشة */
  max-width: 1280px !important;
  width: 100% !important;
  margin-inline: auto !important;
  padding-inline: clamp(12px, 3vw, 32px) !important;
}
footer {display: none !important;}

/* عمودان على الشاشات العريضة، وتكديس على الضيقة */
#main {gap: 22px; align-items: flex-start;}
@media (max-width: 900px) {
  #main {flex-direction: column !important;}
  #main > * {min-width: 100% !important;}
}

/* حالة فارغة للخلّاط قبل أول عزل */
.mx-empty {border: 1px dashed var(--border); border-radius: var(--r);
  padding: 40px 22px; text-align: center; color: var(--fg-dim);
  background: rgba(255,255,255,.015);}
.mx-empty .t {color: var(--fg); font-weight: 600; margin: 12px 0 6px; font-size: .96rem;}
.mx-empty .s {font-size: .84rem; line-height: 1.6;}

/* ── الترويسة ── */
#hero {text-align: center; padding: 22px 0 6px;}
#hero h1 {font-size: 2rem; font-weight: 700; margin: 0; letter-spacing: -.02em;
          color: var(--fg); text-shadow: 0 0 24px rgba(249,115,22,.25);}
#hero p {margin: 8px 0 0; color: var(--fg-dim); font-size: .95rem;}
#hero .chip {display: inline-flex; align-items: center; gap: 6px; margin-top: 10px;
             padding: 5px 12px; border-radius: 999px; font-size: .8rem;
             background: var(--surface-2); border: 1px solid var(--border); color: var(--fg-dim);}
#hero .dot {width: 7px; height: 7px; border-radius: 50%; background: var(--music);
            box-shadow: 0 0 8px var(--music);}

/* ── البطاقات ── */
.card {background: var(--surface); border: 1px solid var(--border);
       border-radius: var(--r); padding: 16px 18px; color: var(--fg);}
.card .muted {color: var(--fg-dim); font-size: .87rem;}

/* ── اختيار الوضع (سريع/دقيق) ── */
/* Gradio يضع dir="ltr" داخليًا على Radio بصرف النظر عن اتجاه الحاوية —
   نفرض RTL صراحةً وإلا انقلب ترتيب دائرة الاختيار عن النص العربي. */
#mode, #mode * {direction: rtl !important;}
#mode {background: transparent !important; border: none !important; padding: 0 !important;}
/* كل خيار قابل للنقر هو <label><input><span>نص</span></label> — القاعدة
   السابقة هنا كانت تطابق هذا الشكل بالضبط فتُخفي الخيارين كليهما بدل
   إخفاء عنوان مكرَّر (كان الظن أنه داخل label، وهو ليس كذلك). حُذفت. */
#mode .wrap {display: flex !important; gap: 8px; flex-wrap: wrap;}
#mode label.selected, #mode label:has(input:checked) {
  border-color: var(--accent) !important; background: rgba(249,115,22,.1) !important;}
#mode > .wrap > label {
  flex: 1; min-width: 200px; min-height: 44px; padding: 12px 14px !important;
  border-radius: 11px !important; border: 1px solid var(--border) !important;
  background: var(--surface) !important; color: var(--fg) !important;
  cursor: pointer; transition: all .18s ease; font-size: .88rem !important;}
#mode > .wrap > label:hover {border-color: var(--fg-dim) !important;}
#mode input[type=radio] {accent-color: var(--accent);}

/* ── الزر الرئيسي ── */
#go {font-size: 1.1rem !important; font-weight: 700 !important; padding: 16px !important;
     border-radius: var(--r) !important; background: var(--accent) !important;
     border: none !important; color: #1a1005 !important;
     transition: transform .18s ease, box-shadow .18s ease, filter .18s ease;}
#go:hover:not([disabled]) {filter: brightness(1.08); box-shadow: 0 6px 24px rgba(249,115,22,.35);}
#go:active:not([disabled]) {transform: scale(.985);}
#go[disabled] {opacity: .45; cursor: not-allowed;}
#go:focus-visible {outline: 3px solid var(--accent); outline-offset: 3px;}

/* ── الخلّاط ── */
.mx {background: linear-gradient(180deg, var(--surface) 0%, var(--surface-2) 100%);
     border: 1px solid var(--border); border-radius: var(--r); padding: 18px; color: var(--fg);}
.mx-head {display: flex; align-items: center; gap: 10px; margin-bottom: 16px;}
.mx-head h3 {margin: 0; font-size: 1.02rem; font-weight: 600; flex: 1;}
.mx-head .hint {color: var(--fg-dim); font-size: .78rem;}

/* شريط النقل */
.mx-transport {display: flex; align-items: center; gap: 14px; margin-bottom: 18px;}
.mx-play {width: 52px; height: 52px; min-width: 52px; border-radius: 50%; border: none;
          background: var(--accent); color: #1a1005; cursor: pointer;
          display: grid; place-items: center;
          transition: transform .18s ease, box-shadow .18s ease;}
.mx-play:hover {box-shadow: 0 0 22px rgba(249,115,22,.5);}
.mx-play:active {transform: scale(.93);}
.mx-play:focus-visible {outline: 3px solid var(--fg); outline-offset: 3px;}
.mx-play .ic-pause {display: none;}
.mx-play.playing .ic-play {display: none;}
.mx-play.playing .ic-pause {display: block;}

.mx-seekwrap {flex: 1; display: flex; flex-direction: column; gap: 6px;}
.mx-time {display: flex; justify-content: space-between; font-size: .78rem;
          color: var(--fg-dim); font-variant-numeric: tabular-nums;}

/* قنوات المزج */
.mx-ch {display: flex; align-items: center; gap: 12px; padding: 13px 14px;
        background: rgba(255,255,255,.028); border: 1px solid var(--border);
        border-radius: 11px; margin-bottom: 10px; transition: border-color .2s ease;}
.mx-ch:focus-within {border-color: var(--accent);}
.mx-ch.off {opacity: .42;}
.mx-badge {width: 38px; height: 38px; min-width: 38px; border-radius: 10px;
           display: grid; place-items: center;}
.mx-ch[data-t="a"] .mx-badge {background: rgba(129,140,248,.16); color: var(--vocals);}
.mx-ch[data-t="b"] .mx-badge {background: rgba(52,211,153,.16);  color: var(--music);}
.mx-name {font-size: .92rem; font-weight: 600; min-width: 74px;}
.mx-val {font-size: .82rem; color: var(--fg-dim); min-width: 46px; text-align: left;
         font-variant-numeric: tabular-nums;}
.mx-mute {width: 40px; height: 40px; min-width: 40px; border-radius: 9px; cursor: pointer;
          background: var(--muted); border: 1px solid var(--border); color: var(--fg-dim);
          display: grid; place-items: center; transition: all .18s ease;}
.mx-mute:hover {color: var(--fg); border-color: var(--fg-dim);}
.mx-mute:focus-visible {outline: 3px solid var(--accent); outline-offset: 2px;}
.mx-mute.on {background: rgba(239,68,68,.16); border-color: var(--danger); color: var(--danger);}
.mx-mute .ic-off {display: none;}
.mx-mute.on .ic-on {display: none;}
.mx-mute.on .ic-off {display: block;}

/* المنزلقات */
.mx input[type=range] {-webkit-appearance: none; appearance: none; height: 6px;
  border-radius: 999px; background: var(--muted); cursor: pointer; outline: none; flex: 1;}
.mx input[type=range]::-webkit-slider-thumb {-webkit-appearance: none; appearance: none;
  width: 18px; height: 18px; border-radius: 50%; background: var(--fg);
  border: 3px solid var(--accent); cursor: pointer;
  transition: transform .15s ease, box-shadow .15s ease;}
.mx input[type=range]::-webkit-slider-thumb:hover {transform: scale(1.18);
  box-shadow: 0 0 12px rgba(249,115,22,.6);}
.mx input[type=range]:focus-visible::-webkit-slider-thumb {box-shadow: 0 0 0 4px rgba(249,115,22,.4);}
.mx-ch[data-t="a"] input[type=range]::-webkit-slider-thumb {border-color: var(--vocals);}
.mx-ch[data-t="b"] input[type=range]::-webkit-slider-thumb {border-color: var(--music);}

/* الإعدادات الجاهزة */
.mx-presets {display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap;}
.mx-preset {flex: 1; min-width: 108px; min-height: 44px; padding: 10px 14px; cursor: pointer;
            border-radius: 10px; background: var(--muted); color: var(--fg-dim);
            border: 1px solid var(--border); font-size: .87rem; font-weight: 600;
            font-family: inherit; transition: all .18s ease;}
.mx-preset:hover {background: var(--surface-2); color: var(--fg); border-color: var(--accent);}
.mx-preset:active {transform: scale(.97);}
.mx-preset:focus-visible {outline: 3px solid var(--accent); outline-offset: 2px;}

@media (prefers-reduced-motion: reduce) {
  .mx *, #go {transition: none !important;}
}
@media (max-width: 640px) {
  .mx-name {min-width: 0; font-size: .85rem;}
  .mx-ch {gap: 9px; padding: 11px;}
}
"""

# ════════════════════════════════════════════════════════════════════
#  منطق الخلّاط — يُحقن في <head> ليُنفَّذ عند تحميل الصفحة.
#  السكربتات الموضوعة داخل gr.HTML لا تُنفَّذ (المتصفّح لا يشغّل
#  <script> المُدرَج عبر innerHTML)، لذا نعتمد تفويض الأحداث بدلًا منها.
# ════════════════════════════════════════════════════════════════════
HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script>
(function () {
  const $ = (s, r) => (r || document).querySelector(s);
  const els = () => ({ a: $('#mx-a'), b: $('#mx-b') });

  function fmt(t) {
    if (!isFinite(t) || t < 0) t = 0;
    const m = Math.floor(t / 60), s = Math.floor(t % 60);
    return m + ':' + String(s).padStart(2, '0');
  }

  // مصدر الحقيقة الوحيد هو الـ DOM — لا حالة عامة تتعارض عند تحميل ملف جديد
  function gain(t) {
    const ch = $('.mx-ch[data-t="' + t + '"]');
    if (!ch) return 0;
    const fader = $('.mx-fader', ch);
    const muted = $('.mx-mute', ch).classList.contains('on');
    return muted ? 0 : (parseFloat(fader.value) || 0) / 100;
  }
  window.__mixGains = () => [gain('a'), gain('b')];

  function apply() {
    const e = els();
    ['a', 'b'].forEach(t => {
      const el = e[t]; if (!el) return;
      const g = gain(t);
      el.volume = Math.max(0, Math.min(1, g));
      const ch = $('.mx-ch[data-t="' + t + '"]');
      const fader = $('.mx-fader', ch);
      $('.mx-val', ch).textContent = Math.round(parseFloat(fader.value)) + '%';
      ch.classList.toggle('off', g === 0);
    });
  }

  // تحديث الواجهة + تصحيح الانجراف. يُستدعى من حدث timeupdate (مضمون حتى
  // والتبويب مخفي) ومن rAF للنعومة عند الظهور فقط.
  function update() {
    const e = els(); if (!e.a) return;
    // المسار (أ) هو الساعة، و(ب) يلاحقه
    if (e.b && !e.a.paused && Math.abs(e.b.currentTime - e.a.currentTime) > 0.08) {
      e.b.currentTime = e.a.currentTime;
    }
    const seek = $('.mx-seek'), cur = $('.mx-cur'), dur = $('.mx-dur');
    if (seek && !seek.dataset.dragging) {
      seek.value = e.a.duration ? (e.a.currentTime / e.a.duration) * 1000 : 0;
    }
    if (cur) cur.textContent = fmt(e.a.currentTime);
    if (dur) dur.textContent = fmt(e.a.duration);
  }

  // rAF متوقّف تمامًا في التبويبات المخفية، فهو تحسين نعومة لا أكثر
  function smooth() {
    const e = els();
    if (!e.a || e.a.paused || document.hidden) return;
    update();
    requestAnimationFrame(smooth);
  }

  // أحداث الوسائط لا تنتشر (bubble) — نلتقطها في طور الالتقاط
  document.addEventListener('timeupdate', ev => {
    if (ev.target.id === 'mx-a') update();
  }, true);
  document.addEventListener('loadedmetadata', ev => {
    if (ev.target.id === 'mx-a') update();
  }, true);
  document.addEventListener('ended', ev => {
    if (ev.target.id !== 'mx-a') return;
    const e = els(); if (e.b) e.b.pause();
    const btn = $('.mx-play');
    if (btn) { btn.classList.remove('playing'); btn.setAttribute('aria-label', 'تشغيل'); }
  }, true);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) requestAnimationFrame(smooth);
  });

  function toggle() {
    const e = els(); if (!e.a || !e.b) return;
    const btn = $('.mx-play');
    if (e.a.paused) {
      e.b.currentTime = e.a.currentTime;      // زامِن قبل البدء
      apply();
      Promise.all([e.a.play(), e.b.play()]).catch(() => {});
      btn.classList.add('playing');
      btn.setAttribute('aria-label', 'إيقاف مؤقت');
      requestAnimationFrame(smooth);
    } else {
      e.a.pause(); e.b.pause();
      btn.classList.remove('playing');
      btn.setAttribute('aria-label', 'تشغيل');
    }
  }

  function seekTo(frac) {
    const e = els(); if (!e.a || !e.a.duration) return;
    const t = frac * e.a.duration;
    e.a.currentTime = t;
    if (e.b) e.b.currentTime = t;
    const cur = $('.mx-cur'); if (cur) cur.textContent = fmt(t);
  }

  function preset(name) {
    const fa = $('.mx-ch[data-t="a"] .mx-fader'), fb = $('.mx-ch[data-t="b"] .mx-fader');
    const ma = $('.mx-ch[data-t="a"] .mx-mute'), mb = $('.mx-ch[data-t="b"] .mx-mute');
    if (!fa || !fb) return;
    const set = (v, m) => { ma.classList.toggle('on', v === 'ka'); mb.classList.toggle('on', v === 'ac'); };
    ma.classList.remove('on'); mb.classList.remove('on');
    if (name === 'karaoke')  { fa.value = 0;   fb.value = 100; ma.classList.add('on'); }
    if (name === 'acapella') { fa.value = 100; fb.value = 0;   mb.classList.add('on'); }
    if (name === 'balanced') { fa.value = 100; fb.value = 100; }
    apply();
  }

  // ── تفويض الأحداث: يعمل مع أي HTML يُحقن لاحقًا ──
  document.addEventListener('click', ev => {
    const play = ev.target.closest('.mx-play');
    if (play) { ev.preventDefault(); toggle(); return; }
    const mute = ev.target.closest('.mx-mute');
    if (mute) {
      ev.preventDefault();
      mute.classList.toggle('on');
      const on = mute.classList.contains('on');
      mute.setAttribute('aria-pressed', on ? 'true' : 'false');
      apply(); return;
    }
    const p = ev.target.closest('.mx-preset');
    if (p) { ev.preventDefault(); preset(p.dataset.preset); }
  });

  document.addEventListener('input', ev => {
    if (ev.target.classList.contains('mx-fader')) apply();
    if (ev.target.classList.contains('mx-seek')) {
      ev.target.dataset.dragging = '1';
      seekTo(parseFloat(ev.target.value) / 1000);
    }
  });
  document.addEventListener('change', ev => {
    if (ev.target.classList.contains('mx-seek')) delete ev.target.dataset.dragging;
  });

  // مسافة = تشغيل/إيقاف، ما لم يكن التركيز داخل حقل إدخال
  document.addEventListener('keydown', ev => {
    if (ev.code !== 'Space' || !$('#mx-a')) return;
    const tag = (ev.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || ev.target.isContentEditable) return;
    ev.preventDefault(); toggle();
  });

  window.__mixInit = () => setTimeout(() => { apply(); update(); }, 60);  // بعد حقن HTML جديد
})();
</script>
"""

ICON = {
    "play": '<svg class="ic-play" width="21" height="21" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5.14v13.72a1 1 0 0 0 1.54.84l10.28-6.86a1 1 0 0 0 0-1.68L9.54 4.3A1 1 0 0 0 8 5.14z"/></svg>',
    "pause": '<svg class="ic-pause" width="19" height="19" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="4" width="4.2" height="16" rx="1.4"/><rect x="13.8" y="4" width="4.2" height="16" rx="1.4"/></svg>',
    "mic": '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/></svg>',
    "music": '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>',
    "vol_on": '<svg class="ic-on" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M18.5 5.5a9 9 0 0 1 0 13"/></svg>',
    "vol_off": '<svg class="ic-off" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="22" y1="9" x2="16" y2="15"/><line x1="16" y1="9" x2="22" y2="15"/></svg>',
    "wave": '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><line x1="3" y1="12" x2="3" y2="12"/><line x1="7" y1="8" x2="7" y2="16"/><line x1="11" y1="5" x2="11" y2="19"/><line x1="15" y1="9" x2="15" y2="15"/><line x1="19" y1="11" x2="19" y2="13"/></svg>',
}


EMPTY_MIXER = f"""
<div class="mx-empty">
  <span style="color:var(--border)">{ICON['wave']}</span>
  <div class="t">الخلّاط سيظهر هنا</div>
  <div class="s">بعد العزل تتحكم بمستوى الغناء والموسيقى أثناء تشغيلهما معًا،<br>
  ثم تحفظ المزيج الذي صنعته.</div>
</div>"""


def file_url(path: str | Path) -> str:
    """رابط Gradio لخدمة ملف محلي — تحقّقت من هذا المسار عمليًا في Gradio 5."""
    return "/gradio_api/file=" + urllib.parse.quote(str(path).replace("\\", "/"))


def mixer_html(vocals: str, music: str) -> str:
    """يبني الخلّاط. المنطق نفسه محقون في <head> ويعمل بتفويض الأحداث."""
    def channel(t: str, icon: str, name: str) -> str:
        return f"""
        <div class="mx-ch" data-t="{t}">
          <div class="mx-badge">{icon}</div>
          <span class="mx-name">{name}</span>
          <button class="mx-mute" type="button" aria-pressed="false"
                  aria-label="كتم {name}">{ICON['vol_on']}{ICON['vol_off']}</button>
          <input class="mx-fader" type="range" min="0" max="100" value="100" step="1"
                 aria-label="مستوى {name}">
          <span class="mx-val">100%</span>
        </div>"""

    return f"""
    <div class="mx">
      <audio id="mx-a" src="{file_url(vocals)}" preload="auto"></audio>
      <audio id="mx-b" src="{file_url(music)}" preload="auto"></audio>

      <div class="mx-head">
        <span style="color:var(--accent)">{ICON['wave']}</span>
        <h3>الخلّاط — المساران يعملان معًا</h3>
        <span class="hint">المسافة = تشغيل/إيقاف</span>
      </div>

      <div class="mx-transport">
        <button class="mx-play" type="button" aria-label="تشغيل">{ICON['play']}{ICON['pause']}</button>
        <div class="mx-seekwrap">
          <input class="mx-seek" type="range" min="0" max="1000" value="0" step="1"
                 aria-label="موضع التشغيل">
          <div class="mx-time"><span class="mx-cur">0:00</span><span class="mx-dur">0:00</span></div>
        </div>
      </div>

      {channel('a', ICON['mic'], 'الغناء')}
      {channel('b', ICON['music'], 'الموسيقى')}

      <div class="mx-presets">
        <button class="mx-preset" type="button" data-preset="karaoke">كاريوكي — موسيقى فقط</button>
        <button class="mx-preset" type="button" data-preset="acapella">أكابيلا — غناء فقط</button>
        <button class="mx-preset" type="button" data-preset="balanced">متوازن</button>
      </div>
    </div>"""


# ════════════════════════════════════════════════════════════════════
#  المنطق
# ════════════════════════════════════════════════════════════════════

def _hardware_line() -> str:
    if resolve_device("auto") == "cuda":
        return f"كرت الشاشة ({vram_gb():.0f} GB) — التسريع مُفعَّل"
    return "المعالج (CPU) — المعالجة أبطأ"


def analyze(path):
    """يقرأ الملف ويعرض معلوماته — بلا اختيار نموذج بعد؛ ذلك يعتمد على الوضع المختار."""
    if not path:
        return "", gr.update(interactive=False), 0.0
    try:
        info = probe(path)
    except Exception as exc:
        return (f'<div class="card">تعذّر قراءة الملف — {exc}</div>',
                gr.update(interactive=False), 0.0)

    mm, ss = divmod(int(info["duration"]), 60)
    kind = "فيديو" if info["has_video"] else "صوت"
    md = (f'<div class="card"><b>{Path(path).name}</b><br>'
          f'<span class="muted">{kind} · {mm}:{ss:02d} · {info["sample_rate"]} Hz</span></div>')
    return md, gr.update(interactive=True), info["duration"]


def mode_estimate(duration_s: float, mode: str) -> str:
    """يعرض الوقت المتوقّع للوضع المختار — يتحدّث فور تبديل الاختيار، قبل الضغط."""
    if not duration_s:
        return ""
    key, why = pick_for_mode(duration_s, mode)
    return f'<div class="card"><span class="muted">التقنية: {BY_KEY[key].model_id}</span><br>{why}</div>'


INSTRUMENT_LABELS = {
    "drums": "الطبول", "bass": "الباص", "guitar": "الجيتار",
    "piano": "البيانو", "other": "أخرى (آلات متبقّية)",
}


def run(path, mode, progress=gr.Progress()):
    if not path:
        raise gr.Error("أفلت ملفًا أولًا.")
    duration = probe(path)["duration"]
    model_key, _ = pick_for_mode(duration, mode)

    # "all" بدل "both": عند اختيار نموذج Demucs يفصل كل آلة على حدة
    # (طبول/باص/جيتار/بيانو)، "both" كانت تتجاهل هذا الفصل الدقيق وتستبدله
    # بمزيج واحد. الآن تصل الأجزاء الفردية كاملة، بالإضافة إلى موسيقى مُجمَّعة
    # للمشغّل. مع نماذج الغناء/الموسيقى الثنائية (Roformer وغيرها) لا فرق —
    # هي أصلًا لا تنتج غير الاثنين.
    #
    # residual_instrumental=True (الطرح الطوري) للموسيقى المُجمَّعة تحديدًا:
    # قِسته فعليًا مقابل جمع أجزاء Demucs النظيفة على العيّنة المرجعية —
    # الطرح أفضل بفارق طفيف (21.34dB مقابل 21.09dB)، لأنه يلتقط ما لا
    # تفصله أقنعة الآلات بدقة (كالصدى والتفاعلات الدقيقة بين الآلات).
    settings = Settings(model=model_key, stem_mode="all", output_format="wav24",
                        sample_rate=44100, device="auto", residual_instrumental=True)

    def cb(frac, msg):
        progress(min(max(frac, 0.0), 1.0), desc=msg)

    try:
        res = separate_file(path, settings, progress=cb)
    except Exception as exc:
        raise gr.Error(str(exc)) from exc

    vocals, music = res.files.get("vocals"), res.files.get("instrumental")
    if not (vocals and music):
        raise gr.Error("لم يُنتج النموذج المسارين المطلوبين.")

    # آلات منفردة أنتجها Demucs إضافةً إلى الموسيقى المُجمَّعة (متاحة فقط حين
    # يقع الاختيار التلقائي على نموذج Demucs — عادة للمقاطع القصيرة).
    extra = {k: v for k, v in res.files.items() if k in INSTRUMENT_LABELS}
    extra_files = list(extra.values())
    extra_note = ""
    if extra:
        names = "، ".join(INSTRUMENT_LABELS[k] for k in extra)
        extra_note = (f'<br><span class="muted">النموذج فصل كل آلة على حدة أيضًا '
                      f'({names}) — تنزيلها بالأسفل.</span>')

    status = (f'<div class="card">تم العزل في {res.seconds/60:.1f} دقيقة — '
              f'نزّل الغناء والموسيقى مباشرة، أو حرّك المنزلقات لتصنع مزيجك الخاص.<br>'
              f'<span class="muted">{res.output_dir}</span>{extra_note}</div>')
    # الحالة تُمرَّر عبر State لا مباشرةً: Gradio يرسم شريط تقدّم فوق كل مخرج
    # مرئي، فتوجيهها هنا كان يُظهر شريطين متطابقين ويبدو كأن الواجهة معطوبة.
    return (mixer_html(vocals, music), gr.update(visible=True), vocals, music,
            status, gr.update(visible=False),
            gr.update(value=extra_files, visible=bool(extra_files)),
            gr.update(value=[vocals, music], visible=True))


def save_mix(vocals, music, gain_v, gain_m):
    """يحفظ المزيج بالمستويات الحالية — نفس ما تسمعه في المعاينة."""
    if not vocals or not music:
        raise gr.Error("لا يوجد مزيج بعد — اعزل ملفًا أولًا.")

    gv, gm = float(gain_v or 0), float(gain_m or 0)
    stem = Path(vocals).stem.replace("__vocals", "")
    tag = f"{round(gv*100)}v-{round(gm*100)}m"
    out = Path(vocals).parent / f"{stem}__mix_{tag}"

    try:
        written, rep = mix_stems({vocals: gv, music: gm}, out, "wav24")
    except Exception as exc:
        raise gr.Error(f"تعذّر حفظ المزيج: {exc}") from exc

    note = ""
    if rep["clipped"]:
        note = '<br><span class="muted">الذروة تجاوزت الحد فخُفِّض المستوى تلقائيًا لمنع التشويه.</span>'
    card = (f'<div class="card">حُفظ المزيج — الغناء {round(gv*100)}% · '
            f'الموسيقى {round(gm*100)}%<br>'
            f'<span class="muted">{written}</span>{note}</div>')
    return gr.update(value=[str(written)], visible=True), card


# على استضافة سحابية (Render وغيرها) لا يوجد جهاز محلي لفتح مجلد فيه،
# ولا مستكشف ملفات أصلًا — الزر يُخفى بالكامل بدل أن يفشل بصمت.
IS_DESKTOP = platform.system() == "Windows"


def open_folder(vocals):
    if not vocals or not IS_DESKTOP:
        return gr.update()
    folder = str(Path(vocals).parent)
    try:
        subprocess.Popen(["explorer", folder])
    except Exception:
        pass
    return gr.update()


def make_sample():
    sys.path.insert(0, str(ROOT / "demo"))
    from make_demo import build_demo
    return str(build_demo(ROOT / "demo"))


# ════════════════════════════════════════════════════════════════════
#  الواجهة
# ════════════════════════════════════════════════════════════════════
with gr.Blocks(title="عازل الصوت", css=CSS, head=HEAD,
               theme=gr.themes.Soft(primary_hue="orange", neutral_hue="slate")) as app:

    gr.HTML(f"""<div id='hero'>
      <h1>عازل الصوت</h1>
      <p>أفلت أغنية أو فيديو — يخرج الغناء وحده والموسيقى وحدها، وتتحكم بمزجهما</p>
      <div class="chip"><span class="dot"></span>{_hardware_line()}</div>
    </div>""")

    st_duration = gr.State(0.0)
    st_vocals = gr.Textbox(visible=False)
    st_music = gr.Textbox(visible=False)
    n_gv = gr.Number(value=1.0, visible=False)
    n_gm = gr.Number(value=1.0, visible=False)

    with gr.Row(elem_id="main"):
        # في RTL يظهر هذا العمود على اليمين — مكان البداية الطبيعي للعين
        with gr.Column(scale=1):
            src = gr.File(label="أفلت الملف هنا  (MP3 · WAV · FLAC · M4A · MP4 · MOV · MKV)",
                          type="filepath", elem_id="drop")
            info = gr.Markdown()
            mode = gr.Radio(
                [("متوازن — أسرع، نتيجة جيدة", "speed"),
                 ("جودة عالية — أبطأ، أدقّ فصل ممكن", "quality")],
                value="speed", label="التقنية", elem_id="mode")
            estimate = gr.HTML()
            go = gr.Button("ابدأ العزل", variant="primary", elem_id="go", interactive=False)
            sample = gr.Button("جرّبه على عيّنة جاهزة", size="sm", variant="secondary")

        with gr.Column(scale=1):
            status = gr.HTML()
            mixer = gr.HTML(EMPTY_MIXER)
            # تنزيل فوري بمجرد انتهاء العزل — بلا أي خطوة إضافية، مثل أي
            # موقع تنزيل عادي. الملفات على خادم الاستضافة لا على جهازك؛
            # هذا الزر هو ما ينقلها إلى جهازك فعليًا عبر المتصفّح.
            raw_dl = gr.File(label="⬇️ تنزيل الغناء والموسيقى", file_count="multiple",
                             visible=False)
            with gr.Row(visible=False) as actions:
                save_btn = gr.Button("اضبط المزيج ثم احفظه", variant="primary")
                folder_btn = gr.Button("افتح مجلد النتائج", variant="secondary",
                                       visible=IS_DESKTOP)
            dl = gr.File(label="⬇️ تنزيل المزيج المخصّص", visible=False)
            extra_dl = gr.File(label="⬇️ آلات منفردة (عند توفّرها)", file_count="multiple",
                               visible=False)

    # Render يضبط RENDER_GIT_COMMIT تلقائيًا لكل نشرة — نعرض أول 7 خانات في
    # التذييل، هامش تشخيصي رخيص للتأكّد أي كوميت منشور فعليًا بلا تخمين.
    _build_tag = os.environ.get("RENDER_GIT_COMMIT", "")[:7]
    _build_line = f" · build {_build_tag}" if _build_tag else ""
    gr.HTML("<p style='text-align:center;opacity:.45;font-size:.8rem;margin-top:16px'>"
            "للتحكم الكامل في النموذج والصيغة والدقة شغّل <code>run-advanced.bat</code>"
            f"{_build_line}</p>")

    # ── الربط ──
    src.change(analyze, src, [info, go, st_duration]).then(
        mode_estimate, [st_duration, mode], estimate)
    mode.change(mode_estimate, [st_duration, mode], estimate)
    sample.click(make_sample, None, src)

    st_status = gr.State("")

    go.click(lambda: gr.update(interactive=False), None, go).then(
        run, [src, mode],
        [mixer, actions, st_vocals, st_music, st_status, dl, extra_dl, raw_dl]).then(
        lambda s: s, st_status, status).then(
        None, None, None, js="() => window.__mixInit && window.__mixInit()").then(
        lambda: gr.update(interactive=True), None, go)

    # الـ js يقرأ مستويات الخلّاط من الصفحة ويمرّرها لبايثون
    save_btn.click(save_mix, [st_vocals, st_music, n_gv, n_gm], [dl, status],
                   js="(v, m, gv, gm) => { const g = window.__mixGains ? window.__mixGains() : [1,1];"
                      " return [v, m, g[0], g[1]]; }")
    folder_btn.click(open_folder, st_vocals, None)


def free_port(start: int = 7860, tries: int = 12) -> int:
    """أول منفذ حر — حتى لا ينهار البرنامج إن بقيت نسخة قديمة تعمل."""
    import socket
    for port in range(start, start + tries):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return 0


def main() -> None:
    """يُستدعى محليًا من run.bat وسحابيًا من app.py الجذري."""
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    # Render (وأغلب الاستضافات) تضبط PORT في البيئة وتتوقّع ربطًا على
    # 0.0.0.0 — بلا فتح متصفّح محلي بالطبع. محليًا نبقي السلوك القديم:
    # منفذ حرّ تلقائي على 127.0.0.1 مع فتح المتصفّح.
    hosted = "PORT" in os.environ
    port = int(os.environ.get("PORT", 0)) or free_port()
    host = "0.0.0.0" if hosted else "127.0.0.1"

    # لا بد من إدراج مجلدَي النتائج والعيّنة، وإلا رفض Gradio تقديم ملفاتهما
    # للمشغّل ولمكوّن الرفع — وتفشل الواجهة بصمت بلا أي رسالة خطأ.
    app.queue(max_size=4).launch(server_name=host, server_port=port,
                                 inbrowser=not hosted, show_api=False, share=False,
                                 allowed_paths=[str(OUTPUTS), str(ROOT / "demo")])


if __name__ == "__main__":
    main()
