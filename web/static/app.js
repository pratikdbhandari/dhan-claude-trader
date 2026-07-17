// ---- theme toggle (persisted) ----
function applyTheme(t){
  document.documentElement.setAttribute('data-theme', t);
  var i=document.getElementById('theme-icon'), l=document.getElementById('theme-label');
  if(i) i.textContent = t==='light' ? '☀' : '◐';
  if(l) l.textContent = t==='light' ? 'Light' : 'Dark';
}
function toggleTheme(){
  var cur = document.documentElement.getAttribute('data-theme');
  var next = cur==='light' ? 'terminal' : 'light';
  try{ localStorage.setItem('dct-theme', next); }catch(e){}
  applyTheme(next);
  document.querySelectorAll('script.plotly-fig').forEach(replot);
}
(function(){ try{ var t=localStorage.getItem('dct-theme'); if(t) applyTheme(t); }catch(e){} })();

// ---- Plotly render from embedded JSON ----
function replot(s){
  try{
    var fig = JSON.parse(s.textContent);
    var el = document.getElementById(s.dataset.target);
    if(!el || !window.Plotly) return;
    // Price charts get TradingView-style handling: scroll to zoom, drag to pan,
    // and a toolbar for the zoom/reset affordances. Report charts stay static.
    var live = s.dataset.target === 'livechart';
    Plotly.newPlot(el, fig.data||[], fig.layout||{}, live ? {
      responsive:true, scrollZoom:true, displaylogo:false,
      displayModeBar:'hover',
      modeBarButtonsToRemove:['select2d','lasso2d','autoScale2d','toggleSpikelines']
    } : {displayModeBar:false, responsive:true});
  }catch(e){ console.error('plot render failed', e); }
}
function renderPlots(root){ (root||document).querySelectorAll('script.plotly-fig').forEach(replot); }
document.addEventListener('DOMContentLoaded', function(){ renderPlots(document); });
document.body.addEventListener('htmx:afterSwap', function(ev){ renderPlots(ev.target); });
document.body.addEventListener('htmx:responseError', function(){
  var t=document.getElementById('toast'); if(t){ t.innerHTML='<div class="banner err">Request failed — retry.</div>'; }
});
// close modal on backdrop click / Escape
document.addEventListener('click', function(ev){
  var d=document.getElementById('dialog');
  if(d && ev.target===d){ d.innerHTML=''; }
});
document.addEventListener('keydown', function(ev){
  if(ev.key==='Escape'){ var d=document.getElementById('dialog'); if(d) d.innerHTML=''; }
});
