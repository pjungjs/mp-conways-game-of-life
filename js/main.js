// Display and input only. Every game rule and every piece of game state lives in game_of_life.py,
// which runs in the browser through Pyodide. This file draws what Python says and forwards what the user does.

const $ = (id) => document.getElementById(id);
const canvas = $('board');
const ctx = canvas.getContext('2d');
const statusEl = $('status');

let game = null;        // the Python Game object
let DEAD = 0;           // cell state numbers, read from Python
let LIVE = 1;
let sizeMin = 3;        // grid size limits, read from Python
let sizeMax = 300;
let colors = {};        // theme colors read from the CSS: live, dead, grid, born, died
let defaultHighlight = {};
let size = 0;
let cellPx = 0;
let showLines = true;
let cells = new Uint8Array(0);
let before = null;      // the grid before the latest step; used to find which cells just changed
let running = false;
let lastStep = 0;

// ---------- messages ----------
function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle('border-accent', !isError);
  statusEl.classList.toggle('border-danger', isError);
  statusEl.classList.toggle('text-danger', isError);
  delete statusEl.dataset.stop;
}

// the game stopped by itself; Python decides when and why, this only words it
function announceStop(reason) {
  const messages = {
    max: `Reached the generation limit (${game.max_generations}). Reset, or raise the limit to continue.`,
    extinct: `All cells have died at generation ${game.generation}.`,
    stable: `Stable: nothing changes anymore after generation ${game.generation}.`,
  };
  setStatus(messages[reason]);
  statusEl.dataset.stop = '1';
}

function clearStopNotice() {
  if (statusEl.dataset.stop) setStatus('');
}

// ---------- drawing ----------
function readCells() {
  const proxy = game.cells();
  cells = proxy.toJs();
  proxy.destroy();
}

// Draws one cell. `roundness` runs from 0 (square) to 1 (a circle).
function fillCell(i, color, roundness) {
  const inset = showLines ? 1 : 0;
  const side = cellPx - inset;
  const x = (i % size) * cellPx + inset;
  const y = Math.floor(i / size) * cellPx + inset;
  ctx.fillStyle = color;
  const radius = roundness * side / 2;
  if (radius < 0.5 || !ctx.roundRect) {
    ctx.fillRect(x, y, side, side);
  } else {
    ctx.beginPath();
    ctx.roundRect(x, y, side, side, radius);
    ctx.fill();
  }
}

// `before` (the grid one step ago) is only set right after a step, so the born/died highlight shows
// the latest generation's changes and disappears once the user edits the grid.
function render() {
  readCells();
  size = game.size;
  cellPx = Math.max(2, Math.floor(1000 / size));
  const px = cellPx * size;
  if (canvas.width !== px) canvas.width = canvas.height = px;
  showLines = cellPx >= 5;   // on very large grids the lines would hide the cells
  const highlight = $('highlight').checked && before && before.length === cells.length;
  const roundness = Number($('smooth').value) / 100;

  ctx.fillStyle = colors.dead;
  ctx.fillRect(0, 0, px, px);

  if (showLines) {
    ctx.strokeStyle = colors.grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 0; i <= size; i++) {
      const p = Math.min(i * cellPx, px - 1) + 0.5;
      ctx.moveTo(p, 0); ctx.lineTo(p, px);
      ctx.moveTo(0, p); ctx.lineTo(px, p);
    }
    ctx.stroke();
  }

  for (let i = 0; i < cells.length; i++) {
    if (cells[i] === LIVE) {
      fillCell(i, (highlight && before[i] === DEAD) ? colors.born : colors.live, roundness);
    } else if (highlight && before[i] === LIVE) {
      fillCell(i, colors.died, roundness);
    }
  }

  $('gen').textContent = game.generation;
  $('live').textContent = game.live_cells;
  if (document.activeElement !== $('size')) $('size').value = size;   // don't overwrite what the user is typing
}

// the user changed the grid: forget the previous generation, so nothing is highlighted
function renderAfterEdit() {
  before = null;
  render();
}

// ---------- run loop (the speed slider is read every frame, so changes apply immediately) ----------
function updateToggleButton() {
  const button = $('toggle');
  button.textContent = running ? 'Stop' : 'Start';
  button.classList.toggle('bg-stop', running);
  button.classList.toggle('border-stop', running);
  button.classList.toggle('bg-go', !running);
  button.classList.toggle('border-go', !running);
}

function stop() {
  running = false;
  updateToggleButton();
}

function frame(now) {
  if (running) {
    const interval = 1000 / Number($('speed').value);
    if (now - lastStep >= interval) {
      game.step();
      before = cells;      // the grid as last drawn, i.e. before this step
      render();
      lastStep = performance.now();   // big grids take a while to step; count the wait from when it finished
      const reason = game.stop_reason;
      if (reason) {
        stop();
        announceStop(reason);
      }
    }
  }
  requestAnimationFrame(frame);
}

// ---------- highlight option ----------
function updateHighlightUi() {
  const on = $('highlight').checked;
  $('highlight-colors').classList.toggle('hidden', !on);
  $('highlight-colors').classList.toggle('flex', on);
  $('legend-born').classList.toggle('hidden', !on);
  $('legend-born').classList.toggle('flex', on);
  $('legend-died').classList.toggle('hidden', !on);
  $('legend-died').classList.toggle('flex', on);
  colors.born = $('born-color').value;
  colors.died = $('died-color').value;
  $('legend-born-swatch').style.backgroundColor = colors.born;
  $('legend-died-swatch').style.backgroundColor = colors.died;
  render();
}

// ---------- controls ----------
function wireControls() {
  $('toggle').addEventListener('click', () => {
    if (running) { stop(); setStatus(''); return; }
    if (game.stop_reason) { announceStop(game.stop_reason); return; }
    running = true;
    lastStep = 0;
    updateToggleButton();
    setStatus('');
  });
  $('reset').addEventListener('click', () => { stop(); game.reset(); renderAfterEdit(); setStatus('Back to the starting grid.'); });
  $('randomize').addEventListener('click', () => { stop(); game.randomize(); renderAfterEdit(); setStatus(''); });
  $('clear').addEventListener('click', () => { stop(); game.clear(); renderAfterEdit(); setStatus('Grid cleared. Click cells to bring them to life.'); });

  // The grid follows the size box as you type. A half-typed number (say "2" on the way to "25")
  // is waited out; when the box loses focus Python clamps whatever is left to the allowed range.
  const applySize = (final) => {
    const text = $('size').value.trim();
    const n = Number(text);
    const valid = text !== '' && Number.isInteger(n) && n >= sizeMin && n <= sizeMax;
    if (!valid && !final) return;
    game.randomize(valid ? n : text);   // Python clamps and validates
    $('size').value = game.size;
    renderAfterEdit();
    clearStopNotice();
  };
  $('size').addEventListener('input', () => applySize(false));
  $('size').addEventListener('change', () => applySize(true));

  // The rule applies as soon as it is valid. A half-typed rule is waited out before the error shows.
  let ruleErrorTimer = null;
  const showRuleError = (error) => {
    $('rule').classList.toggle('invalid', !!error);
    $('rule-error').textContent = error;
  };
  const applyRule = (final) => {
    clearTimeout(ruleErrorTimer);
    const error = game.set_rule($('rule').value);
    if (!error) {
      showRuleError('');
      clearStopNotice();
      if (final) $('rule').value = game.rule_text;   // a blank box becomes the default rule
      return;
    }
    if (final) showRuleError(error);
    else ruleErrorTimer = setTimeout(() => showRuleError(error), 700);
  };
  $('rule').addEventListener('input', () => applyRule(false));
  $('rule').addEventListener('change', () => applyRule(true));

  $('maxgen').addEventListener('input', () => {
    game.set_max_generations($('maxgen').value);
    if (!game.stop_reason) clearStopNotice();
  });
  // Python clamps the limit to its allowed range; show the value that is really used once the user is done typing
  $('maxgen').addEventListener('change', () => { $('maxgen').value = game.max_generations; });

  $('speed').addEventListener('input', () => { $('speed-out').textContent = `${$('speed').value} gen/s`; });
  $('smooth').addEventListener('input', () => {
    const value = Number($('smooth').value);
    $('smooth-out').textContent = value === 0 ? 'Off' : `${value}%`;
    render();
  });

  $('highlight').addEventListener('change', updateHighlightUi);
  $('born-color').addEventListener('input', updateHighlightUi);
  $('died-color').addEventListener('input', updateHighlightUi);
  $('reset-colors').addEventListener('click', () => {
    $('born-color').value = defaultHighlight.born;
    $('died-color').value = defaultHighlight.died;
    updateHighlightUi();
  });

  // click or drag on the grid: this only works out which cell is under the pointer, Python does the painting
  const cellAt = (event) => {
    const rect = canvas.getBoundingClientRect();
    return [
      Math.floor(((event.clientY - rect.top) / rect.height) * size),
      Math.floor(((event.clientX - rect.left) / rect.width) * size),
    ];
  };
  let stroking = false;
  canvas.addEventListener('pointerdown', (event) => {
    canvas.setPointerCapture(event.pointerId);
    stroking = true;
    game.begin_paint(...cellAt(event));
    clearStopNotice();
    renderAfterEdit();
  });
  canvas.addEventListener('pointermove', (event) => {
    if (!stroking) return;
    // a fast drag skips cells between two events, so every event the browser grouped is passed on
    // (Python also fills in the cells between consecutive points)
    for (const e of event.getCoalescedEvents?.() ?? [event]) game.paint(...cellAt(e));
    renderAfterEdit();
  });
  const endStroke = () => { stroking = false; game.end_paint(); };
  canvas.addEventListener('pointerup', endStroke);
  canvas.addEventListener('pointercancel', endStroke);
}

// ---------- start ----------
async function main() {
  try {
    const pyodide = await loadPyodide();
    const source = await (await fetch('game_of_life.py', { cache: 'no-cache' })).text();
    pyodide.runPython(source);

    const py = pyodide.globals;
    game = py.get('game');

    // cell state numbers and the settings' limits come from Python, so nothing is repeated here
    DEAD = py.get('DEAD_CELL');
    LIVE = py.get('LIVE_CELL');
    const css = getComputedStyle(document.documentElement);
    const color = (name) => css.getPropertyValue(`--color-${name}`).trim();
    colors = { live: color('cell-live'), dead: color('cell-dead'), grid: color('cell-grid') };
    defaultHighlight = { born: color('cell-born'), died: color('cell-died') };
    $('born-color').value = defaultHighlight.born;
    $('died-color').value = defaultHighlight.died;

    sizeMin = py.get('MIN_SIZE');
    sizeMax = py.get('MAX_SIZE');
    $('size').min = sizeMin;
    $('size').max = sizeMax;
    $('size-hint').textContent = `size × size, ${sizeMin}–${sizeMax}`;
    $('rule').value = game.rule_text;
    // a link such as index.html?rule=B2/S (the table on the How it works page) opens the game with that rule
    const linkedRule = new URLSearchParams(location.search).get('rule');
    if (linkedRule !== null) {
      const error = game.set_rule(linkedRule);
      $('rule').value = game.rule_text;
      if (error) setStatus(`The linked rule was not used. ${error}`, true);
    }
    $('rules-range').textContent = `0–${py.get('MAX_NEIGHBORS')}`;
    $('maxgen').min = py.get('MIN_GENERATIONS');
    $('maxgen').max = py.get('MAX_GENERATIONS');
    $('maxgen-hint').textContent = `${$('maxgen').min}–${$('maxgen').max}`;
    $('maxgen').value = game.max_generations;

    wireControls();
    $('toggle').disabled = false;
    updateToggleButton();
    updateHighlightUi();   // also draws the first frame
    requestAnimationFrame(frame);
  } catch (error) {
    $('toggle').textContent = 'Failed to load';
    setStatus(`Could not start: ${error.message}. Serve this folder over http (python3 -m http.server) instead of opening the file directly.`, true);
  }
}

main();
