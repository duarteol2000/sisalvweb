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

// Máscaras simples (BR) para denúncia
(function(){
  function attachDecimalKeyguard(input, allowSign){
    input.addEventListener('keydown', function(e){
      const k = e.key;
      if (k === 'Backspace' || k === 'Delete' || k === 'Tab' || k === 'Enter' || k === 'Escape' ||
          k === 'Home' || k === 'End' || k === 'ArrowLeft' || k === 'ArrowRight') { e.stopImmediatePropagation(); return; }
      if (/^[0-9]$/.test(k)) { e.stopImmediatePropagation(); return; }
      if (allowSign && k === '-' && input.selectionStart === 0 && !input.value.includes('-')) { e.stopImmediatePropagation(); return; }
      if (k === ',' || k === '.') { e.stopImmediatePropagation(); return; }
      e.stopImmediatePropagation();
      e.preventDefault();
    }, true);
  }
  function attachDecimalMask(input, maxDecimals, allowSign){
    attachDecimalKeyguard(input, allowSign);
    function sanitize(val){
      if(!val) return '';
      let s = String(val).replace(/\s+/g,'');
      s = s.replace(/\./g, ',');
      let sign = '';
      if(allowSign && s[0] === '-') { sign = '-'; s = s.slice(1); }
      s = s.replace(/[^0-9,]/g,'');
      const parts = s.split(',');
      if(parts.length > 1){
        let int = parts.shift()||'';
        let dec = parts.join('');
        if(typeof maxDecimals === 'number') dec = dec.slice(0, maxDecimals);
        s = int + (dec.length ? ','+dec : '');
      }
      return sign + s;
    }
    input.addEventListener('input', ()=>{
      const cur = input.value; const san = sanitize(cur);
      if(cur !== san) input.value = san;
    });
  }
  function attachOnlyDigits(input, maxLen){
    input.addEventListener('input', ()=>{
      let s = String(input.value).replace(/\D+/g,'');
      if(typeof maxLen==='number') s = s.slice(0,maxLen);
      input.value = s;
    });
  }
  function attachDocMask(input){
    input.addEventListener('input', ()=>{
      let v = (input.value||'').replace(/\D+/g,'').slice(0,14);
      if(v.length <= 11){
        // CPF: 000.000.000-00
        v = v.replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d{1,2})$/, '$1-$2');
      }else{
        // CNPJ: 00.000.000/0000-00
        v = v.replace(/(\d{2})(\d)/, '$1.$2').replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d)/, '$1/$2').replace(/(\d{4})(\d{1,2})$/, '$1-$2');
      }
      input.value = v;
    });
  }
  function attachPhoneMask(input){
    input.addEventListener('input', ()=>{
      let v = (input.value||'').replace(/\D+/g,'').slice(0,11);
      if(v.length <= 10){ // (00) 0000-0000
        v = v.replace(/(\d{2})(\d)/, '($1) $2').replace(/(\d{4})(\d)/, '$1-$2');
      } else { // (00) 00000-0000
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

  document.querySelectorAll('input.js-decimal-6').forEach(el=> attachDecimalMask(el, 6, true));
  document.querySelectorAll('input.js-int').forEach(el=> attachOnlyDigits(el));
  document.querySelectorAll('input.js-doc').forEach(el=> attachDocMask(el));
  document.querySelectorAll('input.js-phone').forEach(el=> attachPhoneMask(el));
  document.querySelectorAll('input.js-cep').forEach(el=> attachCepMask(el));
})();
