// Progressive enhancement: every checklist and link is in the original HTML.
document.querySelectorAll('[data-discovery]').forEach((root) => {
  const english = document.documentElement.lang === 'en';
  const input = root.querySelector('input[type="search"]');
  const links = [...root.querySelectorAll('[data-group]')];
  const sections = [...root.querySelectorAll('[data-group-section]')];
  let group = '';
  const url = new URL(location.href);
  const normal = (s) => s.normalize('NFKC').toLocaleLowerCase().replace(/\s+/g, '');
  const apply = (save = true) => {
    const query = normal(input.value);
    const found = new Set();
    sections.forEach((section) => {
      let count = 0;
      section.querySelectorAll('[data-presentation]').forEach((row) => {
        const visible = (!group || section.dataset.groupSection === group) && (!query || normal(row.dataset.search).includes(query));
        row.hidden = !visible;
        if (visible) { count++; found.add(row.dataset.presentation); }
      });
      section.hidden = count === 0;
      section.querySelector('h2 .meta').textContent = english ? `${count}` : `${count}개`;
    });
    links.forEach((a) => a.setAttribute('aria-current', String(a.dataset.group === group)));
    root.querySelector('[data-result-count]').textContent = english
      ? `${group || 'All'} · ${found.size} presentations${query ? ' found' : ''}`
      : `${group || '전체'} · ${found.size}개 임상표현${query ? ' 검색됨' : ''}`;
    root.querySelector('[data-no-results]').hidden = found.size > 0;
    if (save) {
      const next = new URL(location.href);
      input.value ? next.searchParams.set('q', input.value) : next.searchParams.delete('q');
      group ? next.searchParams.set('group', group) : next.searchParams.delete('group');
      history.replaceState(history.state, '', next.pathname + next.search + next.hash);
    }
  };
  input.value = url.searchParams.get('q') || '';
  group = links.some((a) => a.dataset.group === url.searchParams.get('group')) ? url.searchParams.get('group') : '';
  root.querySelector('.search-tools').hidden = false;
  input.addEventListener('input', () => { group = ''; apply(); });
  links.forEach((a) => a.addEventListener('click', (event) => { event.preventDefault(); group = a.dataset.group; apply(); }));
  window.addEventListener('pageshow', () => apply(false));
  apply(false);
});

document.querySelectorAll('[data-study-views]').forEach((controls) => {
  const allowed = ['all', 'history', 'exam'];
  const links = [...controls.querySelectorAll('[data-view]')];
  const apply = () => {
    const requested = new URL(location.href).searchParams.get('view');
    const view = allowed.includes(requested) ? requested : 'all';
    document.querySelectorAll('[data-study-section]').forEach((section) => {
      section.hidden = view !== 'all' && section.dataset.studySection !== view;
    });
    links.forEach((a) => a.setAttribute('aria-current', String(a.dataset.view === view)));
  };
  links.forEach((a) => a.addEventListener('click', (event) => {
    event.preventDefault();
    history.pushState(history.state, '', a.href);
    apply();
  }));
  window.addEventListener('popstate', apply);
  apply();
});

// A printed sheet includes all sections, even when the screen is filtered.
let printDetails = [];
window.addEventListener('beforeprint', () => {
  printDetails = [...document.querySelectorAll('details')].filter((el) => !el.open);
  printDetails.forEach((el) => { el.open = true; });
});
window.addEventListener('afterprint', () => {
  printDetails.forEach((el) => { el.open = false; });
  printDetails = [];
});
