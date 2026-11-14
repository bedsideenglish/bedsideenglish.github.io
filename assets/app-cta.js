// Device-aware "practice this in the app" bar for content pages.
//
// Content pages convert better than the homepage, but their app links sit in the header and at
// the very end of a long article. This bar surfaces one entrance once the reader is clearly
// reading (scrolled past the first screen), and steps aside whenever the page's own call to
// action is on screen.
//
// - Android: Google Play, reusing the page's own UTM-tagged Play link (utm_content=sticky_bar).
// - iPhone, iPad, desktop and unknown: the web app, reusing the page's most specific practice
//   link (for example a KMLE CPX deep link) when it has one.
// - Dismissing hides it for 14 days on this device (localStorage, best-effort only).
// - No network requests, no identifiers. Clicks are counted by site-analytics.js as
//   placement=sticky_bar on the production host only.
(function () {
  'use strict';
  if (window.__beAppBar) return;
  window.__beAppBar = true;

  var DISMISS_KEY = 'be-appbar-dismissed-at';
  var DISMISS_MS = 14 * 24 * 60 * 60 * 1000;
  var PLAY_DEFAULT = 'https://play.google.com/store/apps/details?id=com.boyskier.bedsideenglish';
  var WEB_DEFAULT = 'https://bedsideenglish.github.io/app/';

  function standalone() {
    return (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) || navigator.standalone === true;
  }

  function dismissedRecently() {
    try {
      var at = Number(localStorage.getItem(DISMISS_KEY) || 0);
      return at > 0 && Date.now() - at < DISMISS_MS;
    } catch (e) {
      return false;
    }
  }

  function platform() {
    var ua = navigator.userAgent || '';
    var hint = navigator.userAgentData && navigator.userAgentData.platform;
    if (hint === 'Android' || /Android/i.test(ua)) return 'android';
    if (/iPhone|iPad|iPod/i.test(ua) || (/Macintosh/i.test(ua) && navigator.maxTouchPoints > 1)) return 'apple-mobile';
    return 'other';
  }

  function section() {
    var parts = location.pathname.split('/').filter(Boolean);
    if (parts[0] === 'ko') parts.shift();
    return (parts[0] || 'site').replace(/\.html$/, '').replace(/[^a-z0-9-]/gi, '').slice(0, 40) || 'site';
  }

  function playHref() {
    var source = document.querySelector('a[href^="https://play.google.com/store/apps/details?id=com.boyskier.bedsideenglish"]');
    var url;
    try {
      url = new URL(source ? source.href : PLAY_DEFAULT);
      var referrer = new URLSearchParams(url.searchParams.get('referrer') || '');
      if (!referrer.get('utm_source')) referrer.set('utm_source', 'website');
      if (!referrer.get('utm_medium')) referrer.set('utm_medium', 'web');
      if (!referrer.get('utm_campaign')) referrer.set('utm_campaign', section());
      referrer.set('utm_content', 'sticky_bar');
      url.searchParams.set('referrer', referrer.toString());
      return url.toString();
    } catch (e) {
      return PLAY_DEFAULT;
    }
  }

  function webHref() {
    var specific = document.querySelector('a.practice-link[href*="/app/"], a.practice-open[href*="/app/"]');
    if (specific) return specific.href;
    var any = document.querySelector('a[href^="https://bedsideenglish.github.io/app/"], a[href^="/app/"]');
    return any ? any.href : WEB_DEFAULT;
  }

  var ko = /^ko\b/i.test(document.documentElement.lang || '');
  var COPY = ko ? {
    region: '앱에서 연습하기',
    playTitle: 'AI 환자와 소리 내어 연습',
    playNote: 'Google Play 앱 · 무료',
    webTitle: 'AI 환자와 소리 내어 연습',
    webNote: '무료 웹앱 · 설치 없이 바로',
    close: '닫기'
  } : {
    region: 'Practice in the app',
    playTitle: 'Practice this out loud',
    playNote: 'AI patient · free on Google Play',
    webTitle: 'Practice this out loud',
    webNote: 'AI patient · free web app, no install',
    close: 'Dismiss'
  };

  var CSS = '' +
    '.be-appbar{position:fixed;z-index:70;inset-inline:.5rem;inset-block-end:calc(.5rem + env(safe-area-inset-bottom,0px));' +
    'display:flex;align-items:center;gap:.25rem;padding:.25rem .25rem .25rem .375rem;border:1px solid #85878c;border-radius:.75rem;' +
    'background:#000;color:#fff;box-shadow:0 .75rem 2rem rgba(0,0,0,.35);font-family:Inter,"Pretendard Variable",Pretendard,system-ui,sans-serif;' +
    'transform:translateY(calc(100% + 1.5rem));opacity:0;visibility:hidden;transition:transform 260ms cubic-bezier(.2,.8,.2,1),opacity 200ms ease,visibility 0s linear 260ms}' +
    '.be-appbar.is-visible{transform:none;opacity:1;visibility:visible;transition:transform 260ms cubic-bezier(.2,.8,.2,1),opacity 200ms ease}' +
    '.be-appbar__go{flex:1;min-width:0;display:flex;align-items:center;gap:.625rem;min-height:3rem;padding:.25rem .5rem;border-radius:.5rem;color:#fff;text-decoration:none}' +
    '.be-appbar__go:hover{background:#1c1c1c}.be-appbar__go:focus-visible,.be-appbar__close:focus-visible{outline:3px solid #6495ed;outline-offset:2px}' +
    '.be-appbar__icon{flex:0 0 auto;width:1.75rem;height:1.75rem}' +
    '.be-appbar__copy{display:flex;flex-direction:column;min-width:0;line-height:1.2}' +
    '.be-appbar__title{font-size:.875rem;font-weight:650;letter-spacing:-.01em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
    '.be-appbar__note{font-size:.6875rem;opacity:.78}' +
    '.be-appbar__arrow{margin-inline-start:auto;font-size:1.125rem;opacity:.85}' +
    '.be-appbar__close{flex:0 0 auto;width:2.75rem;height:2.75rem;display:grid;place-items:center;border:0;border-radius:.5rem;background:transparent;color:#fff;opacity:.7;cursor:pointer;font:inherit;font-size:1.25rem;line-height:1}' +
    '.be-appbar__close:hover{opacity:1;background:#1c1c1c}' +
    '@media (min-width:48rem){.be-appbar{inset-inline:auto 1.25rem;inset-block-end:1.25rem;max-width:26rem}}' +
    '@media (prefers-reduced-motion:reduce){.be-appbar,.be-appbar.is-visible{transition:opacity 50ms linear;transform:none}}' +
    '@media print{.be-appbar{display:none}}';

  var PLAY_ICON = '<svg class="be-appbar__icon" viewBox="0 0 28 28" fill="none" aria-hidden="true"><rect x="8" y="2.5" width="12" height="23" rx="2.5" stroke="currentColor" stroke-width="1.5"/><path d="M12.5 21.5h3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><path d="M12.5 9.5v5l4-2.5z" fill="currentColor"/></svg>';
  var WEB_ICON = '<svg class="be-appbar__icon" viewBox="0 0 28 28" fill="none" aria-hidden="true"><rect x="3" y="4" width="22" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/><path d="M3 8h22M10 25h8M14 20v5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>';

  function build() {
    if (standalone() || dismissedRecently() || document.querySelector('.be-appbar, .mobile-bar')) return;
    var android = platform() === 'android';
    var bar = document.createElement('aside');
    bar.className = 'be-appbar';
    bar.setAttribute('aria-label', COPY.region);
    bar.setAttribute('data-cta', 'sticky_bar');

    var go = document.createElement('a');
    go.className = 'be-appbar__go';
    go.href = android ? playHref() : webHref();
    if (android) {
      go.target = '_blank';
      go.rel = 'noopener noreferrer';
    }
    go.innerHTML = (android ? PLAY_ICON : WEB_ICON) +
      '<span class="be-appbar__copy"><span class="be-appbar__title"></span><span class="be-appbar__note"></span></span>' +
      '<span class="be-appbar__arrow" aria-hidden="true">→</span>';
    go.querySelector('.be-appbar__title').textContent = android ? COPY.playTitle : COPY.webTitle;
    go.querySelector('.be-appbar__note').textContent = android ? COPY.playNote : COPY.webNote;

    var close = document.createElement('button');
    close.type = 'button';
    close.className = 'be-appbar__close';
    close.setAttribute('aria-label', COPY.close);
    close.textContent = '×';

    var style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);
    bar.appendChild(go);
    bar.appendChild(close);
    document.body.appendChild(bar);

    var dismissed = false;
    var ctaOnScreen = 0;
    function update() {
      var reading = window.scrollY > Math.min(window.innerHeight * 0.75, 700);
      bar.classList.toggle('is-visible', !dismissed && reading && ctaOnScreen === 0);
    }
    close.addEventListener('click', function () {
      dismissed = true;
      update();
      try { localStorage.setItem(DISMISS_KEY, String(Date.now())); } catch (e) { /* storage unavailable */ }
    });

    // The page's own calls to action take priority; the bar never doubles them up.
    var ctas = document.querySelectorAll('.cta-panel, .practice-entry, .next, .final, #download, footer, .site-footer');
    if ('IntersectionObserver' in window && ctas.length) {
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          var was = entry.target.__beOnScreen === true;
          if (entry.isIntersecting !== was) {
            entry.target.__beOnScreen = entry.isIntersecting;
            ctaOnScreen += entry.isIntersecting ? 1 : -1;
          }
        });
        update();
      });
      Array.prototype.forEach.call(ctas, function (el) { observer.observe(el); });
    }
    window.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update, { passive: true });
    update();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', build);
  else build();
})();
