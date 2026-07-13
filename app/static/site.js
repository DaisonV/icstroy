const header = document.querySelector('#siteHeader');
const menuToggle = document.querySelector('#menuToggle');
const mobileNav = document.querySelector('#mobileNav');
const trackingDialog = document.querySelector('#trackingDialog');
const trackingForm = document.querySelector('#trackingForm');
const trackingInput = document.querySelector('#trackingInput');
const trackingResult = document.querySelector('#trackingResult');

function updateHeader() {
  header.classList.toggle('scrolled', window.scrollY > 18);
}

function closeMenu() {
  menuToggle.classList.remove('active');
  menuToggle.setAttribute('aria-expanded', 'false');
  menuToggle.setAttribute('aria-label', 'Открыть меню');
  mobileNav.hidden = true;
  header.classList.remove('menu-active');
  document.body.classList.remove('menu-open');
}

menuToggle.addEventListener('click', () => {
  const open = mobileNav.hidden;
  mobileNav.hidden = !open;
  menuToggle.classList.toggle('active', open);
  menuToggle.setAttribute('aria-expanded', String(open));
  menuToggle.setAttribute('aria-label', open ? 'Закрыть меню' : 'Открыть меню');
  header.classList.toggle('menu-active', open);
  document.body.classList.toggle('menu-open', open);
});

mobileNav.querySelectorAll('a').forEach((link) => link.addEventListener('click', closeMenu));
window.addEventListener('scroll', updateHeader, { passive: true });
updateHeader();

const revealObserver = 'IntersectionObserver' in window
  ? new IntersectionObserver((entries, observer) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.12 })
  : null;

document.querySelectorAll('.reveal').forEach((element) => {
  element.style.setProperty('--delay', `${element.dataset.delay || 0}ms`);
  if (revealObserver) revealObserver.observe(element);
  else element.classList.add('visible');
});

document.querySelector('#swapCities').addEventListener('click', () => {
  const form = document.querySelector('#calculatorForm');
  const from = form.elements.from;
  const to = form.elements.to;
  const oldFrom = from.value;
  if ([...from.options].some((option) => option.value === to.value)) from.value = to.value;
  if ([...to.options].some((option) => option.value === oldFrom)) to.value = oldFrom;
});

const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';

document.querySelector('#calculatorForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const from = data.get('from');
  const to = data.get('to');
  const weight = Number(data.get('weight'));
  const volume = Number(data.get('volume'));
  const transport = data.get('transport');

  if (from === to) {
    document.querySelector('#calculatedPrice').textContent = 'Выберите разные города';
    document.querySelector('#calculatedTime').textContent = '—';
    return;
  }

  const priceElement = document.querySelector('#calculatedPrice');
  const timeElement = document.querySelector('#calculatedTime');
  priceElement.textContent = 'Рассчитываем…';
  timeElement.textContent = '—';
  try {
    const response = await fetch('/api/calculate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
      body: JSON.stringify({ from, to, weight, volume, transport }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Не удалось выполнить расчёт.');
    priceElement.textContent = `от ${result.price.toLocaleString('ru-RU')} ₸`;
    timeElement.textContent = `${result.days_min}–${result.days_max} дней`;
  } catch (error) {
    priceElement.textContent = 'Индивидуальный расчёт';
    timeElement.textContent = error.message;
  }
});

function openTracking() {
  trackingResult.hidden = true;
  trackingInput.value = '';
  trackingDialog.showModal();
  document.body.classList.add('dialog-open');
  requestAnimationFrame(() => trackingInput.focus());
}

document.querySelectorAll('[data-open-tracking]').forEach((button) => button.addEventListener('click', openTracking));
trackingDialog.addEventListener('close', () => document.body.classList.remove('dialog-open'));
trackingDialog.addEventListener('click', (event) => {
  if (event.target === trackingDialog) trackingDialog.close();
});
document.querySelector('[data-code]').addEventListener('click', (event) => {
  trackingInput.value = event.currentTarget.dataset.code;
  trackingInput.focus();
});

trackingForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const code = trackingInput.value.trim().toUpperCase();
  trackingResult.hidden = false;
  trackingResult.classList.remove('error');
  try {
    const response = await fetch(`/api/tracking/${encodeURIComponent(code)}`);
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Отправление не найдено.');
    trackingResult.replaceChildren();
    const head = document.createElement('div');
    head.className = 'tracking-result-head';
    const number = document.createElement('strong');
    number.textContent = result.tracking_number;
    const status = document.createElement('span');
    status.className = 'status status-transit';
    status.textContent = result.status_label;
    head.append(number, status);
    const route = document.createElement('p');
    route.textContent = `${result.origin} → ${result.destination}${result.current_location ? ` · сейчас: ${result.current_location}` : ''}`;
    trackingResult.append(head, route);
  } catch (error) {
    trackingResult.classList.add('error');
    trackingResult.replaceChildren();
    const title = document.createElement('strong');
    title.textContent = error.message;
    const text = document.createElement('p');
    text.textContent = 'Проверьте номер накладной или свяжитесь с менеджером.';
    trackingResult.append(title, text);
  }
});

const toast = document.querySelector('#toast');
let toastTimer;
document.querySelector('#contactForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = form.querySelector('button[type="submit"]');
  const payload = Object.fromEntries(new FormData(form));
  submit.disabled = true;
  try {
    const response = await fetch('/api/applications', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Не удалось отправить заявку.');
    toast.querySelector('strong').textContent = `Заявка ${result.number} принята`;
    toast.querySelector('small').textContent = 'Она уже появилась в CRM. Менеджер свяжется с вами.';
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.hidden = true; }, 5000);
    form.reset();
  } catch (error) {
    toast.querySelector('strong').textContent = 'Заявка не отправлена';
    toast.querySelector('small').textContent = error.message;
    toast.hidden = false;
  } finally {
    submit.disabled = false;
  }
});
