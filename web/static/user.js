// Меню пользователя в шапке: имя, профиль, выход. Подключается на всех страницах после входа.
(async function () {
  let me = null;
  try { const r = await fetch('/api/me'); if (r.ok) me = await r.json(); } catch (e) {}
  if (!me) return;
  window.ME = me;
  document.dispatchEvent(new CustomEvent('me-ready', {detail: me}));
  const bar = document.querySelector('.topbar');
  if (!bar) return;
  const box = document.createElement('div');
  box.className = 'userbox';
  const esc = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  box.innerHTML = `<button class="btn" id="ub-btn" aria-haspopup="true">${esc(me.name)}${me.role === 'admin' ? ' · админ' : ''} ▾</button>
    <div class="usermenu" id="ub-menu" hidden>
      <a href="/profile">Профиль</a>
      ${me.role === 'admin' ? '<a href="/admin">Настройки и журнал</a>' : ''}
      <a href="/">Новая проверка</a>
      <a href="#" id="ub-out">Выйти</a>
      ${me.version ? `<div class="muted small" style="padding:6px 14px">Версия ${esc(me.version)}</div>` : ''}
    </div>`;
  bar.appendChild(box);
  const menu = box.querySelector('#ub-menu');
  box.querySelector('#ub-btn').onclick = ev => { ev.stopPropagation(); menu.hidden = !menu.hidden; };
  document.addEventListener('click', () => { menu.hidden = true; });
  box.querySelector('#ub-out').onclick = async ev => {
    ev.preventDefault();
    await fetch('/api/logout', {method: 'POST'});
    location.href = '/login';
  };
  if (me.default_password) {
    const b = document.createElement('div');
    b.className = 'banner warnbar';
    b.innerHTML = 'У вас пароль по умолчанию. <a href="/profile">Смените пароль в профиле</a>.';
    bar.insertAdjacentElement('afterend', b);
  }
})();
