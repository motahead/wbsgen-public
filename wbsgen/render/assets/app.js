(() => {
  const chartBody = document.querySelector('.chart-body');
  const rowHeight = Number(chartBody?.dataset.rowHeight || '32');
  const chartFooterHeight = Number(chartBody?.dataset.footerHeight || '0');
  const overlay = document.querySelector('.gantt-overlay');
  const collapseState = new Set();
  let milestoneLines = null;
  const paneResizeHandle = document.querySelector('.pane-resize-handle');
  const taskNameResizeHandle = document.querySelector('.task-name-resize-handle');
  const assigneeResizeHandle = document.querySelector('.assignee-resize-handle');
  const leftHead = document.querySelector('.left-head');
  const queryParams = new URLSearchParams(window.location.search);
  const columnWidthOverrides = queryColumnWidths(queryParams);
  const widthModel = window.WbsWidthModel.create({
    idColumnWidth: 58,
    defaultTaskNameWidth: columnWidthOverrides.name ?? Number(leftHead?.dataset.taskNameWidth || '220'),
    defaultAssigneeWidth: columnWidthOverrides.assignee ?? Number(leftHead?.dataset.assigneeWidth || '56'),
    defaultCommentWidth: columnWidthOverrides.comment ?? Number(leftHead?.dataset.commentWidth || '220'),
    columnWidths: {'planned-period': 76, 'actual-period': 76, progress: 52, 'expected-progress': 52, issue: 58},
  });
  const analysisColumnWidths = {progress: 52, 'expected-progress': 52, delta: 56, delay: 76, pace: 80};
  const wbsViewTabs = Array.from(document.querySelectorAll('[data-wbs-view-target]'));
  let currentWbsView = 'standard';
  const leftPaneWidths = {};
  const leftPaneManuallyResized = {standard: false, analysis: false};
  const viewMenu = document.querySelector('.view-menu');
  const app = document.querySelector('.app');
  const workspace = document.querySelector('.workspace');
  const scrollPanes = document.querySelectorAll('.left-pane, .right-pane');
  const layerTargets = ['inazuma', 'actual', 'milestone'];
  const columnKeyMap = {assignee: 'assignee', planned: 'planned-period', actual: 'actual-period', progress: 'progress', expected: 'expected-progress', issue: 'issue', comment: 'comment'};
  const displayLayerKeys = ['inazuma', 'actual', 'highlight', 'tooltip', 'delayHighlight', 'milestone'];
  const hiddenLayers = new Set();
  const dateCells = Array.from(document.querySelectorAll('.date-cell'));
  const leftRows = Array.from(document.querySelectorAll('.wbs-row[data-task-id]'));
  const ganttRows = Array.from(document.querySelectorAll('.gantt-row[data-task-id]'));
  const interactionLayer = document.querySelector('.interaction-layer');
  const highlightToggle = document.querySelector('[data-highlight-toggle]');
  const tooltipToggle = document.querySelector('[data-tooltip-toggle]');
  const delayHighlightToggle = document.querySelector('[data-delay-highlight-toggle]');
  const sourceDownload = document.querySelector('[data-source-download]');
  const shareLinkCopy = document.querySelector('[data-share-link-copy]');
  const searchSummary = document.querySelector('[data-search-summary]');
  const searchDrawer = document.querySelector('[data-search-drawer]');
  const searchKeyword = document.querySelector('[data-search-keyword]');
  const searchFieldInputs = Array.from(document.querySelectorAll('[data-search-field]'));
  const searchModeInputs = Array.from(document.querySelectorAll('[data-search-mode]'));
  const searchClear = document.querySelector('[data-search-clear]');
  const searchClose = document.querySelector('[data-search-close]');
  const tooltip = document.querySelector('.app-tooltip');
  const dayWidth = Number(chartBody?.dataset.dayWidth || '32');
  const pinnedTaskIds = new Set();
  const pinnedDateIndexes = new Set();
  let highlightsEnabled = highlightToggle ? highlightToggle.checked : true;
  let tooltipsEnabled = tooltipToggle ? tooltipToggle.checked : true;
  let delayHighlightEnabled = delayHighlightToggle ? delayHighlightToggle.checked : true;
  let hoveredTaskId = null;
  let hoveredDateIndex = null;
  let shareLinkLabelTimeout = null;
  let activeTooltipTarget = null;
  const searchFieldKeys = ['name', 'comment', 'assignee', 'issue'];
  const searchState = {keyword: '', fields: new Set(searchFieldKeys), mode: 'filter'};
  let directMatchTaskIds = new Set();
  let filterVisibleTaskIds = new Set();

  function ensureTooltipElement() {
    if (tooltip) {
      tooltip.setAttribute('role', 'tooltip');
      tooltip.setAttribute('aria-hidden', tooltip.classList.contains('is-visible') ? 'false' : 'true');
      return tooltip;
    }
    const element = document.createElement('div');
    element.className = 'app-tooltip';
    element.setAttribute('role', 'tooltip');
    element.setAttribute('aria-hidden', 'true');
    (app || document.body).appendChild(element);
    return element;
  }

  const tooltipElement = ensureTooltipElement();

  function isDescendant(taskId, ancestorId) {
    return taskId === ancestorId || taskId.startsWith(`${ancestorId}.`);
  }

  function visibleRows() {
    return Array.from(document.querySelectorAll('.gantt-row[data-task-id]')).filter(
      (row) => !row.classList.contains('is-collapsed-descendant') && !row.classList.contains('is-search-filtered-out')
    );
  }

  function normalizeSearchText(value, field) {
    const text = String(value || '').trim().toLocaleLowerCase();
    return field === 'issue' ? text.replace(/^#/, '') : text;
  }

  function searchValueForRow(row, field) {
    return row.dataset[`search${field[0].toUpperCase()}${field.slice(1)}`] || '';
  }

  function parseSearchTerms(keyword) {
    const includes = [];
    const excludes = [];
    String(keyword || '').trim().split(/\s+/).filter(Boolean).forEach((term) => {
      if (term.startsWith('-')) {
        const excluded = term.slice(1);
        if (excluded) {
          excludes.push(excluded);
        }
      } else {
        includes.push(term);
      }
    });
    return {includes, excludes};
  }

  function hasSearchTerms() {
    const terms = parseSearchTerms(searchState.keyword);
    return Boolean(terms.includes.length || terms.excludes.length);
  }

  function rowMatchesSearchTerm(row, term) {
    return Array.from(searchState.fields).some((field) =>
      normalizeSearchText(searchValueForRow(row, field), field)
        .includes(normalizeSearchText(term, field))
    );
  }

  function taskMatchesSearch(row) {
    if (!hasSearchTerms()) {
      return false;
    }
    const terms = parseSearchTerms(searchState.keyword);
    return terms.includes.every((term) => rowMatchesSearchTerm(row, term))
      && terms.excludes.every((term) => !rowMatchesSearchTerm(row, term));
  }

  function addTaskAndAncestors(taskId, target) {
    const parts = taskId.split('.');
    while (parts.length) {
      target.add(parts.join('.'));
      parts.pop();
    }
  }

  function updateSearchMatches() {
    directMatchTaskIds = new Set(
      leftRows.filter((row) => taskMatchesSearch(row)).map((row) => row.dataset.taskId)
    );
    filterVisibleTaskIds = new Set();
    directMatchTaskIds.forEach((taskId) => addTaskAndAncestors(taskId, filterVisibleTaskIds));
  }

  function syncSearchControls() {
    if (searchKeyword) {
      searchKeyword.value = searchState.keyword;
    }
    searchFieldInputs.forEach((input) => {
      input.checked = input.dataset.searchField === 'all'
        ? searchState.fields.size === searchFieldKeys.length
        : searchState.fields.has(input.dataset.searchField);
    });
    searchModeInputs.forEach((input) => {
      input.checked = input.dataset.searchMode === searchState.mode;
    });
    if (searchSummary) {
      searchSummary.textContent = `検索 ${directMatchTaskIds.size}件`;
    }
  }

  function renderSearchHighlights() {
    const active = hasSearchTerms() && searchState.mode === 'highlight';
    leftRows.forEach((row) => row.classList.toggle('is-search-match', active && directMatchTaskIds.has(row.dataset.taskId)));
    ganttRows.forEach((row) => row.classList.toggle('is-search-match', active && directMatchTaskIds.has(row.dataset.taskId)));
  }

  function refreshSearchResults() {
    updateSearchMatches();
    syncSearchControls();
    updateRowVisibility();
  }

  function setSearchDrawerOpen(open) {
    if (!searchDrawer || !searchSummary) {
      return;
    }
    searchDrawer.hidden = !open;
    searchSummary.setAttribute('aria-expanded', String(open));
  }

  function initializeSearchState(params) {
    searchState.keyword = (params.get('keyword') || '').trim();
    const fields = (params.get('fields') || '').split(',').filter((field) => searchFieldKeys.includes(field));
    searchState.fields = new Set(fields.length ? fields : searchFieldKeys);
    searchState.mode = params.get('mode') === 'highlight' ? 'highlight' : 'filter';
    updateSearchMatches();
    syncSearchControls();
  }

  function dateIndexForCell(cell) {
    return dateCells.indexOf(cell);
  }

  function sortedNumbers(values) {
    return Array.from(values).sort((a, b) => a - b);
  }

  function clearHighlightClasses() {
    leftRows.forEach((row) => row.classList.remove('is-hovered-task', 'is-pinned-task'));
    ganttRows.forEach((row) => row.classList.remove('is-hovered-task', 'is-pinned-task'));
    dateCells.forEach((cell) => cell.classList.remove('is-hovered-date', 'is-pinned-date'));
    if (interactionLayer) {
      interactionLayer.textContent = '';
    }
  }

  function taskTop(taskId) {
    const row = visibleRows().find((candidate) => candidate.dataset.taskId === taskId);
    return row ? row.offsetTop : null;
  }

  function appendRowHighlight(taskId, pinned) {
    if (!interactionLayer) {
      return;
    }
    const top = taskTop(taskId);
    if (top === null) {
      return;
    }
    const row = document.createElement('div');
    row.className = `highlight-row${pinned ? ' is-pinned' : ''}`;
    row.style.top = `${top}px`;
    interactionLayer.appendChild(row);
  }

  function appendDateHighlight(dateIndex, pinned) {
    if (!interactionLayer) {
      return;
    }
    const column = document.createElement('div');
    column.className = `highlight-date${pinned ? ' is-pinned' : ''}`;
    column.style.left = `${dateIndex * dayWidth}px`;
    interactionLayer.appendChild(column);
  }

  function appendCrossHighlight(taskId, dateIndex, pinned) {
    if (!interactionLayer) {
      return;
    }
    const top = taskTop(taskId);
    if (top === null || !Number.isInteger(dateIndex)) {
      return;
    }
    const cross = document.createElement('div');
    cross.className = `highlight-cross${pinned ? ' is-pinned' : ''}`;
    cross.style.left = `${dateIndex * dayWidth}px`;
    cross.style.top = `${top}px`;
    interactionLayer.appendChild(cross);
  }

  function renderHighlights() {
    if (!highlightsEnabled) {
      clearHighlightClasses();
      return;
    }
    leftRows.forEach((row) => {
      row.classList.toggle('is-hovered-task', row.dataset.taskId === hoveredTaskId);
      row.classList.toggle('is-pinned-task', pinnedTaskIds.has(row.dataset.taskId));
    });
    ganttRows.forEach((row) => {
      row.classList.toggle('is-hovered-task', row.dataset.taskId === hoveredTaskId);
      row.classList.toggle('is-pinned-task', pinnedTaskIds.has(row.dataset.taskId));
    });
    dateCells.forEach((cell, index) => {
      cell.classList.toggle('is-hovered-date', index === hoveredDateIndex);
      cell.classList.toggle('is-pinned-date', pinnedDateIndexes.has(index));
    });
    if (!interactionLayer) {
      return;
    }
    interactionLayer.textContent = '';
    sortedNumbers(pinnedDateIndexes).forEach((dateIndex) => appendDateHighlight(dateIndex, true));
    Array.from(pinnedTaskIds).forEach((taskId) => appendRowHighlight(taskId, true));
    if (hoveredDateIndex !== null) {
      appendDateHighlight(hoveredDateIndex, false);
    }
    if (hoveredTaskId !== null) {
      appendRowHighlight(hoveredTaskId, false);
    }
    Array.from(pinnedTaskIds).forEach((taskId) => {
      sortedNumbers(pinnedDateIndexes).forEach((dateIndex) => appendCrossHighlight(taskId, dateIndex, true));
    });
    if (hoveredTaskId !== null && hoveredDateIndex !== null) {
      appendCrossHighlight(hoveredTaskId, hoveredDateIndex, false);
    }
  }

  function updateToggleButtons() {
    document.querySelectorAll('.tree-toggle[data-task-id]').forEach((button) => {
      const taskId = button.dataset.taskId;
      const collapsed = collapseState.has(taskId);
      button.textContent = collapsed ? '▸' : '▾';
      button.title = collapsed ? '子タスクを展開する' : '子タスクを折りたたむ';
      button.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    });
  }

  function updateChartHeight() {
    if (!chartBody || !overlay) {
      return;
    }
    const height = visibleRows().length * rowHeight + chartFooterHeight;
    chartBody.style.height = `${height}px`;
    overlay.setAttribute('height', String(height));
    overlay.setAttribute('viewBox', `0 0 ${Number(chartBody.dataset.chartWidth || overlay.getAttribute('width') || '0')} ${height}`);
  }

  function updateInazuma() {
    if (!overlay || !chartBody) {
      return;
    }
    if (milestoneLines === null) {
      milestoneLines = Array.from(overlay.querySelectorAll('line.milestone-line')).map((line) => ({
        x: line.getAttribute('x1'),
        date: line.dataset.date || '',
      }));
    }
    const statusX = Number(chartBody.dataset.statusX || '0');
    const rows = visibleRows();
    const points = [`${statusX},0`];
    const circles = [];
    rows.forEach((row) => {
      const progressX = row.dataset.progressX;
      if (!progressX) {
        return;
      }
      const centerY = Math.round(row.offsetTop + row.offsetHeight / 2);
      points.push(`${progressX},${centerY}`);
      circles.push(`<circle class="gantt-progress-point" cx="${progressX}" cy="${centerY}" r="3" data-task-id="${row.dataset.taskId}" />`);
    });
    points.push(`${statusX},${rows.length * rowHeight}`);
    const chartHeight = overlay.getAttribute('height');
    const milestoneLineMarkup = milestoneLines.map((item) => `<line class="milestone-line" x1="${item.x}" y1="0" x2="${item.x}" y2="${chartHeight}" data-kind="milestone-line" data-date="${item.date}" />`).join('');
    overlay.innerHTML = `${milestoneLineMarkup}<polyline class="gantt-inazuma" points="${points.join(' ')}" data-kind="inazuma" />${circles.join('')}`;
  }

  function updateRowVisibility() {
    const rows = Array.from(document.querySelectorAll('.wbs-row[data-task-id], .gantt-row[data-task-id]'));
    rows.forEach((row) => {
      const taskId = row.dataset.taskId;
      const collapsed = Array.from(collapseState).some((ancestorId) => ancestorId !== taskId && isDescendant(taskId, ancestorId));
      const filteredOut = hasSearchTerms()
        && searchState.mode === 'filter'
        && !filterVisibleTaskIds.has(taskId);
      row.classList.toggle('is-collapsed-descendant', collapsed);
      row.classList.toggle('is-search-filtered-out', filteredOut);
    });
    updateToggleButtons();
    updateChartHeight();
    updateInazuma();
    renderSearchHighlights();
    renderHighlights();
  }

  function setCollapsed(taskId, collapsed) {
    if (collapsed) {
      collapseState.add(taskId);
    } else {
      collapseState.delete(taskId);
    }
    updateRowVisibility();
  }

  function applyResizableWidths() {
    document.documentElement.style.setProperty('--task-name-w', `${widthModel.getTaskNameWidth()}px`);
    document.documentElement.style.setProperty('--assignee-w', `${widthModel.getAssigneeWidth()}px`);
    document.documentElement.style.setProperty('--comment-w', `${widthModel.getCommentWidth()}px`);
    document.documentElement.style.setProperty('--left-w', `${widthModel.getLeftPaneWidth()}px`);
  }

  function updateColumnVisibilityUI(column) {
    const hidden = widthModel.isColumnHidden(column);
    document.querySelectorAll(`[data-column="${column}"]`).forEach((cell) => {
      cell.classList.toggle('is-hidden-column', hidden);
    });
    document.querySelectorAll(`[data-column-visibility-toggle="${column}"]`).forEach((checkbox) => {
      checkbox.checked = !hidden;
    });
  }

  function setColumnHidden(column, hidden) {
    if (widthModel.isColumnHidden(column) === hidden) {
      return;
    }
    widthModel.setColumnHidden(column, hidden);
    updateColumnVisibilityUI(column);
    applyResizableWidths();
  }

  const columnLabels = {assignee: '担当者', 'planned-period': '計画', 'actual-period': '実績', progress: '進捗', 'expected-progress': '期待', issue: 'Issue', comment: 'コメント', delta: '差分', delay: '遅れ営業日', pace: '必要ペース'};
  const defaultColumnOrders = {
    standard: ['assignee', 'planned-period', 'actual-period', 'progress', 'expected-progress', 'issue'],
    analysis: ['assignee', 'progress', 'expected-progress', 'delta', 'delay', 'pace'],
  };
  const columnOrders = {standard: [], analysis: []};

  function normalizeColumnOrder(order, defaults) {
    const specified = Array.isArray(order) ? order.filter((column) => defaults.includes(column)) : [];
    return specified.concat(defaults.filter((column) => !specified.includes(column)));
  }

  function applyColumnOrder(view) {
    const order = columnOrders[view];
    [leftHead, ...leftRows].forEach((container) => {
      const anchor = view === 'standard'
        ? container.querySelector('[data-column="comment"]')
        : container.querySelector('.milestone-cell');
      order.forEach((column) => {
        const cell = container.querySelector(`[data-column="${column}"]`);
        if (cell) {
          if (anchor) {
            container.insertBefore(cell, anchor);
          } else {
            container.append(cell);
          }
        }
      });
    });
    renderColumnSettings();
    applyResizableWidths();
  }

  function renderColumnSettings() {
    ['standard', 'analysis'].forEach((view) => {
      const target = document.querySelector(`[data-column-settings="${view}"]`);
      if (!target) return;
      const order = columnOrders[view];
      target.innerHTML = `<div class="column-settings-header"><span>項目</span><span>${view === 'standard' ? '表示' : ''}</span><span>順序</span></div>` + order.map((column, index) => {
        const visibility = view === 'standard' ? `<label><input type="checkbox" data-column-visibility-toggle="${column}" ${widthModel.isColumnHidden(column) ? '' : 'checked'}>表示</label>` : '<span></span>';
        const controls = `<span class="column-order-controls"><button class="control-button column-order-button" data-column-order="${column}" data-direction="up" ${index === 0 ? 'disabled' : ''}>↑</button><button class="control-button column-order-button" data-column-order="${column}" data-direction="down" ${index === order.length - 1 ? 'disabled' : ''}>↓</button></span>`;
        return `<div class="column-settings-row"><span>${columnLabels[column]}</span>${visibility}${controls}</div>`;
      }).join('') + (view === 'standard' ? `<div class="column-settings-row"><span>コメント</span><label><input type="checkbox" data-column-visibility-toggle="comment" ${widthModel.isColumnHidden('comment') ? '' : 'checked'}>表示</label><span></span></div>` : '');
    });
    updateColumnSettingsLabelWidths();
  }

  function updateColumnSettingsLabelWidths() {
    document.querySelectorAll('.column-settings').forEach((settings) => {
      const rows = Array.from(settings.querySelectorAll('.column-settings-row'));
      const sample = rows[0];
      if (!sample) {
        return;
      }
      const style = getComputedStyle(sample);
      const canvas = document.createElement('canvas');
      const context = canvas.getContext('2d');
      context.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
      const widest = Math.max(...rows.map((row) => context.measureText(row.firstElementChild?.textContent.trim() || '').width));
      settings.style.setProperty('--column-label-w', `${Math.ceil(widest)}px`);
    });
  }

  function analysisColumnTotalWidth() {
    return widthModel.getIdColumnWidth() + widthModel.getTaskNameWidth() + widthModel.getColumnWidth('assignee')
      + Object.values(analysisColumnWidths).reduce((total, width) => total + width, 0);
  }

  function currentLeftPaneMaxWidth() {
    return currentWbsView === 'analysis' ? analysisColumnTotalWidth() : widthModel.getVisibleColumnTotalWidth();
  }

  function setWbsView(view) {
    if (view === currentWbsView) return;
    leftPaneWidths[currentWbsView] = widthModel.getLeftPaneWidth();
    currentWbsView = view;
    document.documentElement.dataset.wbsView = view;
    wbsViewTabs.forEach((tab) => {
      const active = tab.dataset.wbsViewTarget === view;
      tab.classList.toggle('is-active', active);
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    applyColumnOrder(view);
    const naturalWidth = currentLeftPaneMaxWidth();
    const targetWidth = leftPaneManuallyResized[view] ? leftPaneWidths[view] : naturalWidth;
    widthModel.setLeftPaneWidth(targetWidth, naturalWidth);
    applyResizableWidths();
  }

  function readDisplaySettings() {
    const element = document.getElementById('wbsgen-display-settings');
    if (!element) {
      return {standard: {columns: {visible: ['*']}}, analysis: {columns: {}}, layers: {visible: ['*']}};
    }
    try {
      const parsed = JSON.parse(element.textContent || '{}');
      return {
        standard: {columns: parsed.standard?.columns || {}},
        analysis: {columns: parsed.analysis?.columns || {}},
        layers: parsed.layers || {},
      };
    } catch (_error) {
      return {standard: {columns: {visible: ['*']}}, analysis: {columns: {}}, layers: {visible: ['*']}};
    }
  }

  function visibleKeysFromDisplayConfig(values, availableKeys) {
    if (!Array.isArray(values)) {
      return new Set(availableKeys);
    }
    if (values.includes('*')) {
      const visible = new Set(availableKeys);
      values.forEach((value) => {
        if (typeof value === 'string' && value.startsWith('-')) {
          visible.delete(value.slice(1));
        }
      });
      return visible;
    }
    return new Set(values.filter((value) => availableKeys.includes(value)));
  }

  function queryList(params, name) {
    const value = params.get(name);
    if (!value) {
      return [];
    }
    return value.split(',').map((item) => item.trim()).filter(Boolean);
  }

  function queryColumnWidths(params) {
    const raw = params.get('columnWidths');
    if (!raw) {
      return {};
    }
    const widths = {};
    raw.split(',').forEach((entry) => {
      const [key, rawValue] = entry.split(':');
      if (!['name', 'assignee', 'comment'].includes(key)) {
        return;
      }
      const value = Number(rawValue);
      if (Number.isInteger(value) && value >= 40) {
        widths[key] = value;
      }
    });
    return widths;
  }

  function buildShareUrl() {
    const url = new URL(window.location.href);
    const params = new URLSearchParams();
    params.set('keyword', searchState.keyword.trim());
    params.set('fields', searchFieldKeys.filter((key) => searchState.fields.has(key)).join(','));
    params.set('mode', searchState.mode);
    params.set('hideColumns', Object.entries(columnKeyMap)
      .filter(([, column]) => widthModel.isColumnHidden(column))
      .map(([key]) => key).join(','));
    params.set('hideLayers', displayLayerKeys.filter((layer) => {
      if (layer === 'highlight') return !highlightsEnabled;
      if (layer === 'tooltip') return !tooltipsEnabled;
      if (layer === 'delayHighlight') return !delayHighlightEnabled;
      return hiddenLayers.has(layer);
    }).join(','));
    params.set('standardOrder', columnOrders.standard.join(','));
    params.set('analysisOrder', columnOrders.analysis.join(','));
    params.set('columnWidths', [
      `name:${widthModel.getTaskNameWidth()}`,
      `assignee:${widthModel.getAssigneeWidth()}`,
      `comment:${widthModel.getCommentWidth()}`,
    ].join(','));
    url.search = params.toString();
    return url.toString();
  }

  function showShareLinkCopyResult(label) {
    if (!shareLinkCopy) return;
    if (shareLinkLabelTimeout !== null) {
      window.clearTimeout(shareLinkLabelTimeout);
    }
    shareLinkCopy.textContent = label;
    shareLinkLabelTimeout = window.setTimeout(() => {
      shareLinkCopy.textContent = 'クリップボードにコピー';
      shareLinkLabelTimeout = null;
    }, 2000);
  }

  async function copyShareLink() {
    try {
      if (typeof navigator.clipboard?.writeText !== 'function') {
        throw new Error('Clipboard API is unavailable');
      }
      await navigator.clipboard.writeText(buildShareUrl());
      showShareLinkCopyResult('コピーしました');
    } catch (_error) {
      showShareLinkCopyResult('コピーできませんでした');
    }
  }

  function normalizeTooltipText(value) {
    return String(value || '')
      .replace(/\r\n?/g, '\n')
      .split('\n')
      .map((line) => line.trim())
      .filter((line, index, lines) => line !== '' || (index > 0 && index < lines.length - 1))
      .join(' ')
      .trim();
  }

  function isOverflowing(element) {
    if (!element) {
      return false;
    }
    return element.scrollWidth > element.clientWidth || element.scrollHeight > element.clientHeight;
  }

  function formatActualPeriod(actualStart, actualEnd) {
    if (!actualStart) {
      return 'なし';
    }
    if (!actualEnd) {
      return `${actualStart} - 進行中`;
    }
    return `${actualStart} - ${actualEnd}`;
  }

  function positionTooltip(event) {
    if (!tooltipElement) {
      return;
    }
    const offset = 12;
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    let left = event.clientX + offset;
    let top = event.clientY + offset;
    const rect = tooltipElement.getBoundingClientRect();
    if (left + rect.width > viewportWidth - 8) {
      left = Math.max(8, viewportWidth - rect.width - 8);
    }
    if (top + rect.height > viewportHeight - 8) {
      top = Math.max(8, event.clientY - rect.height - offset);
    }
    tooltipElement.style.left = `${left}px`;
    tooltipElement.style.top = `${top}px`;
  }

  function showTooltip(event, text) {
    if (!tooltipsEnabled || !tooltipElement) {
      return;
    }
    if (!text || !String(text).trim()) {
      hideTooltip();
      return;
    }
    tooltipElement.textContent = text;
    tooltipElement.classList.add('is-visible');
    tooltipElement.setAttribute('aria-hidden', 'false');
    positionTooltip(event);
  }

  function hideTooltip() {
    activeTooltipTarget = null;
    if (!tooltipElement) {
      return;
    }
    tooltipElement.classList.remove('is-visible');
    tooltipElement.setAttribute('aria-hidden', 'true');
  }

  function planBarTooltipText(bar) {
    const taskName = normalizeTooltipText(bar.dataset.taskName);
    const progressLabel = bar.dataset.progressLabel || '-';
    const expectedProgressLabel = bar.dataset.expectedProgressLabel || '';
    const progressLine = bar.dataset.delayState === 'delayed' && expectedProgressLabel
      ? `進捗: ${progressLabel}（遅延 / 期待 ${expectedProgressLabel}）`
      : `進捗: ${progressLabel}`;
    return [
      taskName,
      `計画終了: ${bar.dataset.plannedEnd || '-'}`,
      progressLine,
      `実績: ${formatActualPeriod(bar.dataset.actualStart, bar.dataset.actualEnd)}`,
    ].join('\n');
  }

  function bindCellTooltips() {
    document.querySelectorAll('[data-tooltip-role="task-name"], [data-tooltip-role="comment"], [data-tooltip-role="assignee"]').forEach((element) => {
      element.addEventListener('mouseenter', (event) => {
        if (!tooltipsEnabled || !isOverflowing(element)) {
          hideTooltip();
          return;
        }
        activeTooltipTarget = element;
        showTooltip(event, normalizeTooltipText(element.dataset.tooltipText));
      });
      element.addEventListener('mousemove', (event) => {
        if (activeTooltipTarget !== element || !tooltipElement.classList.contains('is-visible')) {
          return;
        }
        positionTooltip(event);
      });
      element.addEventListener('mouseleave', () => {
        if (activeTooltipTarget === element) {
          hideTooltip();
        }
      });
    });
  }

  function bindPlanBarTooltips() {
    document.querySelectorAll('[data-tooltip-role="plan-bar"]').forEach((bar) => {
      bar.addEventListener('mouseenter', (event) => {
        if (!tooltipsEnabled) {
          hideTooltip();
          return;
        }
        activeTooltipTarget = bar;
        showTooltip(event, planBarTooltipText(bar));
      });
      bar.addEventListener('mousemove', (event) => {
        if (activeTooltipTarget !== bar || !tooltipElement.classList.contains('is-visible')) {
          return;
        }
        positionTooltip(event);
      });
      bar.addEventListener('mouseleave', () => {
        if (activeTooltipTarget === bar) {
          hideTooltip();
        }
      });
    });
  }

  function setTooltipsEnabled(enabled) {
    tooltipsEnabled = enabled;
    if (tooltipToggle) {
      tooltipToggle.checked = enabled;
    }
    if (app) {
      app.classList.toggle('is-tooltip-hidden', !enabled);
    }
    if (!enabled) {
      hideTooltip();
    }
  }

  function downloadSourceJson(event) {
    event.preventDefault();
    const errorSource = {
      error: '埋め込みJSONが不正なため、正本データをダウンロードできません。',
    };
    let sourceData = errorSource;
    let filename = 'wbsgen-source-error.json';
    try {
      const sourceScript = document.getElementById('wbsgen-source');
      const parsed = sourceScript ? JSON.parse(sourceScript.textContent || '') : null;
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed) && Object.keys(parsed).length) {
        sourceData = parsed;
        filename = 'wbsgen-source.json';
      }
    } catch (_error) {
      // Download the fixed error JSON without showing a dialog or notification.
    }
    const jsonText = `${JSON.stringify(sourceData, null, 2)}\n`;
    const blob = new Blob([jsonText], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function updateLayerVisibility() {
    if (!app) {
      return;
    }
    layerTargets.forEach((layer) => {
      const visible = !hiddenLayers.has(layer);
      app.classList.toggle(`is-layer-${layer}-hidden`, !visible);
      if (layer === 'milestone') {
        const total = app.dataset.milestoneBandTotal || '0px';
        app.style.setProperty('--milestone-band-total', visible ? total : '0px');
      }
      document.querySelectorAll(`[data-layer-action="toggle"][data-layer-target="${layer}"]`).forEach((checkbox) => {
        checkbox.checked = !hiddenLayers.has(layer);
      });
    });
  }

  function setLayerVisible(layer, visible) {
    if (!layerTargets.includes(layer)) {
      return;
    }
    if (visible) {
      hiddenLayers.delete(layer);
    } else {
      hiddenLayers.add(layer);
    }
    updateLayerVisibility();
  }

  function setDelayHighlightEnabled(enabled) {
    delayHighlightEnabled = enabled;
    if (delayHighlightToggle) {
      delayHighlightToggle.checked = enabled;
    }
    if (app) {
      app.classList.toggle('is-delay-highlight-hidden', !enabled);
    }
  }

  function hideDisplayLayer(layer) {
    if (layer === 'inazuma' || layer === 'actual' || layer === 'milestone') {
      setLayerVisible(layer, false);
    } else if (layer === 'highlight') {
      highlightsEnabled = false;
      if (highlightToggle) {
        highlightToggle.checked = false;
      }
      renderHighlights();
    } else if (layer === 'tooltip') {
      setTooltipsEnabled(false);
    } else if (layer === 'delayHighlight') {
      setDelayHighlightEnabled(false);
    }
  }

  function initializeLayerVisibility(displaySettings, params) {
    const visibleLayers = visibleKeysFromDisplayConfig(displaySettings.layers, displayLayerKeys);
    setLayerVisible('inazuma', visibleLayers.has('inazuma'));
    setLayerVisible('actual', visibleLayers.has('actual'));
    setLayerVisible('milestone', visibleLayers.has('milestone'));
    highlightsEnabled = visibleLayers.has('highlight');
    if (highlightToggle) {
      highlightToggle.checked = highlightsEnabled;
    }
    renderHighlights();
    setTooltipsEnabled(visibleLayers.has('tooltip'));
    setDelayHighlightEnabled(visibleLayers.has('delayHighlight'));
    queryList(params, 'hideLayers').forEach((layer) => hideDisplayLayer(layer));
  }

  function initializeColumnVisibility(displaySettings, params) {
    const visibleColumns = visibleKeysFromDisplayConfig(displaySettings.standard.columns.visible, Object.keys(columnKeyMap));
    Object.entries(columnKeyMap).forEach(([key, column]) => {
      setColumnHidden(column, !visibleColumns.has(key));
    });
    queryList(params, 'hideColumns').forEach((key) => {
      const column = columnKeyMap[key];
      if (column) {
        setColumnHidden(column, true);
      }
    });
  }

  function togglePinnedTask(taskId) {
    if (!taskId) {
      return;
    }
    if (pinnedTaskIds.has(taskId)) {
      pinnedTaskIds.delete(taskId);
    } else {
      pinnedTaskIds.add(taskId);
    }
  }

  function togglePinnedDate(dateIndex) {
    if (!Number.isInteger(dateIndex)) {
      return;
    }
    if (pinnedDateIndexes.has(dateIndex)) {
      pinnedDateIndexes.delete(dateIndex);
    } else {
      pinnedDateIndexes.add(dateIndex);
    }
  }

  function togglePinnedScheduleCell(taskId, dateIndex) {
    const taskPinned = Boolean(taskId && pinnedTaskIds.has(taskId));
    const datePinned = Number.isInteger(dateIndex) && pinnedDateIndexes.has(dateIndex);
    if (taskPinned || datePinned) {
      if (taskId) {
        pinnedTaskIds.delete(taskId);
      }
      if (Number.isInteger(dateIndex)) {
        pinnedDateIndexes.delete(dateIndex);
      }
      return;
    }
    if (taskId) {
      pinnedTaskIds.add(taskId);
    }
    if (Number.isInteger(dateIndex)) {
      pinnedDateIndexes.add(dateIndex);
    }
  }

  function positionFromChartEvent(event) {
    if (!chartBody) {
      return {taskId: null, dateIndex: null};
    }
    const rect = chartBody.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const rowIndex = Math.floor(y / rowHeight);
    const dateIndex = Math.floor(x / dayWidth);
    return {
      taskId: visibleRows()[rowIndex]?.dataset.taskId || null,
      dateIndex: dateIndex >= 0 && dateIndex < dateCells.length ? dateIndex : null,
    };
  }

  function startResize(event, handle, onDelta) {
    event.preventDefault();
    const startX = event.clientX;
    document.body.classList.add('is-resizing');
    handle.classList.add('is-active');
    handle.setPointerCapture?.(event.pointerId);

    function move(moveEvent) {
      onDelta(moveEvent.clientX - startX);
      applyResizableWidths();
    }

    function end() {
      document.body.classList.remove('is-resizing');
      handle.classList.remove('is-active');
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', end);
      window.removeEventListener('pointercancel', end);
    }

    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', end);
    window.addEventListener('pointercancel', end);
  }

  if (paneResizeHandle) {
    paneResizeHandle.addEventListener('pointerdown', (event) => {
      leftPaneManuallyResized[currentWbsView] = true;
      if (currentWbsView === 'analysis') {
        const startWidth = widthModel.getLeftPaneWidth();
        const maxWidth = analysisColumnTotalWidth();
        startResize(event, paneResizeHandle, (deltaX) => {
          widthModel.setLeftPaneWidth(startWidth + deltaX, maxWidth);
        });
        return;
      }
      widthModel.beginPaneResize();
      startResize(event, paneResizeHandle, (deltaX) => {
        widthModel.updatePaneResize(deltaX, {windowInnerWidth: window.innerWidth});
      });
    });
  }

  if (taskNameResizeHandle) {
    taskNameResizeHandle.addEventListener('pointerdown', (event) => {
      widthModel.beginTaskNameResize();
      startResize(event, taskNameResizeHandle, (deltaX) => {
        widthModel.updateTaskNameResize(deltaX, {
          windowInnerWidth: window.innerWidth,
          workspaceClientWidth: workspace?.clientWidth,
        });
        if (currentWbsView === 'analysis') {
          widthModel.setLeftPaneWidth(widthModel.getLeftPaneWidth(), analysisColumnTotalWidth());
        }
      });
    });
  }

  if (assigneeResizeHandle) {
    assigneeResizeHandle.addEventListener('pointerdown', (event) => {
      widthModel.beginAssigneeResize();
      startResize(event, assigneeResizeHandle, (deltaX) => {
        widthModel.updateAssigneeResize(deltaX, {windowInnerWidth: window.innerWidth});
        if (currentWbsView === 'analysis') {
          widthModel.setLeftPaneWidth(widthModel.getLeftPaneWidth(), analysisColumnTotalWidth());
        }
      });
    });
  }

  wbsViewTabs.forEach((tab) => {
    tab.addEventListener('click', () => setWbsView(tab.dataset.wbsViewTarget || 'standard'));
  });

  scrollPanes.forEach((pane) => {
    pane.addEventListener('wheel', (event) => {
      if (!workspace || Math.abs(event.deltaY) <= Math.abs(event.deltaX)) {
        return;
      }
      workspace.scrollTop += event.deltaY;
      event.preventDefault();
    }, {passive: false});
  });

  leftRows.forEach((row) => {
    row.addEventListener('mouseenter', () => {
      hoveredTaskId = row.dataset.taskId || null;
      renderHighlights();
    });
    row.addEventListener('mouseleave', () => {
      hoveredTaskId = null;
      renderHighlights();
    });
    row.addEventListener('click', (event) => {
      if (!event.metaKey && !event.ctrlKey) {
        return;
      }
      event.preventDefault();
      togglePinnedTask(row.dataset.taskId);
      renderHighlights();
    });
  });

  dateCells.forEach((cell) => {
    cell.addEventListener('mouseenter', () => {
      hoveredDateIndex = dateIndexForCell(cell);
      renderHighlights();
    });
    cell.addEventListener('mouseleave', () => {
      hoveredDateIndex = null;
      renderHighlights();
    });
    cell.addEventListener('click', (event) => {
      if (!event.metaKey && !event.ctrlKey) {
        return;
      }
      event.preventDefault();
      togglePinnedDate(dateIndexForCell(cell));
      renderHighlights();
    });
  });

  if (chartBody) {
    chartBody.addEventListener('mousemove', (event) => {
      const position = positionFromChartEvent(event);
      hoveredTaskId = position.taskId;
      hoveredDateIndex = position.dateIndex;
      renderHighlights();
    });
    chartBody.addEventListener('mouseleave', () => {
      hoveredTaskId = null;
      hoveredDateIndex = null;
      renderHighlights();
    });
    chartBody.addEventListener('click', (event) => {
      if (!event.metaKey && !event.ctrlKey) {
        return;
      }
      const position = positionFromChartEvent(event);
      event.preventDefault();
      togglePinnedScheduleCell(position.taskId, position.dateIndex);
      renderHighlights();
    });
  }

  if (highlightToggle) {
    highlightToggle.addEventListener('change', () => {
      highlightsEnabled = highlightToggle.checked;
      renderHighlights();
    });
  }

  if (tooltipToggle) {
    tooltipToggle.addEventListener('change', () => {
      setTooltipsEnabled(tooltipToggle.checked);
    });
  }

  if (delayHighlightToggle) {
    delayHighlightToggle.addEventListener('change', () => {
      setDelayHighlightEnabled(delayHighlightToggle.checked);
    });
  }

  if (sourceDownload) {
    sourceDownload.addEventListener('click', downloadSourceJson);
  }
  if (shareLinkCopy) {
    shareLinkCopy.addEventListener('click', copyShareLink);
  }

  if (searchSummary) {
    searchSummary.addEventListener('click', () => setSearchDrawerOpen(searchDrawer?.hidden));
  }
  if (searchClose) {
    searchClose.addEventListener('click', () => setSearchDrawerOpen(false));
  }
  if (searchKeyword) {
    searchKeyword.addEventListener('input', () => {
      searchState.keyword = searchKeyword.value;
      refreshSearchResults();
    });
  }
  searchFieldInputs.forEach((input) => {
    input.addEventListener('change', () => {
      const field = input.dataset.searchField;
      if (field === 'all') {
        searchState.fields = input.checked ? new Set(searchFieldKeys) : new Set();
      } else if (input.checked) {
        searchState.fields.add(field);
      } else {
        searchState.fields.delete(field);
      }
      refreshSearchResults();
    });
  });
  searchModeInputs.forEach((input) => {
    input.addEventListener('change', () => {
      if (input.checked) {
        searchState.mode = input.dataset.searchMode;
        refreshSearchResults();
      }
    });
  });
  if (searchClear) {
    searchClear.addEventListener('click', () => {
      searchState.keyword = '';
      searchState.fields = new Set(searchFieldKeys);
      refreshSearchResults();
    });
  }

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') {
      return;
    }
    pinnedTaskIds.clear();
    pinnedDateIndexes.clear();
    hideTooltip();
    renderHighlights();
  });

  document.addEventListener('click', (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }
    if (viewMenu && viewMenu.open && !viewMenu.contains(event.target)) {
      viewMenu.open = false;
    }
    const layerToggle = event.target.closest('[data-layer-action="toggle"][data-layer-target]');
    if (layerToggle) {
      setLayerVisible(layerToggle.dataset.layerTarget, layerToggle.checked);
      return;
    }
    const columnVisibilityToggle = event.target.closest('[data-column-visibility-toggle]');
    if (columnVisibilityToggle) {
      setColumnHidden(columnVisibilityToggle.dataset.columnVisibilityToggle, !columnVisibilityToggle.checked);
      return;
    }
    const columnVisibilityAction = event.target.closest('[data-column-visibility-action]');
    if (columnVisibilityAction) {
      const hide = columnVisibilityAction.dataset.columnVisibilityAction === 'hide-all';
      widthModel.getOtherColumnKeys().concat('comment', 'assignee').forEach((column) => setColumnHidden(column, hide));
      return;
    }
    const columnOrderButton = event.target.closest('[data-column-order][data-direction]');
    if (columnOrderButton) {
      const order = columnOrders[currentWbsView];
      const index = order.indexOf(columnOrderButton.dataset.columnOrder);
      const targetIndex = columnOrderButton.dataset.direction === 'up' ? index - 1 : index + 1;
      if (index >= 0 && targetIndex >= 0 && targetIndex < order.length) {
        [order[index], order[targetIndex]] = [order[targetIndex], order[index]];
        applyColumnOrder(currentWbsView);
      }
      return;
    }
    const collapseButton = event.target.closest('[data-action]');
    if (collapseButton) {
      const action = collapseButton.dataset.action;
      if (action === 'collapse-all') {
        document.querySelectorAll('.tree-toggle[data-task-id]').forEach((button) => {
          collapseState.add(button.dataset.taskId);
        });
        updateRowVisibility();
      } else if (action === 'expand-all') {
        collapseState.clear();
        updateRowVisibility();
      }
      return;
    }
    const toggle = event.target.closest('.tree-toggle[data-task-id]');
    if (!toggle) {
      return;
    }
    const taskId = toggle.dataset.taskId;
    setCollapsed(taskId, !collapseState.has(taskId));
  });

  function initializeDockWindows() {
    // Both the warning and holiday panels dock at the bottom-right corner.
    // The first-opened window keeps the rightmost slot (position 0); each
    // subsequently-opened window stacks to its left. Closing a window
    // collapses the gap so the remaining windows shift back toward the edge.
    const edge = 16;
    const gap = 16;
    const pairs = [
      {checkbox: document.querySelector('.warning-checkbox'), window: document.querySelector('.warning-window')},
      {checkbox: document.querySelector('.holiday-checkbox'), window: document.querySelector('.holiday-window')},
    ].filter((pair) => pair.checkbox && pair.window && pair.window.hasAttribute('data-dock-window'));
    if (!pairs.length) {
      return;
    }
    const openOrder = [];

    function layout() {
      let right = edge;
      openOrder.forEach((win) => {
        win.style.right = `${right}px`;
        // The next window sits to the left of this one.
        right += win.offsetWidth + gap;
      });
    }

    pairs.forEach(({checkbox, window: win}) => {
      // Seed the order with windows that are already open on load
      // (the warning window opens by default when warnings exist).
      if (checkbox.checked) {
        openOrder.push(win);
      }
      checkbox.addEventListener('change', () => {
        const index = openOrder.indexOf(win);
        if (checkbox.checked) {
          if (index === -1) {
            openOrder.push(win);
          }
        } else if (index !== -1) {
          openOrder.splice(index, 1);
        }
        layout();
      });
    });

    layout();
  }

  function initializeDisplaySettings() {
    const displaySettings = readDisplaySettings();
    const params = queryParams;
    initializeColumnVisibility(displaySettings, params);
    initializeLayerVisibility({layers: displaySettings.layers.visible}, params);
    const standardBase = normalizeColumnOrder(displaySettings.standard.columns.order, defaultColumnOrders.standard);
    const analysisBase = normalizeColumnOrder(displaySettings.analysis.columns.order, defaultColumnOrders.analysis);
    const standardQueryOrder = queryList(params, 'standardOrder');
    const analysisQueryOrder = queryList(params, 'analysisOrder');
    columnOrders.standard = standardQueryOrder.length ? normalizeColumnOrder(standardQueryOrder, standardBase) : standardBase;
    columnOrders.analysis = analysisQueryOrder.length ? normalizeColumnOrder(analysisQueryOrder, analysisBase) : analysisBase;
    applyColumnOrder(currentWbsView);
  }

  initializeDisplaySettings();
  initializeSearchState(queryParams);
  document.documentElement.dataset.wbsView = currentWbsView;
  updateRowVisibility();
  applyResizableWidths();
  bindCellTooltips();
  bindPlanBarTooltips();
  initializeDockWindows();
  renderHighlights();
  window.updateRowVisibility = updateRowVisibility;
  window.updateInazuma = updateInazuma;
  window.setCollapsed = setCollapsed;
})();
