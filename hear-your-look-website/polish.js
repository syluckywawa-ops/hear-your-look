'use strict';

const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const compactSettings = window.matchMedia('(max-width: 620px)');
const displaySettings = document.querySelector('.display-settings');

function syncDisplaySettings(event) {
  if (!displaySettings) return;
  displaySettings.toggleAttribute('open', !event.matches);
}

syncDisplaySettings(compactSettings);
compactSettings.addEventListener('change', syncDisplaySettings);

document.querySelector('#speed').addEventListener('change', () => {
  stopSpeech();
  document.querySelector('#voice-status').textContent = '语速已调整，点击重听可试听。';
  savePreferences();
});

document.querySelector('#contrast').addEventListener('click', event => {
  const enabled = document.documentElement.classList.toggle('high-contrast');
  event.currentTarget.setAttribute('aria-pressed', String(enabled));
  event.currentTarget.textContent = enabled ? '标准对比度' : '高对比度';
  savePreferences();
});

document.querySelector('#focus').addEventListener('click', event => {
  const enabled = document.body.classList.toggle('focused');
  event.currentTarget.setAttribute('aria-pressed', String(enabled));
  event.currentTarget.textContent = enabled ? '退出专注' : '专注体验';
});

document.querySelectorAll('a[href="#plan"]').forEach(link => link.addEventListener('click', () => {
  document.body.classList.remove('focused');
  document.querySelector('#focus').setAttribute('aria-pressed', 'false');
  document.querySelector('#focus').textContent = '专注体验';
}));

if (!prefersReducedMotion.matches && 'IntersectionObserver' in window) {
  document.documentElement.classList.add('motion-ready');
  const revealObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-visible');
      revealObserver.unobserve(entry.target);
    });
  }, { rootMargin: '0px 0px -10% 0px', threshold: 0.12 });
  document.querySelectorAll('[data-reveal]').forEach(element => revealObserver.observe(element));

  const ribbon = document.querySelector('.sound-ribbon');
  if (ribbon) {
    const ribbonObserver = new IntersectionObserver(([entry]) => {
      ribbon.classList.toggle('is-running', entry.isIntersecting);
    }, { threshold: 0.08 });
    ribbonObserver.observe(ribbon);
  }

  const flowStage = document.querySelector('.flow-stage');
  const flowArticles = document.querySelectorAll('[data-flow-step]');
  if (flowStage && flowArticles.length) {
    flowStage.dataset.activeFlow = flowArticles[0].dataset.flowStep;
    flowArticles[0].classList.add('is-current');
    const flowObserver = new IntersectionObserver(entries => {
      const visible = entries
        .filter(entry => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!visible) return;
      flowArticles.forEach(article => article.classList.toggle('is-current', article === visible.target));
      flowStage.dataset.activeFlow = visible.target.dataset.flowStep;
    }, { rootMargin: '-28% 0px -28% 0px', threshold: [0.15, 0.4, 0.7] });
    flowArticles.forEach(article => flowObserver.observe(article));
  }
}

const heroMedia = document.querySelector('.hero-media');
const finePointer = window.matchMedia('(pointer: fine)');

if (heroMedia && finePointer.matches && !prefersReducedMotion.matches) {
  let pointerFrame = 0;
  heroMedia.addEventListener('pointermove', event => {
    if (pointerFrame) cancelAnimationFrame(pointerFrame);
    pointerFrame = requestAnimationFrame(() => {
      const bounds = heroMedia.getBoundingClientRect();
      const x = (event.clientX - bounds.left) / bounds.width - 0.5;
      const y = (event.clientY - bounds.top) / bounds.height - 0.5;
      heroMedia.style.setProperty('--hero-x', `${x * -12}px`);
      heroMedia.style.setProperty('--hero-y', `${y * -8}px`);
    });
  });
  heroMedia.addEventListener('pointerleave', () => {
    if (pointerFrame) cancelAnimationFrame(pointerFrame);
    heroMedia.style.setProperty('--hero-x', '0px');
    heroMedia.style.setProperty('--hero-y', '0px');
  });
}

const studio = document.querySelector('.studio');
if (studio && finePointer.matches && !prefersReducedMotion.matches) {
  let studioFrame = 0;
  studio.addEventListener('pointermove', event => {
    if (studioFrame) cancelAnimationFrame(studioFrame);
    studioFrame = requestAnimationFrame(() => {
      const bounds = studio.getBoundingClientRect();
      const x = Math.max(0, Math.min(100, ((event.clientX - bounds.left) / bounds.width) * 100));
      const y = Math.max(0, Math.min(100, ((event.clientY - bounds.top) / bounds.height) * 100));
      studio.style.setProperty('--studio-x', `${x}%`);
      studio.style.setProperty('--studio-y', `${y}%`);
    });
  });
  studio.addEventListener('pointerleave', () => {
    if (studioFrame) cancelAnimationFrame(studioFrame);
    studio.style.setProperty('--studio-x', '62%');
    studio.style.setProperty('--studio-y', '22%');
  });
}
