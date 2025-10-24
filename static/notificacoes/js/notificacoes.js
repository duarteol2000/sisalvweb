(function () {
  const fileInput = document.querySelector('input[name="fotos"]');
  const wrapper = document.getElementById('preview-wrapper');
  const grid = document.getElementById('preview-grid');
  if (!fileInput || !wrapper || !grid) return;

  function clearPreviews() { grid.innerHTML = ''; }
  function makeThumb(url, name) {
    const item = document.createElement('div');
    item.className = 'anexo-item';
    const link = document.createElement('a');
    link.href = url; link.target = '_blank'; link.rel = 'noopener';
    const img = document.createElement('img');
    img.src = url; img.alt = name || 'pré-visualização'; img.className = 'thumb'; img.loading = 'lazy';
    link.appendChild(img); item.appendChild(link);
    const legend = document.createElement('p'); legend.className = 'anexo-legenda'; legend.textContent = name || '';
    item.appendChild(legend); grid.appendChild(item);
  }

  fileInput.addEventListener('change', function () {
    clearPreviews();
    const files = Array.from(fileInput.files || []);
    const imgs = files.filter(f => /^image\//i.test(f.type));
    if (!imgs.length) { wrapper.style.display = 'none'; return; }
    imgs.forEach(f => {
      const url = URL.createObjectURL(f);
      makeThumb(url, f.name);
      const img = grid.lastChild?.querySelector('img');
      if (img) img.addEventListener('load', () => URL.revokeObjectURL(url), { once: true });
    });
    wrapper.style.display = 'block';
  });
})();
