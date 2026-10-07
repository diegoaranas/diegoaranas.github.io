// Collapsible main menu on narrow screens (see .nav-toggle in style.css).
// Loaded in <head> so the "js" class is set before first paint: without JS
// the menu simply stays expanded.
document.documentElement.classList.add('js');

document.addEventListener('click', function (e) {
  var b = e.target.closest ? e.target.closest('.nav-toggle') : null;
  if (!b) return;
  b.setAttribute('aria-expanded', b.getAttribute('aria-expanded') === 'true' ? 'false' : 'true');
});

document.addEventListener('keydown', function (e) {
  if (e.key !== 'Escape') return;
  var b = document.querySelector('.nav-toggle[aria-expanded="true"]');
  if (b) { b.setAttribute('aria-expanded', 'false'); b.focus(); }
});
