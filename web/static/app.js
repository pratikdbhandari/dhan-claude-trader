// Render any Plotly figures embedded as <script type="application/json" class="plotly-fig" data-target="id">
function renderPlots(root){
  (root||document).querySelectorAll('script.plotly-fig').forEach(function(s){
    try{
      var fig = JSON.parse(s.textContent);
      var el = document.getElementById(s.dataset.target);
      if(el && window.Plotly){ Plotly.newPlot(el, fig.data||[], fig.layout||{}, {displayModeBar:false, responsive:true}); }
    }catch(e){ console.error('plot render failed', e); }
  });
}
document.addEventListener('DOMContentLoaded', function(){ renderPlots(document); });
document.body.addEventListener('htmx:afterSwap', function(ev){ renderPlots(ev.target); });
document.body.addEventListener('htmx:responseError', function(){
  var t=document.getElementById('toast'); if(t){ t.innerHTML='<div class="banner err">Request failed — retry.</div>'; }
});
