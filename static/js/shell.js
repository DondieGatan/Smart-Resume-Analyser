/* App shell: theme switch, sidebar (collapse and mobile), the delete-account and confirm dialogs, the topbar
   clock, and one delegated listener that wires every [data-action] / [data-backdrop] / [data-confirm-submit] /
   [data-toggle-password] in the templates, so the templates carry no inline event handlers.
   showConfirmModal(message, {title, confirmLabel}) stays global: page scripts call it. */

function toggleTheme() {
    var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    if (isDark) {
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('theme', 'light');
    } else {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('theme', 'dark');
    }
    updateThemeIcons();
}

// Icon visibility and the switch knob's position are driven purely by
// CSS off the [data-theme] attribute (see style.css) — that attribute
// is already set synchronously in <head>, before first paint, so
// nothing here needs to run before the page can render correctly.
// Doing this in JS instead used to mean every full-page navigation
// rendered the switch in its default (light) position for a moment,
// then visibly slid into place once this ran on DOMContentLoaded —
// only the text label still needs JS, since CSS can't set that.
function updateThemeIcons() {
    var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    var label = document.getElementById('theme-toggle-label');
    if (label) label.textContent = isDark ? 'Light mode' : 'Dark mode';
}

// Update icons on load
document.addEventListener('DOMContentLoaded', updateThemeIcons);

// User dropdown menu (legacy navbar, logged-out pages don't use it but kept safe)
function toggleUserMenu() {
    var dd = document.getElementById('user-dropdown');
    if (dd) dd.classList.toggle('show');
}
document.addEventListener('click', function(e) {
    var btn = document.getElementById('user-menu-btn');
    var dd = document.getElementById('user-dropdown');
    if (dd && btn && !btn.contains(e.target) && !dd.contains(e.target)) {
        dd.classList.remove('show');
    }
});

// ---------- Sidebar collapse (desktop icon-only mode) ----------
function toggleSidebarCollapse() {
    var collapsed = document.documentElement.getAttribute('data-sidebar-collapsed') === 'true';
    if (collapsed) {
        document.documentElement.removeAttribute('data-sidebar-collapsed');
        localStorage.setItem('sidebarCollapsed', 'false');
    } else {
        document.documentElement.setAttribute('data-sidebar-collapsed', 'true');
        localStorage.setItem('sidebarCollapsed', 'true');
    }
    updateSidebarCollapseToggle();
}
function updateSidebarCollapseToggle() {
    var btn = document.getElementById('sidebar-collapse-toggle');
    if (!btn) return;
    var collapsed = document.documentElement.getAttribute('data-sidebar-collapsed') === 'true';
    btn.title = collapsed ? 'Expand menu' : 'Collapse menu';
}
document.addEventListener('DOMContentLoaded', updateSidebarCollapseToggle);

// ---------- Sidebar (mobile off-canvas) ----------
function openSidebar() {
    var sb = document.getElementById('sidebar');
    var bd = document.getElementById('sidebar-backdrop');
    if (sb) sb.classList.add('open');
    if (bd) bd.classList.add('show');
}
function closeSidebar() {
    var sb = document.getElementById('sidebar');
    var bd = document.getElementById('sidebar-backdrop');
    if (sb) sb.classList.remove('open');
    if (bd) bd.classList.remove('show');
}
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeSidebar();
});

// ---------- Delete-account confirmation modal ----------
function openDeleteAccountModal() {
    var modal = document.getElementById('delete-account-modal');
    if (modal) modal.classList.add('show');
}
function closeDeleteAccountModal() {
    var modal = document.getElementById('delete-account-modal');
    if (modal) modal.classList.remove('show');
}
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeDeleteAccountModal();
});

// ---------- Generic themed confirm modal (replaces native confirm()) ----------
var _confirmModalResolve = null;
function showConfirmModal(message, options) {
    options = options || {};
    document.getElementById('confirm-modal-title').textContent = options.title || 'Are you sure?';
    document.getElementById('confirm-modal-message').textContent = message;
    document.getElementById('confirm-modal-confirm-btn').textContent = options.confirmLabel || 'Delete';
    document.getElementById('confirm-modal').classList.add('show');
    return new Promise(function(resolve) { _confirmModalResolve = resolve; });
}
function _resolveConfirmModal(result) {
    document.getElementById('confirm-modal').classList.remove('show');
    if (_confirmModalResolve) { _confirmModalResolve(result); _confirmModalResolve = null; }
}
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') _resolveConfirmModal(false);
});

// Shared helper for "Delete" forms: intercepts the submit, shows the
// themed modal, and only actually submits the form if confirmed.
function confirmDeleteSubmit(e, form, message) {
    e.preventDefault();
    showConfirmModal(message).then(function(ok) { if (ok) form.submit(); });
    return false;
}

// ---------- Topbar live date/time ----------
function updateTopbarClock() {
    var el = document.getElementById('topbar-datetime');
    if (!el) return;
    var now = new Date();
    el.textContent = now.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' }) +
        ', ' + now.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}
updateTopbarClock();
setInterval(updateTopbarClock, 30000);
    


// ---------- Wiring: data attributes -> the functions above ----------
var SHELL_ACTIONS = {
    'toggle-theme': toggleTheme,
    'toggle-sidebar-collapse': toggleSidebarCollapse,
    'open-sidebar': openSidebar,
    'close-sidebar': closeSidebar,
    'open-delete-account': openDeleteAccountModal,
    'close-delete-account': closeDeleteAccountModal,
    'submit-delete-account': function () { document.getElementById('delete-account-form').submit(); },
    'confirm-cancel': function () { _resolveConfirmModal(false); },
    'confirm-ok': function () { _resolveConfirmModal(true); }
};

document.addEventListener('click', function (e) {
    var backdrop = e.target.closest('[data-backdrop]');
    if (backdrop && e.target === backdrop) {            // a click on the dim area itself, not on the dialog
        var close = SHELL_ACTIONS[backdrop.dataset.backdrop];
        if (close) close();
        return;
    }
    var el = e.target.closest('[data-action]');
    if (el && SHELL_ACTIONS[el.dataset.action]) SHELL_ACTIONS[el.dataset.action](e, el);

    var pw = e.target.closest('[data-toggle-password]');  // the eye button next to a password field
    if (pw) {
        var input = document.getElementById(pw.dataset.togglePassword);
        var show = pw.querySelector('.eye-show');
        var hide = pw.querySelector('.eye-hide');
        if (!input) return;
        var reveal = input.type === 'password';
        input.type = reveal ? 'text' : 'password';
        if (show) show.style.display = reveal ? 'none' : 'block';
        if (hide) hide.style.display = reveal ? 'block' : 'none';
    }
});

// <form data-confirm-submit="Are you sure?"> asks in the themed dialog first and submits only on yes
document.addEventListener('submit', function (e) {
    var form = e.target.closest('form[data-confirm-submit]');
    if (!form) return;
    e.preventDefault();
    showConfirmModal(form.dataset.confirmSubmit).then(function (ok) { if (ok) form.submit(); });
});
