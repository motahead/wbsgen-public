window.WbsWidthModel = (() => {
  function maxAdditionalResizableWidth(windowInnerWidth) {
    return Math.min(480, windowInnerWidth * 0.3);
  }

  function create({idColumnWidth, defaultTaskNameWidth, defaultAssigneeWidth, defaultCommentWidth, columnWidths}) {
    const state = {
      idColumnWidth,
      defaultTaskNameWidth,
      defaultAssigneeWidth,
      defaultCommentWidth,
      columnWidths: {...columnWidths},
      hiddenColumns: new Set(),
      taskNameWidth: defaultTaskNameWidth,
      assigneeWidth: defaultAssigneeWidth,
      commentWidth: defaultCommentWidth,
      leftPaneWidth: idColumnWidth + defaultTaskNameWidth + defaultAssigneeWidth + defaultCommentWidth
        + Object.values(columnWidths).reduce((total, width) => total + width, 0),
    };

    let taskNameResizeStart = null;
    let assigneeResizeStart = null;
    let paneResizeStart = null;

    function displayedColumnWidth(column) {
      if (state.hiddenColumns.has(column)) {
        return 0;
      }
      if (column === 'comment') {
        return state.commentWidth;
      }
      if (column === 'assignee') {
        return state.assigneeWidth;
      }
      return state.columnWidths[column];
    }

    function visibleColumnTotalWidth() {
      const othersTotal = Object.keys(state.columnWidths).reduce(
        (total, column) => total + displayedColumnWidth(column),
        0,
      );
      return state.idColumnWidth + state.taskNameWidth + displayedColumnWidth('assignee') + displayedColumnWidth('comment') + othersTotal;
    }

    function leftPaneMinWidth() {
      return state.idColumnWidth + state.taskNameWidth;
    }

    function maxTaskNameWidth(windowInnerWidth, workspaceClientWidth) {
      const viewportWidth = workspaceClientWidth || windowInnerWidth;
      const nonTaskWidth = visibleColumnTotalWidth() - state.taskNameWidth;
      const reachableTaskNameWidth = viewportWidth - nonTaskWidth - 4;
      return Math.max(
        state.defaultTaskNameWidth,
        Math.min(state.defaultTaskNameWidth + maxAdditionalResizableWidth(windowInnerWidth), reachableTaskNameWidth),
      );
    }

    function maxAssigneeWidth(windowInnerWidth) {
      return state.defaultAssigneeWidth + maxAdditionalResizableWidth(windowInnerWidth);
    }

    function maxCommentWidth(windowInnerWidth) {
      return state.defaultCommentWidth + maxAdditionalResizableWidth(windowInnerWidth);
    }

    function clamp(value, min, max) {
      return Math.min(Math.max(value, min), max);
    }

    function applyLeftPaneClamp() {
      state.leftPaneWidth = clamp(state.leftPaneWidth, leftPaneMinWidth(), visibleColumnTotalWidth());
    }

    function widthsSnapshot() {
      return {
        taskNameWidth: state.taskNameWidth,
        assigneeWidth: state.assigneeWidth,
        commentWidth: state.commentWidth,
        leftPaneWidth: state.leftPaneWidth,
      };
    }

    return {
      getTaskNameWidth() { return state.taskNameWidth; },
      getAssigneeWidth() { return state.assigneeWidth; },
      getCommentWidth() { return state.commentWidth; },
      getLeftPaneWidth() { return state.leftPaneWidth; },
      isColumnHidden(column) { return state.hiddenColumns.has(column); },
      getColumnWidth(column) { return displayedColumnWidth(column); },
      getVisibleColumnTotalWidth() { return visibleColumnTotalWidth(); },
      getIdColumnWidth() { return state.idColumnWidth; },

      getOtherColumnKeys() { return Object.keys(state.columnWidths); },

      setColumnHidden(column, hidden) {
        if (state.hiddenColumns.has(column) === hidden) {
          return widthsSnapshot();
        }
        const widthBefore = displayedColumnWidth(column);
        if (hidden) {
          state.hiddenColumns.add(column);
        } else {
          state.hiddenColumns.delete(column);
        }
        state.leftPaneWidth += displayedColumnWidth(column) - widthBefore;
        applyLeftPaneClamp();
        return widthsSnapshot();
      },

      setLeftPaneWidth(width, maxWidth) {
        state.leftPaneWidth = clamp(width, leftPaneMinWidth(), maxWidth);
        return widthsSnapshot();
      },

      beginTaskNameResize() {
        taskNameResizeStart = {
          startTaskNameWidth: state.taskNameWidth,
          startLeftPaneWidth: state.leftPaneWidth,
        };
      },

      updateTaskNameResize(deltaX, {windowInnerWidth, workspaceClientWidth}) {
        if (!taskNameResizeStart) {
          throw new Error('beginTaskNameResize must be called before updateTaskNameResize');
        }
        const {startTaskNameWidth, startLeftPaneWidth} = taskNameResizeStart;
        state.taskNameWidth = clamp(
          startTaskNameWidth + deltaX,
          state.defaultTaskNameWidth,
          maxTaskNameWidth(windowInnerWidth, workspaceClientWidth),
        );
        state.leftPaneWidth = startLeftPaneWidth + (state.taskNameWidth - startTaskNameWidth);
        applyLeftPaneClamp();
        return widthsSnapshot();
      },

      beginAssigneeResize() {
        assigneeResizeStart = {
          startAssigneeWidth: state.assigneeWidth,
          startLeftPaneWidth: state.leftPaneWidth,
        };
      },

      updateAssigneeResize(deltaX, {windowInnerWidth}) {
        if (!assigneeResizeStart) {
          throw new Error('beginAssigneeResize must be called before updateAssigneeResize');
        }
        const {startAssigneeWidth, startLeftPaneWidth} = assigneeResizeStart;
        state.assigneeWidth = clamp(
          startAssigneeWidth + deltaX,
          state.defaultAssigneeWidth,
          maxAssigneeWidth(windowInnerWidth),
        );
        state.leftPaneWidth = startLeftPaneWidth + (state.assigneeWidth - startAssigneeWidth);
        applyLeftPaneClamp();
        return widthsSnapshot();
      },

      beginPaneResize() {
        paneResizeStart = {
          startWidth: state.leftPaneWidth,
          commentHiddenAtStart: state.hiddenColumns.has('comment'),
          fixedPartAtStart: visibleColumnTotalWidth() - displayedColumnWidth('comment'),
        };
      },

      updatePaneResize(deltaX, {windowInnerWidth}) {
        if (!paneResizeStart) {
          throw new Error('beginPaneResize must be called before updatePaneResize');
        }
        const {startWidth, commentHiddenAtStart, fixedPartAtStart} = paneResizeStart;
        const desiredWidth = startWidth + deltaX;
        if (commentHiddenAtStart) {
          state.leftPaneWidth = clamp(desiredWidth, leftPaneMinWidth(), fixedPartAtStart);
        } else {
          state.commentWidth = clamp(
            desiredWidth - fixedPartAtStart,
            state.defaultCommentWidth,
            maxCommentWidth(windowInnerWidth),
          );
          state.leftPaneWidth = clamp(
            desiredWidth,
            leftPaneMinWidth(),
            fixedPartAtStart + maxCommentWidth(windowInnerWidth),
          );
        }
        applyLeftPaneClamp();
        return widthsSnapshot();
      },
    };
  }

  return {create};
})();
