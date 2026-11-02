// Móvil/tablet: al tocar una clase, baja a la lista de inscritos (si no, queda fuera de pantalla).
(function () {
  var menu = document.getElementById('menu');
  if (!menu) return;
  menu.addEventListener('click', function (e) {
    if (!e.target.closest('button') || window.innerWidth > 1000) return;
    setTimeout(function () {
      var box = document.getElementById('inscritos');
      if (box) box.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 350);
  });
})();
