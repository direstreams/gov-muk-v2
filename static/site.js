(() => {
  const nav = document.getElementById('primary-navigation');
  const menuButtons = document.querySelectorAll('.menu-button,.menu-jump');

  function setMenu(open) {
    if (!nav) return;
    nav.classList.toggle('open', open);
    menuButtons.forEach(button => button.setAttribute('aria-expanded', String(open)));
  }

  menuButtons.forEach(button => button.addEventListener('click', () => {
    setMenu(!nav?.classList.contains('open'));
  }));

  nav?.querySelectorAll('a').forEach(link => link.addEventListener('click', () => setMenu(false)));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') setMenu(false);
  });

  document.querySelectorAll('.search-toggle,.search-jump').forEach(button => button.addEventListener('click', () => {
    const homeSearch = document.getElementById('home-q');
    if (homeSearch) {
      homeSearch.focus();
      homeSearch.scrollIntoView({behavior:'smooth', block:'center'});
    } else {
      window.location.href = '/#home-q';
    }
  }));

  const panel = document.getElementById('cookie-panel');
  try {
    if (localStorage.getItem('govMukCookieChoice') && panel) panel.hidden = true;
  } catch (_) {}

  document.querySelectorAll('[data-cookie-choice]').forEach(button => button.addEventListener('click', () => {
    try { localStorage.setItem('govMukCookieChoice', button.dataset.cookieChoice); } catch (_) {}
    if (panel) panel.hidden = true;
  }));

  document.getElementById('view-cookie-info')?.addEventListener('click', event => {
    const extra = document.getElementById('cookie-extra');
    extra?.classList.toggle('open');
    event.currentTarget.setAttribute('aria-expanded', String(extra?.classList.contains('open')));
  });

  document.querySelectorAll('form[action*="/delete/"] button, form[action*="/delete/"] .danger').forEach(button => {
    button.addEventListener('click', event => {
      if (!window.confirm('Delete this record? This cannot be undone.')) event.preventDefault();
    });
  });

  document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', () => {
      const submitter = form.querySelector('button[type="submit"],button:not([type])');
      if (submitter && !submitter.classList.contains('danger')) {
        submitter.disabled = true;
        submitter.dataset.originalText = submitter.textContent;
        submitter.textContent = 'Saving…';
      }
    });
  });
})();
