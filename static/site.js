// Small enhancements only; the site works without JavaScript.
(function () {
  var d = document.getElementById('q-date');
  if (d) { try { d.min = new Date().toISOString().slice(0, 10); } catch (e) {} }
  var f = document.querySelector('.quote-form');
  if (f) f.addEventListener('submit', function () {
    var b = f.querySelector('button[type=submit]');
    if (b) { b.disabled = true; b.textContent = 'Sending request…'; }
  });
})();
