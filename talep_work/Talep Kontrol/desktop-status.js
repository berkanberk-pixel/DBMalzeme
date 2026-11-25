/* Talep Kontrol: yerel bağlantı sağlık kontrolleri. */
(() => {
  'use strict';
  const el = document.getElementById('tkDesktopStatus');
  if (!el) return;
  const title = document.getElementById('tkDesktopStatusTitle');
  const message = document.getElementById('tkDesktopStatusMessage');
  const icon = document.getElementById('tkDesktopStatusIcon');
  let sourceAccess = null;
  let checking = false;
  let previous = null;
  let dismissed = false;
  const set = (kind, heading, body, quiet = false) => {
    el.dataset.kind = kind;
    title.textContent = heading;
    message.textContent = body;
    icon.textContent = kind === 'error' ? '!' : kind === 'warning' ? '⚠' : '✓';
    el.hidden = Boolean(quiet || dismissed);
  };
  document.getElementById('tkDesktopStatusClose')?.addEventListener('click', () => {
    dismissed = true;
    el.hidden = true;
  });
  const notify = (text, kind) => {
    if (typeof window.toast === 'function') window.toast(text, kind, 6500, 'Sistem Durumu');
  };
  async function checkHealth() {
    if(checking)return;checking=true;
    try {
      const ctrl = new AbortController();
      const timeout = setTimeout(() => ctrl.abort(), 7000);
      let response;
      try { response = await fetch('/api/health?gui=' + Date.now(), {cache:'no-store',signal:ctrl.signal}); }
      finally { clearTimeout(timeout); }
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const status = await response.json();
      if (!status.ok || status.app !== 'Talep Kontrol') throw new Error('Uygulama servisi doğrulanamadı.');
      window.dispatchEvent(new CustomEvent('talep-service-access',{detail:{connected:true,recordSecurity:status.recordSecurity}}));
      if (previous === 'offline') notify('Yerel uygulama hizmetine yeniden bağlanıldı.', 'success');
      const writes = status.recordSecurity?.sharedWritesEnabled === true;
      const next = writes ? 'online' : 'restricted';
      if (previous !== next) dismissed = false;
      previous = next;
      if(sourceAccess?.current===false){
        set('warning','Salt okunur görünüm',sourceAccess.reason||'Kaynak güncelliği doğrulanamadı. Verileri yenileyin.');
      } else if (!writes) {
        set('warning', 'Merkezi kayıt koruması etkin',
          status.recordSecurity?.reason || 'Bu Windows oturumu kesin kayıt için yetkili değil.');
      } else {
        set('success', 'Sistem bağlantısı sağlıklı', 'Yerel uygulama servisine bağlanıldı.', true);
      }
    } catch (error) {
      window.dispatchEvent(new CustomEvent('talep-service-access',{detail:{connected:false}}));
      if (previous !== 'offline') dismissed = false;
      previous = 'offline';
      set('error','Bağlantı kesildi','Uygulama hizmeti yanıt vermiyor. Görüntülenen sonuçlar güncel olmayabilir; yeniden bağlanınca kontrolü tekrarlayın.');
    } finally { checking=false; }
  }
  window.addEventListener('talep-source-access',e=>{sourceAccess=e.detail;dismissed=false;if(previous==='offline')return;if(sourceAccess?.current===false)set('warning','Salt okunur görünüm',sourceAccess.reason||'Kaynak güncelliği doğrulanamadı.');else checkHealth()});
  window.addEventListener('online', checkHealth);
  window.addEventListener('offline', checkHealth);
  checkHealth();
  setInterval(checkHealth, 30000);
})();
