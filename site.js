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

document.querySelector('#calculatorForm').addEventListener('submit', (event) => {
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

  const destinationRates = { Астана: 120, Алматы: 110, Шымкент: 130, Караганда: 135, Актобе: 180, Москва: 350 };
  const originFactor = { Алматы: 1, Астана: 1.04, Шымкент: 1.08, Караганда: 1.02, Актобе: 1.12, Франкфурт: 2.4, Варшава: 2.15, Милан: 2.5, Париж: 2.6 };
  const transportFactor = { groupage: 0.78, auto: 1, air: 3.2 };
  const transitDays = { groupage: [5, 9], auto: [2, 5], air: [3, 6] };
  const chargeableWeight = Math.max(weight, volume * 167);
  const rate = (destinationRates[to] || 140) * (originFactor[from] || 1) * transportFactor[transport];
  const total = Math.max(5000, Math.round(chargeableWeight * rate / 500) * 500);
  const days = transitDays[transport];

  document.querySelector('#calculatedPrice').textContent = `от ${total.toLocaleString('ru-RU')} ₸`;
  document.querySelector('#calculatedTime').textContent = `${days[0]}–${days[1]} ${days[1] <= 4 ? 'дня' : 'дней'}`;
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

trackingForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const code = trackingInput.value.trim().toUpperCase();
  trackingResult.hidden = false;
  trackingResult.classList.toggle('error', code !== 'IC-2048');

  if (code !== 'IC-2048') {
    trackingResult.replaceChildren();
    const title = document.createElement('strong');
    title.textContent = 'Отправление не найдено';
    const text = document.createElement('p');
    text.textContent = 'Проверьте номер накладной или свяжитесь с менеджером.';
    trackingResult.append(title, text);
    return;
  }

  trackingResult.innerHTML = '<div class="tracking-result-head"><strong>IC-2048</strong><span class="status status-transit"><i></i>В пути</span></div><p>Алматы → Астана · прибытие сегодня до 18:00</p>';
});

const toast = document.querySelector('#toast');
let toastTimer;
document.querySelector('#contactForm').addEventListener('submit', (event) => {
  event.preventDefault();
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.hidden = true; }, 4500);
  event.currentTarget.reset();
});
