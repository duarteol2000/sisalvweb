// Simple ViaCEP autofill for CEP fields.
(function(){
  function digits(v){ return (v||'').replace(/\D+/g,''); }

  async function fetchCEP(cep){
    cep = digits(cep);
    if(!cep || cep.length < 8) return null;
    try{
      const resp = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
      if(!resp.ok) return null;
      const data = await resp.json();
      if(data.erro) return null;
      return {
        logradouro: data.logradouro || '',
        bairro: data.bairro || '',
        cidade: data.localidade || '',
        uf: data.uf || '',
      };
    }catch(e){ return null; }
  }

  function attach(container){
    const scope = (container||document);
    // Suporta múltiplos padrões: 'cep' padrão e prefixados como 'local_oco_cep'
    const ceps = Array.from(scope.querySelectorAll('input[name$="cep"]'));
    if(!ceps.length) return;
    ceps.forEach(cep=>{
      const nm = cep.getAttribute('name')||'';
      // prefixo: remove sufixo 'cep' incluindo possível underscore
      let prefix = '';
      if(nm.length>3){
        const idx = nm.lastIndexOf('cep');
        prefix = nm.slice(0, idx); // mantém underscore final, ex.: 'local_oco_'
      }
      const sel = (field)=> scope.querySelector(`[name="${prefix}${field}"]`);
      const logradouro = sel('logradouro');
      const bairro = sel('bairro');
      const cidade = sel('cidade');
      const uf = sel('uf');
      cep.addEventListener('blur', async ()=>{
        const data = await fetchCEP(cep.value);
        if(!data) return; // mantém manual
        if(logradouro && !logradouro.value) logradouro.value = data.logradouro;
        if(bairro && !bairro.value) bairro.value = data.bairro;
        if(cidade && !cidade.value) cidade.value = data.cidade;
        if(uf && !uf.value) uf.value = data.uf;
      });
    });
  }

  // auto-attach
  document.addEventListener('DOMContentLoaded', ()=> attach(document));
})();
