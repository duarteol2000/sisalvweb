/* Minimal heat layer for Leaflet (fallback implementation)
 * API compat subset: L.heatLayer(latlngs, {radius, blur, max})
 * Draws grayscale alpha mask then colorizes. Not a full replacement.
 */
(function(factory){
  if(typeof define==='function' && define.amd){ define(['leaflet'], factory); }
  else if(typeof module==='object' && module.exports){ module.exports = factory(require('leaflet')); }
  else{ factory(window.L); }
})(function(L){
  if(!L) return;
  var HeatLayer = L.Layer.extend({
    initialize: function(latlngs, options){
      L.setOptions(this, options||{});
      this._latlngs = latlngs||[];
      this._buildGradient();
    },
    onAdd: function(map){
      this._map = map;
      if(!this._canvas){ this._initCanvas(); }
      map.getPanes().overlayPane.appendChild(this._canvas);
      map.on('moveend zoomend resize', this._reset, this);
      this._reset();
    },
    onRemove: function(map){
      if(this._canvas && this._canvas.parentNode){ this._canvas.parentNode.removeChild(this._canvas); }
      map.off('moveend zoomend resize', this._reset, this);
    },
    setLatLngs: function(latlngs){ this._latlngs = latlngs||[]; return this.redraw(); },
    addLatLng: function(ll){ this._latlngs.push(ll); return this.redraw(); },
    redraw: function(){ if(this._map){ this._reset(); } return this; },
    setOptions: function(opts){ L.setOptions(this, opts||{}); this._buildGradient(); return this.redraw(); },
    _initCanvas: function(){
      this._canvas = L.DomUtil.create('canvas', 'leaflet-heat-layer');
      // Permite que o mapa receba eventos de rolagem e clique por baixo do canvas
      // para manter o zoom via scroll e interações padrões do Leaflet.
      this._canvas.style.pointerEvents = 'none';
      // Não bloquear a rolagem: removido disableScrollPropagation
      // Não é necessário bloquear clique já que pointer-events está em none.
    },
    _reset: function(){
      var size = this._map.getSize();
      this._canvas.width = size.x; this._canvas.height = size.y;
      var pos = this._map.containerPointToLayerPoint([0,0]);
      L.DomUtil.setPosition(this._canvas, pos);
      this._draw();
    },
    _draw: function(){
      var ctx = this._canvas.getContext('2d');
      var w = this._canvas.width, h = this._canvas.height;
      ctx.clearRect(0,0,w,h);
      var pts = this._latlngs||[];
      if(!pts.length) return;
      var radius = this.options.radius || 24;
      var blur = (this.options.blur==null) ? Math.round(radius*0.9) : this.options.blur;
      var max = this.options.max || 1.2;
      // precompute circle mask
      var r = radius + blur;
      var circle = document.createElement('canvas');
      circle.width = circle.height = r*2;
      var cctx = circle.getContext('2d');
      var grad = cctx.createRadialGradient(r, r, Math.max(1, radius*0.1), r, r, r);
      grad.addColorStop(0, 'rgba(0,0,0,1)');
      grad.addColorStop(1, 'rgba(0,0,0,0)');
      cctx.fillStyle = grad;
      cctx.fillRect(0,0,circle.width,circle.height);
      // Alpha mask pass
      for(var i=0;i<pts.length;i++){
        var p = pts[i]; // [lat,lng,weight]
        var lat = p[0], lng = p[1]; var weight = p[2];
        var q = this._map.latLngToContainerPoint([lat,lng]);
        var a = Math.max(0, Math.min(1, (weight==null?1:weight)/max));
        if(!isFinite(q.x) || !isFinite(q.y)) continue;
        ctx.globalAlpha = a;
        ctx.drawImage(circle, Math.round(q.x - r), Math.round(q.y - r));
      }
      // Colorize pass (softer alpha mapping)
      var img = ctx.getImageData(0,0,w,h);
      var d = img.data;
      for(var i=3;i<d.length;i+=4){
        var alpha = d[i]/255; if(alpha<=0) continue;
        var col = this._color(alpha);
        d[i-3] = col[0]; d[i-2] = col[1]; d[i-1] = col[2];
        d[i] = Math.min(255, Math.round(255*(0.08+0.50*alpha)));
      }
      ctx.putImageData(img,0,0);
      ctx.globalAlpha = 1;
    },
    _buildGradient: function(){
      // Support options.gradient like Leaflet.heat: {0.4:'#4facfe', 0.65:'#00f2fe', ...}
      var g = this.options && this.options.gradient; if(!g){ this._grad = null; return; }
      // Build LUT 0..255
      var keys = Object.keys(g).map(parseFloat).filter(function(v){return isFinite(v);}).sort(function(a,b){return a-b;});
      if(!keys.length){ this._grad=null; return; }
      var lut = new Array(256);
      function parse(c){
        if(!c) return [0,0,0];
        if(/^#/.test(c)){
          var h=c.replace('#',''); if(h.length===3){ h=h.replace(/(.)/g,'$1$1'); }
          var n=parseInt(h,16); return [(n>>16)&255,(n>>8)&255,n&255];
        }
        var m = c.match(/rgba?\(([^)]+)\)/i);
        if(m){ var p=m[1].split(',').map(function(x){return parseFloat(x);}); return [p[0]||0,p[1]||0,p[2]||0]; }
        return [0,0,0];
      }
      var stops = keys.map(function(k){ return {t:Math.max(0,Math.min(1, k)), c:parse(g[k])}; });
      for(var i=0;i<256;i++){
        var t=i/255; var a=stops[0], b=stops[stops.length-1];
        for(var s=0;s<stops.length-1;s++){ if(t>=stops[s].t && t<=stops[s+1].t){ a=stops[s]; b=stops[s+1]; break; } }
        var u = (t - a.t) / Math.max(1e-6, (b.t - a.t));
        lut[i] = [
          Math.round(a.c[0] + (b.c[0]-a.c[0])*u),
          Math.round(a.c[1] + (b.c[1]-a.c[1])*u),
          Math.round(a.c[2] + (b.c[2]-a.c[2])*u)
        ];
      }
      this._grad = lut;
    },
    _color: function(t){
      var x=Math.max(0,Math.min(1,t));
      if(this._grad){ return this._grad[Math.max(0,Math.min(255, Math.round(x*255)))]; }
      // fallback simple palette
      var r=0,g=0,b=0;
      if(x<0.2){ var u=x/0.2; r=0; g=Math.round(255*u); b=255; }
      else if(x<0.4){ var u=(x-0.2)/0.2; r=0; g=255; b=Math.round(255*(1-u)); }
      else if(x<0.6){ var u=(x-0.4)/0.2; r=Math.round(255*u); g=255; b=0; }
      else if(x<0.8){ var u=(x-0.6)/0.2; r=255; g=Math.round(255*(1-u)+128*u); b=0; }
      else { var u=(x-0.8)/0.2; r=255; g=Math.round(128*(1-u)); b=0; }
      return [r,g,b];
    }
  });
  L.HeatLayer = HeatLayer;
  L.heatLayer = function(latlngs, options){ return new HeatLayer(latlngs, options); };
});
