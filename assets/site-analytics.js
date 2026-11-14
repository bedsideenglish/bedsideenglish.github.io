// Site-wide GA4 click measurement for bedsideenglish.github.io.
//
// Loaded only by the production analytics snippet in every page's <head> (never on localhost,
// 127.0.0.1 or in automated browsers), after gtag('config') has run. It records which app
// entrance a visitor used, so website-driven installs can be estimated even though Play Console
// buckets small traffic sources as "Other".
//
//   play_store_click  a Google Play link was clicked
//   web_app_click     a link into the web app (/app/) was clicked
//
// Parameters: placement (nav | hero | sticky_bar | cta_panel | footer | inline),
// page_section (first path segment, e.g. model-interviews, kmle-cpx, ko/kmle-cpx, home) and,
// for Play links, campaign (the utm_campaign carried in the Play referrer). Only these fixed
// labels are sent: no link text, no page content, no identifiers. See privacy.html §5.
(function () {
  'use strict';
  if (typeof window.gtag !== 'function' || window.__beSiteAnalytics) return;
  window.__beSiteAnalytics = true;

  var PLAY = /^https:\/\/play\.google\.com\/store\/apps\/details\?/;
  var WEB_APP = /^https:\/\/bedsideenglish\.github\.io\/app(?:[/?#]|$)/;

  function pageSection() {
    var parts = location.pathname.replace(/\.html$/, '').split('/').filter(Boolean);
    if (!parts.length || parts[0] === 'index') return 'home';
    if (parts[0] === 'ko') return parts.length > 1 ? 'ko/' + parts[1] : 'ko';
    return parts[0];
  }

  function placement(link) {
    var explicit = link.closest('[data-cta]');
    if (explicit) return explicit.getAttribute('data-cta').slice(0, 24);
    if (link.closest('.be-appbar, .mobile-bar')) return 'sticky_bar';
    if (link.closest('header, nav, .site-head, .topbar')) return 'nav';
    if (link.closest('footer')) return 'footer';
    if (link.closest('.hero')) return 'hero';
    if (link.closest('.cta-panel, .final, #download, .next, .practice-entry, .practice-cta')) return 'cta_panel';
    return 'inline';
  }

  function playCampaign(href) {
    try {
      var referrer = new URL(href).searchParams.get('referrer') || '';
      var match = /(?:^|&)utm_campaign=([a-z0-9_-]{1,40})/i.exec(referrer);
      return match ? match[1].toLowerCase() : '(none)';
    } catch (e) {
      return '(none)';
    }
  }

  document.addEventListener('click', function (event) {
    try {
      var link = event.target && event.target.closest && event.target.closest('a[href]');
      if (!link) return;
      var href = link.href;
      var common = { placement: placement(link), page_section: pageSection() };
      if (PLAY.test(href)) {
        common.campaign = playCampaign(href);
        window.gtag('event', 'play_store_click', common);
      } else if (WEB_APP.test(href)) {
        window.gtag('event', 'web_app_click', common);
      }
    } catch (e) {
      // Measurement is best-effort and must never affect navigation.
    }
  }, true);
})();
