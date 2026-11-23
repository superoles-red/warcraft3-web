// Adapt a one-finger gesture to the engine's mouse controls. Desktop input stays native.
(() => {
  document.title = 'Warcraft III';
  const chrome = document.createElement('style');
  chrome.textContent = '.metrics { display: none !important; }';
  document.head.appendChild(chrome);
  const canvas = document.querySelector('#map');
  if (!canvas) return;
  canvas.style.touchAction = 'none';
  const fingers = new Map();
  let hold;
  let gesture = 'tap';
  let lastDistance = 0;
  const stopHold = () => clearTimeout(hold);
  const scene = () => window.openwar3?.mapScene();
  const gap = () => {
    const [a, b] = [...fingers.values()];
    return a && b ? Math.hypot(a.x - b.x, a.y - b.y) : 0;
  };
  function mouse(type, p, button, buttons) {
    canvas.dispatchEvent(new PointerEvent(type, {
      bubbles: true, cancelable: true, pointerId: p.id, pointerType: 'mouse',
      button, buttons, clientX: p.x, clientY: p.y,
    }));
  }
  function consume(e) {
    e.preventDefault();
    e.stopImmediatePropagation();
  }
  canvas.addEventListener('pointerdown', e => {
    if (e.pointerType !== 'touch') return;
    consume(e);
    const p = { id: e.pointerId, x: e.clientX, y: e.clientY, x0: e.clientX, y0: e.clientY };
    canvas.setPointerCapture(e.pointerId);
    fingers.set(p.id, p);
    stopHold();
    if (fingers.size === 1) {
      gesture = 'tap';
      hold = setTimeout(() => {
        if (gesture !== 'tap') return;
        gesture = 'order';
        mouse('pointerdown', p, 2, 2);
        mouse('pointerup', p, 2, 0);
      }, 420);
    } else {
      gesture = 'pinch';
      lastDistance = gap();
    }
  }, true);
  canvas.addEventListener('pointermove', e => {
    const p = fingers.get(e.pointerId);
    if (e.pointerType !== 'touch' || !p) return;
    consume(e);
    let dx = e.clientX - p.x, dy = e.clientY - p.y;
    p.x = e.clientX;
    p.y = e.clientY;
    if (gesture === 'tap' && Math.hypot(p.x - p.x0, p.y - p.y0) > 6) {
      stopHold();
      gesture = 'pan';
      dx = p.x - p.x0;
      dy = p.y - p.y0;
    }
    const game = scene();
    if (!game?.userControl || game.hardPaused) return;
    if (gesture === 'pan') game.midPan(dx, dy);
    if (gesture === 'pinch' && fingers.size === 2) {
      const distance = gap();
      if (Math.abs(distance - lastDistance) > 22) {
        canvas.dispatchEvent(new WheelEvent('wheel', {
          bubbles: true, cancelable: true, clientX: p.x, clientY: p.y,
          deltaY: distance > lastDistance ? -120 : 120,
        }));
        lastDistance = distance;
      }
    }
  }, true);
  function finish(e) {
    const p = fingers.get(e.pointerId);
    if (e.pointerType !== 'touch' || !p) return;
    consume(e);
    stopHold();
    if (e.type === 'pointerup' && gesture === 'tap') {
      mouse('pointerdown', p, 0, 1);
      mouse('pointerup', p, 0, 0);
    }
    fingers.delete(p.id);
    if (fingers.size) gesture = 'pan';
  }
  canvas.addEventListener('pointerup', finish, true);
  canvas.addEventListener('pointercancel', finish, true);
  window.addEventListener('blur', () => { stopHold(); fingers.clear(); });
})();
