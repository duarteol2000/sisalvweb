// Pequenas melhorias opcionais nos filtros
(function () {
  // Submete ao apertar Enter em qualquer input (sem clicar no Filtrar)
  const form = document.querySelector('form[data-denuncias-filtros="1"]');
  if (form) {
    form.addEventListener('keypress', function (e) {
      const target = e.target;
      if (target && target.tagName === 'INPUT' && e.key === 'Enter') {
        e.preventDefault();
        form.submit();
      }
    });
  }
})();
