const menuButtons=document.querySelectorAll('.menu-button,.menu-jump');
const nav=document.getElementById('primary-navigation');
menuButtons.forEach(button=>button.addEventListener('click',()=>{if(!nav)return;const open=nav.classList.toggle('open');button.setAttribute('aria-expanded',String(open));}));
document.querySelectorAll('.search-toggle,.search-jump').forEach(button=>button.addEventListener('click',()=>document.getElementById('home-q')?.focus()));
const panel=document.getElementById('cookie-panel');
if(localStorage.getItem('govMukCookieChoice')&&panel)panel.style.display='none';
document.querySelectorAll('[data-cookie-choice]').forEach(button=>button.addEventListener('click',()=>{localStorage.setItem('govMukCookieChoice',button.dataset.cookieChoice);if(panel)panel.style.display='none';}));
document.getElementById('view-cookie-info')?.addEventListener('click',()=>document.getElementById('cookie-extra')?.classList.toggle('open'));
