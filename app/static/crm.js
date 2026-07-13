const sidebar = document.querySelector('#sidebar');
const sidebarOverlay = document.querySelector('#sidebarOverlay');
const applicationDialog = document.querySelector('#applicationDialog');
const crmToast = document.querySelector('#crmToast');

function setSidebar(open) {
  sidebar.classList.toggle('open', open);
  sidebarOverlay.classList.toggle('active', open);
  document.body.style.overflow = open ? 'hidden' : '';
}

document.querySelector('#sidebarOpen').addEventListener('click', () => setSidebar(true));
document.querySelector('#sidebarClose').addEventListener('click', () => setSidebar(false));
sidebarOverlay.addEventListener('click', () => setSidebar(false));

const realViews = new Set(['dashboard', 'applications', 'shipments', 'clients']);

function showView(view, title) {
  const actualView = realViews.has(view) ? view : 'placeholder';
  document.querySelectorAll('[data-view-panel]').forEach((panel) => {
    const active = panel.dataset.viewPanel === actualView;
    panel.hidden = !active;
    panel.classList.toggle('active', active);
  });
  document.querySelectorAll('[data-view]').forEach((button) => button.classList.toggle('active', button.dataset.view === view));
  document.querySelector('#viewTitle').textContent = title || 'Обзор';
  if (actualView === 'placeholder') document.querySelector('#placeholderTitle').textContent = `${title}: раздел в разработке`;
  setSidebar(false);
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

document.querySelectorAll('[data-view]').forEach((button) => {
  button.addEventListener('click', () => showView(button.dataset.view, button.dataset.title));
});

document.querySelectorAll('[data-go-view]').forEach((button) => {
  button.addEventListener('click', () => {
    const target = document.querySelector(`[data-view="${button.dataset.goView}"]`);
    showView(button.dataset.goView, target?.dataset.title);
  });
});

function openApplicationDialog() {
  applicationDialog.showModal();
}

document.querySelector('#newApplicationButton').addEventListener('click', openApplicationDialog);
document.querySelectorAll('.duplicate-new').forEach((button) => button.addEventListener('click', openApplicationDialog));

document.querySelector('#applicationForm').addEventListener('submit', (event) => {
  const submitter = event.submitter;
  if (!submitter || submitter.value === 'cancel') return;
  event.preventDefault();
  if (!event.currentTarget.reportValidity()) return;
  applicationDialog.close();
  event.currentTarget.reset();
  crmToast.hidden = false;
  window.setTimeout(() => { crmToast.hidden = true; }, 4000);
});

function filterApplications() {
  const query = document.querySelector('#applicationSearch').value.trim().toLowerCase();
  const status = document.querySelector('#statusFilter').value;
  let visible = 0;
  document.querySelectorAll('#applicationsTable tbody tr').forEach((row) => {
    const matchesQuery = row.dataset.search.includes(query);
    const matchesStatus = status === 'all' || row.dataset.status === status;
    row.hidden = !(matchesQuery && matchesStatus);
    if (!row.hidden) visible += 1;
  });
  document.querySelector('#applicationCount').textContent = `Показано ${visible} из 24 заявок`;
}

document.querySelector('#applicationSearch').addEventListener('input', filterApplications);
document.querySelector('#statusFilter').addEventListener('change', filterApplications);

document.addEventListener('keydown', (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault();
    document.querySelector('#globalSearch').focus();
  }
  if (event.key.toLowerCase() === 'n' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) openApplicationDialog();
});

document.querySelector('#globalSearch').addEventListener('keydown', (event) => {
  if (event.key !== 'Enter') return;
  const query = event.currentTarget.value.trim();
  if (!query) return;
  showView('applications', 'Заявки');
  document.querySelector('#applicationSearch').value = query;
  filterApplications();
});
