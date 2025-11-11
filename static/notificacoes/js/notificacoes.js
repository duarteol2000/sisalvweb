(function () {
  // ---- Pré-visualização de fotos ----
  const fileInput = document.querySelector('input[name="fotos"]');
  const wrapper = document.getElementById('preview-wrapper');
  const grid = document.getElementById('preview-grid');
  if (fileInput && wrapper && grid) {
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
  }

  // ---- Máscaras de entrada (BR) ----
  function attachDecimalKeyguard(input, allowSign){
    input.addEventListener('keydown', function(e){
      const k = e.key;
      // Allow navigation/editing keys
      if (k === 'Backspace' || k === 'Delete' || k === 'Tab' || k === 'Enter' || k === 'Escape' ||
          k === 'Home' || k === 'End' || k === 'ArrowLeft' || k === 'ArrowRight') { e.stopImmediatePropagation(); return; }
      // Allow digits always
      if (/^[0-9]$/.test(k)) { e.stopImmediatePropagation(); return; }
      // Allow sign only at start and only once
      if (allowSign && k === '-' && input.selectionStart === 0 && !input.value.includes('-')) { e.stopImmediatePropagation(); return; }
      // Allow decimal separators '.' or ',' (we convert later)
      if (k === ',' || k === '.') { e.stopImmediatePropagation(); return; }
      // Block everything else
      e.stopImmediatePropagation();
      e.preventDefault();
    }, true);
  }

  function attachDecimalMask(input, maxDecimals, allowSign) {
    attachDecimalKeyguard(input, allowSign);
    function sanitize(val) {
      if (!val) return '';
      let s = String(val).replace(/\s+/g, '');
      // Troca ponto por vírgula (padrão BR)
      s = s.replace(/\./g, ',');
      // Mantém apenas dígitos, vírgula e (opcional) sinal no início
      let sign = '';
      if (allowSign && s[0] === '-') { sign = '-'; s = s.slice(1); }
      // remove caracteres inválidos
      s = s.replace(/[^0-9,]/g, '');
      // garante apenas uma vírgula
      const parts = s.split(',');
      if (parts.length > 1) {
        let int = parts.shift() || '';
        let dec = parts.join('');
        if (typeof maxDecimals === 'number') dec = dec.slice(0, maxDecimals);
        s = int + (dec.length ? ',' + dec : '');
      }
      return sign + s;
    }

    function padOnBlur(val) {
      if (typeof maxDecimals !== 'number') return val;
      if (!val) return val;
      // Não padroniza para lat/lng (quando maxDecimals > 2, por convenção)
      if (maxDecimals > 2) return val;
      const hasComma = val.includes(',');
      if (!hasComma) return val; // não força casas se usuário não digitou decimais
      const [i, d = ''] = val.split(',');
      return i + ',' + (d + '0'.repeat(maxDecimals)).slice(0, maxDecimals);
    }

    input.addEventListener('input', () => {
      const cur = input.value;
      const san = sanitize(cur);
      if (cur !== san) input.value = san;
    });
    input.addEventListener('blur', () => {
      input.value = padOnBlur(input.value);
    });
  }

  function attachIntMask(input) {
    input.addEventListener('input', () => {
      const cur = input.value;
      const san = String(cur).replace(/\D+/g, '');
      if (cur !== san) input.value = san;
    });
  }
  // Documentos/contatos
  function attachDocMask(input){
    input.addEventListener('input', ()=>{
      let v = (input.value||'').replace(/\D+/g,'').slice(0,14);
      if(v.length <= 11){
        v = v.replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d{1,2})$/, '$1-$2');
      }else{
        v = v.replace(/(\d{2})(\d)/, '$1.$2').replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d)/, '$1/$2').replace(/(\d{4})(\d{1,2})$/, '$1-$2');
      }
      input.value = v;
    });
  }
  function attachPhoneMask(input){
    input.addEventListener('input', ()=>{
      let v = (input.value||'').replace(/\D+/g,'').slice(0,11);
      if(v.length <= 10){
        v = v.replace(/(\d{2})(\d)/, '($1) $2').replace(/(\d{4})(\d)/, '$1-$2');
      } else {
        v = v.replace(/(\d{2})(\d)/, '($1) $2').replace(/(\d{5})(\d)/, '$1-$2');
      }
      input.value = v;
    });
  }
  function attachCepMask(input){
    input.addEventListener('input', ()=>{
      let v = (input.value||'').replace(/\D+/g,'').slice(0,8);
      v = v.replace(/(\d{5})(\d)/, '$1-$2');
      input.value = v;
    });
  }

  // Aplica máscara decimal de 2 casas em todos os campos marcados
  document.querySelectorAll('input.js-decimal-2').forEach(el => {
    attachDecimalMask(el, 2, false);
  });
  // Para js-decimal-6, ignorar latitude/longitude; máscara genérica só para outros campos raros
  document.querySelectorAll('input.js-decimal-6').forEach(el => {
    if (el.name === 'latitude' || el.name === 'longitude') return; 
    attachDecimalMask(el, 6, true);
  });
  document.querySelectorAll('input.js-int').forEach(el => attachIntMask(el));
  document.querySelectorAll('input.js-doc').forEach(el => attachDocMask(el));
  document.querySelectorAll('input.js-phone').forEach(el => attachPhoneMask(el));
  document.querySelectorAll('input.js-cep').forEach(el => attachCepMask(el));

  // Fallback: se o template ainda renderizou como type=number sem classes, força text e aplica máscara por nome
  (function(){
    const byNames6 = ['latitude','longitude'];
    // Latitude/Longitude: aceitar ponto e normalizar vírgula -> ponto, sem converter para vírgula
    function attachLatLngInput(el){
      try{ el.type = 'text'; el.removeAttribute('pattern'); el.removeAttribute('step'); el.setAttribute('inputmode','decimal'); }catch(_){ }
      el.addEventListener('keydown', function(e){
        const k = e.key;
        if (k === 'Backspace' || k === 'Delete' || k === 'Tab' || k === 'Enter' || k === 'Escape' ||
            k === 'Home' || k === 'End' || k === 'ArrowLeft' || k === 'ArrowRight') { e.stopImmediatePropagation(); return; }
        if (/^[0-9]$/.test(k)) { e.stopImmediatePropagation(); return; }
        if (k === '-' && el.selectionStart === 0 && !el.value.includes('-')) { e.stopImmediatePropagation(); return; }
        if (k === '.') { e.stopImmediatePropagation(); return; }
        if (k === ',') { e.stopImmediatePropagation(); e.preventDefault(); return; }
        e.stopImmediatePropagation(); e.preventDefault();
      }, true);
      el.addEventListener('input', ()=>{ if (el.value && el.value.includes(',')) el.value = el.value.replace(/,/g,'.'); });
    }
    byNames6.forEach(n=>{
      const el = document.querySelector('input[name="'+n+'"]');
      if(!el) return;
      attachLatLngInput(el);
    });
  })();

  // Garantia extra: antes de enviar o formulário, normaliza lat/lng para ponto
  (function(){
    document.querySelectorAll('form.notificacao-form').forEach(form => {
      form.addEventListener('submit', () => {
        const lat = form.querySelector('input[name="latitude"]');
        const lng = form.querySelector('input[name="longitude"]');
        if (lat && typeof lat.value === 'string') lat.value = lat.value.replace(/,/g, '.').trim();
        if (lng && typeof lng.value === 'string') lng.value = lng.value.replace(/,/g, '.').trim();
      });
    });
  })();

  // Removida a formatação tipo moeda; usamos a máscara decimal genérica acima.
})();
