const menuButton=document.querySelector('.menu-button');
const nav=document.querySelector('.service-nav');
menuButton?.addEventListener('click',()=>{const open=nav.classList.toggle('open');menuButton.setAttribute('aria-expanded',String(open));});
document.querySelectorAll('.service-nav a').forEach(a=>{if(a.pathname===location.pathname)a.setAttribute('aria-current','page');});
