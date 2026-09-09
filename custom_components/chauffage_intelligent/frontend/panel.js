/**
 * Chauffage Intelligent - weekly schedule editor panel.
 *
 * Vanilla custom element: no build step, no dependencies. Home Assistant
 * injects `hass`, `narrow` and `panel` as properties (panel_custom contract)
 * and the element talks to the integration over the websocket API.
 */

const DAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"];
const DAYS_SHORT = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];

const SOURCE_LABELS = {
  planning: "Planning",
  manuel: "Manuel",
  defaut: "Hors plage",
  off: "Éteint",
};

/** Map a temperature to a colour: cold blue -> warm red. */
function temperatureColor(value) {
  if (value === null || value === undefined) return "transparent";
  const ratio = Math.min(1, Math.max(0, (value - 13) / 11));
  const hue = 215 - ratio * 205;
  return `hsl(${hue}, 68%, ${62 - ratio * 8}%)`;
}

function formatCellTime(index, stepMinutes) {
  const minutes = index * stepMinutes;
  const hh = String(Math.floor(minutes / 60)).padStart(2, "0");
  const mm = String(minutes % 60).padStart(2, "0");
  return `${hh}:${mm}`;
}

function formatNextChange(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("fr-FR", {
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const STYLES = `
  :host {
    display: block;
    height: 100%;
    background: var(--primary-background-color, #f5f5f5);
    color: var(--primary-text-color, #212121);
    font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
    --ci-border: var(--divider-color, rgba(127, 127, 127, 0.3));
  }
  .toolbar {
    display: flex;
    align-items: center;
    gap: 16px;
    height: 56px;
    padding: 0 16px;
    background: var(--app-header-background-color, var(--primary-color, #03a9f4));
    color: var(--app-header-text-color, #fff);
    font-size: 20px;
    font-weight: 400;
    box-sizing: border-box;
  }
  .content { padding: 16px; max-width: 1100px; margin: 0 auto; box-sizing: border-box; }
  .card {
    background: var(--card-background-color, #fff);
    border-radius: var(--ha-card-border-radius, 12px);
    box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0,0,0,.12));
    padding: 16px;
    margin-bottom: 16px;
  }
  .rooms { display: flex; flex-wrap: wrap; gap: 8px; }
  button {
    font: inherit;
    font-size: 14px;
    border: 1px solid var(--ci-border);
    border-radius: 20px;
    padding: 7px 16px;
    background: transparent;
    color: inherit;
    cursor: pointer;
  }
  button:hover:not(:disabled) { background: rgba(127,127,127,.12); }
  button:disabled { opacity: .45; cursor: default; }
  button.active {
    background: var(--primary-color, #03a9f4);
    border-color: var(--primary-color, #03a9f4);
    color: var(--text-primary-color, #fff);
  }
  button.primary {
    background: var(--primary-color, #03a9f4);
    border-color: var(--primary-color, #03a9f4);
    color: var(--text-primary-color, #fff);
  }
  .stats { display: flex; flex-wrap: wrap; gap: 24px; }
  .stat .label {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: .04em;
    color: var(--secondary-text-color, #727272);
  }
  .stat .value { font-size: 22px; font-weight: 500; margin-top: 2px; }
  .section-title {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: .04em;
    color: var(--secondary-text-color, #727272);
    margin-bottom: 8px;
  }
  .palette { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .swatch {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 7px 14px;
    border-radius: 20px;
    border: 2px solid transparent;
    background: rgba(127,127,127,.12);
    cursor: pointer;
    font-size: 14px;
  }
  .swatch .dot {
    width: 14px; height: 14px; border-radius: 50%;
    border: 1px solid var(--ci-border);
  }
  .swatch.selected { border-color: var(--primary-text-color, #212121); }
  .swatch input {
    width: 58px; font: inherit; font-size: 14px; padding: 2px 4px;
    border: 1px solid var(--ci-border); border-radius: 4px;
    background: var(--card-background-color, #fff); color: inherit;
  }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .spacer { flex: 1; }
  .grid-wrap { overflow-x: auto; }
  .grid {
    display: grid;
    grid-template-columns: 52px repeat(7, minmax(58px, 1fr));
    gap: 1px;
    min-width: 520px;
    touch-action: none;
    user-select: none;
  }
  .head {
    text-align: center;
    font-size: 13px;
    font-weight: 500;
    padding: 6px 0;
    position: sticky;
    top: 0;
    background: var(--card-background-color, #fff);
    z-index: 1;
  }
  .head button { border: none; padding: 4px 8px; border-radius: 6px; font-size: 13px; }
  .time {
    font-size: 11px;
    color: var(--secondary-text-color, #727272);
    text-align: right;
    padding-right: 8px;
    line-height: 15px;
    height: 15px;
  }
  .cell {
    height: 15px;
    background: var(--ci-empty, rgba(127,127,127,.10));
    cursor: crosshair;
  }
  .cell.hour { box-shadow: inset 0 1px 0 var(--ci-border); }
  .legend {
    display: flex; gap: 16px; flex-wrap: wrap;
    font-size: 12px; color: var(--secondary-text-color, #727272);
    margin-top: 12px;
  }
  .legend span { display: inline-flex; align-items: center; gap: 6px; }
  .legend .dot { width: 12px; height: 12px; border-radius: 3px; }
  .empty { text-align: center; padding: 48px 16px; color: var(--secondary-text-color, #727272); }
  .dirty { color: var(--warning-color, #ffa600); font-size: 14px; }
`;

class ChauffageIntelligentPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._rooms = [];
    this._meta = { step_minutes: 30, slots_per_day: 48, days: 7 };
    this._currentId = null;
    this._grid = null;
    this._baseline = null;
    this._paintValue = null;
    this._customTemp = 21;
    this._painting = false;
    this._loaded = false;
    this._cells = [];

    this._onPointerDown = this._onPointerDown.bind(this);
    this._onPointerMove = this._onPointerMove.bind(this);
    this._onPointerUp = this._onPointerUp.bind(this);
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._loaded) {
      this._loaded = true;
      this._loadRooms();
    }
  }

  get hass() {
    return this._hass;
  }

  set narrow(value) {
    this._narrow = value;
  }

  set panel(value) {
    this._panel = value;
  }

  connectedCallback() {
    window.addEventListener("pointerup", this._onPointerUp);
    this._render();
  }

  disconnectedCallback() {
    window.removeEventListener("pointerup", this._onPointerUp);
  }

  get _room() {
    return this._rooms.find((room) => room.id === this._currentId) || null;
  }

  get _isDirty() {
    if (!this._grid || !this._baseline) return false;
    return JSON.stringify(this._grid) !== JSON.stringify(this._baseline);
  }

  // ----------------------------------------------------------------
  // Data
  // ----------------------------------------------------------------

  async _loadRooms() {
    try {
      const result = await this._hass.callWS({ type: "chauffage_intelligent/rooms" });
      this._rooms = result.rooms || [];
      this._meta = result;
      // The selected room may have been deleted from the integration options.
      if (!this._room) {
        this._currentId = this._rooms.length ? this._rooms[0].id : null;
        this._grid = null;
        this._baseline = null;
        if (this._currentId) {
          await this._loadSchedule();
          return;
        }
      }
      this._render();
    } catch (err) {
      this._error = String(err.message || err);
      this._render();
    }
  }

  async _loadSchedule() {
    if (!this._currentId) return;
    try {
      const result = await this._hass.callWS({
        type: "chauffage_intelligent/schedule/get",
        piece_id: this._currentId,
      });
      this._grid = result.grid;
      this._baseline = JSON.parse(JSON.stringify(result.grid));
      const room = this._room;
      if (room && room.temperatures && this._paintValue === null) {
        this._paintValue = Number(room.temperatures.confort);
      }
    } catch (err) {
      this._error = String(err.message || err);
    }
    this._render();
  }

  async _save() {
    try {
      const result = await this._hass.callWS({
        type: "chauffage_intelligent/schedule/set",
        piece_id: this._currentId,
        grid: this._grid,
      });
      this._grid = result.grid;
      this._baseline = JSON.parse(JSON.stringify(result.grid));
      await this._loadRooms();
    } catch (err) {
      this._error = String(err.message || err);
      this._render();
    }
  }

  async _selectRoom(id) {
    if (this._isDirty && !confirm("Des modifications non enregistrées seront perdues. Continuer ?")) {
      return;
    }
    this._currentId = id;
    this._paintValue = null;
    await this._loadSchedule();
  }

  async _copyToRoom(targetId) {
    if (this._isDirty) {
      await this._save();
    }
    try {
      await this._hass.callWS({
        type: "chauffage_intelligent/schedule/copy",
        from_piece: this._currentId,
        to_pieces: [targetId],
      });
    } catch (err) {
      this._error = String(err.message || err);
      this._render();
    }
  }

  // ----------------------------------------------------------------
  // Painting
  // ----------------------------------------------------------------

  _cellFromEvent(event) {
    // Point hit-testing is what makes drag painting work on touch, where
    // pointermove keeps reporting the element the gesture started on.
    let node = null;
    if (this.shadowRoot.elementFromPoint) {
      node = this.shadowRoot.elementFromPoint(event.clientX, event.clientY);
    }
    if (!node || !node.classList || !node.classList.contains("cell")) {
      node = event.target;
    }
    if (!node || !node.classList || !node.classList.contains("cell")) return null;
    return node;
  }

  _paintCell(node) {
    const day = Number(node.dataset.day);
    const index = Number(node.dataset.index);
    if (this._grid[day][index] === this._paintValue) return;
    this._grid[day][index] = this._paintValue;
    this._paintNode(node, this._paintValue);
    this._updateDirtyState();
  }

  _paintNode(node, value) {
    node.style.background = value === null ? "" : temperatureColor(value);
    node.title = `${DAYS[Number(node.dataset.day)]} ${formatCellTime(
      Number(node.dataset.index),
      this._meta.step_minutes
    )} — ${value === null ? "hors plage" : `${value}°C`}`;
  }

  _onPointerDown(event) {
    const node = this._cellFromEvent(event);
    if (!node) return;
    event.preventDefault();
    this._painting = true;
    this._paintCell(node);
  }

  _onPointerMove(event) {
    if (!this._painting) return;
    const node = this._cellFromEvent(event);
    if (node) this._paintCell(node);
  }

  _onPointerUp() {
    this._painting = false;
  }

  _fillDay(day) {
    for (let i = 0; i < this._meta.slots_per_day; i += 1) {
      this._grid[day][i] = this._paintValue;
    }
    this._render();
  }

  _copyDayToWeek(day) {
    const row = this._grid[day];
    for (let d = 0; d < this._meta.days; d += 1) {
      this._grid[d] = row.slice();
    }
    this._render();
  }

  _clearAll() {
    this._grid = this._grid.map((row) => row.map(() => null));
    this._render();
  }

  _updateDirtyState() {
    const badge = this.shadowRoot.getElementById("dirty");
    const save = this.shadowRoot.getElementById("save");
    const reset = this.shadowRoot.getElementById("reset");
    const dirty = this._isDirty;
    if (badge) badge.textContent = dirty ? "Modifications non enregistrées" : "";
    if (save) save.disabled = !dirty;
    if (reset) reset.disabled = !dirty;
  }

  // ----------------------------------------------------------------
  // Rendering
  // ----------------------------------------------------------------

  _render() {
    const root = this.shadowRoot;
    root.innerHTML = "";

    const style = document.createElement("style");
    style.textContent = STYLES;
    root.appendChild(style);

    const toolbar = document.createElement("div");
    toolbar.className = "toolbar";
    toolbar.textContent = "Chauffage — Planning hebdomadaire";
    root.appendChild(toolbar);

    const content = document.createElement("div");
    content.className = "content";
    root.appendChild(content);

    if (this._error) {
      content.appendChild(this._card(`Erreur : ${this._error}`));
    }

    if (!this._rooms.length) {
      const empty = document.createElement("div");
      empty.className = "card empty";
      empty.textContent =
        "Aucune pièce configurée. Ajoutez-en une depuis Paramètres → Appareils et services → Chauffage Intelligent.";
      content.appendChild(empty);
      return;
    }

    content.appendChild(this._renderRooms());
    if (this._room) {
      content.appendChild(this._renderStats());
      if (this._grid) {
        content.appendChild(this._renderEditor());
      }
    }
  }

  _card(text) {
    const card = document.createElement("div");
    card.className = "card";
    card.textContent = text;
    return card;
  }

  _renderRooms() {
    const card = document.createElement("div");
    card.className = "card";

    const title = document.createElement("div");
    title.className = "section-title";
    title.textContent = "Pièce";
    card.appendChild(title);

    const rooms = document.createElement("div");
    rooms.className = "rooms";
    this._rooms.forEach((room) => {
      const button = document.createElement("button");
      button.textContent = room.name;
      if (room.id === this._currentId) button.classList.add("active");
      button.addEventListener("click", () => this._selectRoom(room.id));
      rooms.appendChild(button);
    });
    card.appendChild(rooms);

    return card;
  }

  _renderStats() {
    const room = this._room;
    const card = document.createElement("div");
    card.className = "card stats";

    const stats = [
      ["Température", room.temperature === null || room.temperature === undefined
        ? "—" : `${Number(room.temperature).toFixed(1)}°C`],
      ["Consigne", room.consigne === null || room.consigne === undefined
        ? "—" : `${Number(room.consigne).toFixed(1)}°C`],
      ["Source", SOURCE_LABELS[room.source] || "—"],
      ["Créneau", room.creneau_actuel || "—"],
      ["Prochain changement", formatNextChange(room.prochain_changement)],
    ];

    stats.forEach(([label, value]) => {
      const stat = document.createElement("div");
      stat.className = "stat";
      const labelNode = document.createElement("div");
      labelNode.className = "label";
      labelNode.textContent = label;
      const valueNode = document.createElement("div");
      valueNode.className = "value";
      valueNode.textContent = value;
      stat.appendChild(labelNode);
      stat.appendChild(valueNode);
      card.appendChild(stat);
    });

    return card;
  }

  _renderEditor() {
    const card = document.createElement("div");
    card.className = "card";

    card.appendChild(this._renderPalette());
    card.appendChild(this._renderActions());
    card.appendChild(this._renderGrid());
    card.appendChild(this._renderLegend());

    return card;
  }

  _renderPalette() {
    const room = this._room;
    const wrap = document.createElement("div");

    const title = document.createElement("div");
    title.className = "section-title";
    title.textContent = "Température à appliquer";
    wrap.appendChild(title);

    const palette = document.createElement("div");
    palette.className = "palette";

    const entries = [
      ["Confort", Number(room.temperatures.confort)],
      ["Éco", Number(room.temperatures.eco)],
      ["Hors-gel", Number(room.temperatures.hors_gel)],
    ];

    entries.forEach(([label, value]) => {
      palette.appendChild(
        this._swatch(`${label} ${value}°`, value, this._paintValue === value)
      );
    });

    // Free value.
    const custom = document.createElement("label");
    custom.className = "swatch";
    if (this._paintValue === this._customTemp) custom.classList.add("selected");
    const dot = document.createElement("span");
    dot.className = "dot";
    dot.style.background = temperatureColor(this._customTemp);
    const input = document.createElement("input");
    input.type = "number";
    input.min = "5";
    input.max = "30";
    input.step = "0.5";
    input.value = String(this._customTemp);
    input.addEventListener("input", () => {
      const value = Number(input.value);
      if (Number.isNaN(value)) return;
      this._customTemp = value;
      this._paintValue = value;
      dot.style.background = temperatureColor(value);
      this._markSelected(custom);
    });
    input.addEventListener("click", (event) => event.stopPropagation());
    custom.appendChild(dot);
    custom.appendChild(input);
    const unit = document.createElement("span");
    unit.textContent = "°C";
    custom.appendChild(unit);
    custom.addEventListener("click", () => {
      this._paintValue = this._customTemp;
      this._markSelected(custom);
    });
    palette.appendChild(custom);

    // Erase.
    palette.appendChild(this._swatch("Hors plage", null, this._paintValue === null));

    wrap.appendChild(palette);
    return wrap;
  }

  _swatch(label, value, selected) {
    const node = document.createElement("div");
    node.className = "swatch" + (selected ? " selected" : "");
    const dot = document.createElement("span");
    dot.className = "dot";
    dot.style.background = value === null ? "transparent" : temperatureColor(value);
    node.appendChild(dot);
    const text = document.createElement("span");
    text.textContent = label;
    node.appendChild(text);
    node.addEventListener("click", () => {
      this._paintValue = value;
      this._markSelected(node);
    });
    return node;
  }

  _markSelected(node) {
    this.shadowRoot
      .querySelectorAll(".swatch")
      .forEach((swatch) => swatch.classList.remove("selected"));
    node.classList.add("selected");
  }

  _renderActions() {
    const wrap = document.createElement("div");
    wrap.className = "actions";
    wrap.style.margin = "16px 0";

    const clear = document.createElement("button");
    clear.textContent = "Tout effacer";
    clear.addEventListener("click", () => this._clearAll());
    wrap.appendChild(clear);

    const others = this._rooms.filter((room) => room.id !== this._currentId);
    if (others.length) {
      const copy = document.createElement("select");
      copy.style.cssText =
        "font:inherit;font-size:14px;padding:7px 10px;border-radius:20px;" +
        "border:1px solid var(--ci-border);background:transparent;color:inherit;";
      const placeholder = document.createElement("option");
      placeholder.textContent = "Copier vers…";
      placeholder.value = "";
      copy.appendChild(placeholder);
      others.forEach((room) => {
        const option = document.createElement("option");
        option.value = room.id;
        option.textContent = room.name;
        copy.appendChild(option);
      });
      copy.addEventListener("change", () => {
        if (copy.value) this._copyToRoom(copy.value);
        copy.value = "";
      });
      wrap.appendChild(copy);
    }

    const spacer = document.createElement("div");
    spacer.className = "spacer";
    wrap.appendChild(spacer);

    const dirty = document.createElement("span");
    dirty.id = "dirty";
    dirty.className = "dirty";
    dirty.textContent = this._isDirty ? "Modifications non enregistrées" : "";
    wrap.appendChild(dirty);

    const reset = document.createElement("button");
    reset.id = "reset";
    reset.textContent = "Annuler";
    reset.disabled = !this._isDirty;
    reset.addEventListener("click", () => {
      this._grid = JSON.parse(JSON.stringify(this._baseline));
      this._render();
    });
    wrap.appendChild(reset);

    const save = document.createElement("button");
    save.id = "save";
    save.className = "primary";
    save.textContent = "Enregistrer";
    save.disabled = !this._isDirty;
    save.addEventListener("click", () => this._save());
    wrap.appendChild(save);

    return wrap;
  }

  _renderGrid() {
    const wrap = document.createElement("div");
    wrap.className = "grid-wrap";

    const grid = document.createElement("div");
    grid.className = "grid";
    grid.addEventListener("pointerdown", this._onPointerDown);
    grid.addEventListener("pointermove", this._onPointerMove);

    // Header row: corner + day names (click a day name to fill it).
    const corner = document.createElement("div");
    corner.className = "head";
    grid.appendChild(corner);

    for (let day = 0; day < this._meta.days; day += 1) {
      const head = document.createElement("div");
      head.className = "head";

      const fill = document.createElement("button");
      fill.textContent = window.innerWidth < 700 ? DAYS_SHORT[day] : DAYS[day];
      fill.title = "Remplir la journée avec la température sélectionnée";
      fill.addEventListener("click", () => this._fillDay(day));
      head.appendChild(fill);

      const spread = document.createElement("button");
      spread.textContent = "⇥";
      spread.title = "Copier cette journée sur toute la semaine";
      spread.addEventListener("click", () => this._copyDayToWeek(day));
      head.appendChild(spread);

      grid.appendChild(head);
    }

    this._cells = [];
    for (let index = 0; index < this._meta.slots_per_day; index += 1) {
      const isHour = (index * this._meta.step_minutes) % 60 === 0;

      const time = document.createElement("div");
      time.className = "time";
      time.textContent = isHour ? formatCellTime(index, this._meta.step_minutes) : "";
      grid.appendChild(time);

      for (let day = 0; day < this._meta.days; day += 1) {
        const cell = document.createElement("div");
        cell.className = "cell" + (isHour ? " hour" : "");
        cell.dataset.day = String(day);
        cell.dataset.index = String(index);
        this._paintNode(cell, this._grid[day][index]);
        grid.appendChild(cell);
        this._cells.push(cell);
      }
    }

    wrap.appendChild(grid);
    return wrap;
  }

  _renderLegend() {
    const legend = document.createElement("div");
    legend.className = "legend";

    const room = this._room;
    const items = [
      ["Hors plage → " + Number(room.temperatures.eco).toFixed(1) + "°C (éco)", null],
      ["Froid", 14],
      ["Tempéré", 19],
      ["Chaud", 23],
    ];

    items.forEach(([label, value]) => {
      const item = document.createElement("span");
      const dot = document.createElement("span");
      dot.className = "dot";
      dot.style.background = value === null
        ? "var(--ci-empty, rgba(127,127,127,.10))"
        : temperatureColor(value);
      item.appendChild(dot);
      const text = document.createElement("span");
      text.textContent = label;
      item.appendChild(text);
      legend.appendChild(item);
    });

    return legend;
  }
}

customElements.define("chauffage-intelligent-panel", ChauffageIntelligentPanel);
