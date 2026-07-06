
    document.addEventListener("DOMContentLoaded", function() {
        let currentView  = "Week";
        // 算本周一（不用 isoWeek 插件，纯数学）
        var _t = dayjs(), _d = _t.day(); // 0=周日,1=周一,...,6=周六
        let currentStart = _t.subtract(_d === 0 ? 6 : _d - 1, "day").startOf("day");
        var cellBackgrounds = {};   // 日期背景色缓存

        // ---- 日期提取：直接用 value 前10位（DayPilot 按 UTC 天分列，同列日期一致）----
        function cellDateStr(start) {
            try {
                var v = start.value;
                if (!v) return null;
                return v.slice(0, 10);
            } catch(e) {
                return null;
            }
        }

        // ---- 设置读取 ----
        function getOverlaySettings() {
            var s = localStorage.getItem('rubedo-overlays');
            if (!s) s = '{"solar":true,"fest":true,"holiday":true,"sem":true}';
            try { return JSON.parse(s); } catch(e) { return {"solar":true,"fest":true,"holiday":true,"sem":true}; }
        }
        var typeKey = {solar: "solar", fest: "fest", holiday: "holiday", sem: "sem", custom: "sem"};

        // ---- DetailPanel：事件详情面板（渲染器注册模式）----
        window.DetailPanel = {
            container: null,
            renderers: {},

            init: function() {
                this.container = document.getElementById('detail-panel');
            },

            register: function(type, rendererFn) {
                this.renderers[type] = rendererFn;
            },

            show: function(event) {
                console.log('DetailPanel.show:', event.kind, event.text);
                if (!this.container) this.init();
                this.container.classList.add('show');
                document.getElementById('detail-loading').style.display = 'block';
                document.getElementById('detail-content').innerHTML = '';

                var renderer = this.renderers[event.kind] || this.renderers['default'];
                if (renderer) {
                    renderer(event, this.container);
                } else {
                    this.showContent('<div style="padding:20px;color:#888;">未知事件类型：' + event.kind + '</div>');
                }
                // 底部面板显示后，通知 DayPilot 重绘（容器高度变了）
                setTimeout(function() {
                    if (window.dp) window.dp.update();
                    console.log('[DayPilot] dp.update() called after DetailPanel.show');
                }, 100);
            },

            showLoading: function() {
                document.getElementById('detail-loading').style.display = 'block';
                document.getElementById('detail-content').innerHTML = '';
            },

            showContent: function(html) {
                document.getElementById('detail-loading').style.display = 'none';
                document.getElementById('detail-content').innerHTML = html;
            },

            hide: function() {
                if (!this.container) this.init();
                this.container.classList.remove('show');
            },

            toggleStatus: function(eventId) {
                // 调用 API 切换状态，然后刷新详情
                fetch('/api/events?day=' + new Date().toISOString().slice(0,10))
                    .then(r => r.json())
                    .then(events => {
                        var ev = events.find(e => e.id === eventId);
                        if (ev) {
                            // 调用 toggle API
                            return fetch('/api/event/' + eventId + '/toggle', { method: 'POST' });
                        }
                    })
                    .then(() => {
                        // 刷新详情面板
                        var currentEvent = window.DetailPanel._currentEvent;
                        if (currentEvent) window.DetailPanel.show(currentEvent);
                        // 刷新日历
                        if (window.dp) window.dp.loadEvents();
                    });
            },

            deleteEvent: function(eventId) {
                if (!confirm('确定要删除这个事件吗？')) return;
                fetch('/api/event/' + eventId, { method: 'DELETE' })
                    .then(r => r.json())
                    .then(data => {
                        if (data.ok) {
                            window.DetailPanel.hide();
                            if (window.dp) window.dp.loadEvents();
                        } else {
                            alert('删除失败：' + (data.error || '未知错误'));
                        }
                    });
            }
        };

        // ---- 注册 SOP 渲染器（步骤导航 + 工具区）----
        window.DetailPanel.register('sop', function(event, container) {
            var sopId = event.sop_id || 'kujiale';
            window.DetailPanel._currentEvent = event;
            
            // 隐藏空提示，显示 SOP 内容
            document.getElementById('sop-empty').style.display = 'none';
            document.getElementById('sop-content').classList.add('show');
            
            // 获取 SOP JSON
            fetch('/api/sop/' + sopId)
                .then(r => r.json())
                .then(data => {
                    if (!data.ok) {
                        document.getElementById('sop-tool-area').innerHTML = '<div style="color:#e94560;padding:20px;">加载 SOP 失败：' + (data.error || '未知错误') + '</div>';
                        return;
                    }
                    
                    var sop = data.sop;
                    var currentStep = event.sop_current_step || 0;
                    
                    // 设置 SOP 名称
                    document.getElementById('sop-name').textContent = sop.name || 'SOP';
                    
                    // 计算进度
                    var totalSteps = sop.steps ? sop.steps.length : 0;
                    var doneSteps = currentStep; // 简化：当前步骤之前的都算完成
                    var progressPct = totalSteps > 0 ? Math.round(doneSteps / totalSteps * 100) : 0;
                    document.getElementById('sop-progress').textContent = doneSteps + '/' + totalSteps;
                    document.getElementById('sop-progress-fill').style.width = progressPct + '%';
                    
                    // 渲染步骤导航条
                    var stepsContainer = document.getElementById('sop-steps');
                    stepsContainer.innerHTML = '';
                    
                    if (sop.steps) {
                        sop.steps.forEach(function(step, idx) {
                            var stepEl = document.createElement('div');
                            stepEl.className = 'sop-step';
                            if (idx === currentStep) stepEl.classList.add('active');
                            if (idx < currentStep) stepEl.classList.add('done');
                            
                            var statusIcon = idx < currentStep ? '✓' : (idx === currentStep ? '▶' : '⏳');
                            
                            stepEl.innerHTML = '<span class="sop-step-status">' + statusIcon + '</span><span>' + (step.name || '步骤' + (idx + 1)) + '</span>';
                            
                            stepEl.onclick = function() {
                                // 切换当前步骤高亮
                                stepsContainer.querySelectorAll('.sop-step').forEach(function(el) {
                                    el.classList.remove('active');
                                });
                                stepEl.classList.add('active');
                                
                                // 显示工具区（占位）
                                window.DetailPanel._showStepTool(sop, step, idx);
                            };
                            
                            stepsContainer.appendChild(stepEl);
                        });
                    }
                    
                    // 默认显示第一个步骤的工具区
                    if (sop.steps && sop.steps.length > 0) {
                        window.DetailPanel._showStepTool(sop, sop.steps[currentStep], currentStep);
                    }
                })
                .catch(err => {
                    document.getElementById('sop-tool-area').innerHTML = '<div style="color:#e94560;padding:20px;">加载 SOP 失败：' + err + '</div>';
                });
        });
        
        // ---- 显示步骤工具区（占位）----
        window.DetailPanel._showStepTool = function(sop, step, stepIdx) {
            var toolArea = document.getElementById('sop-tool-area');
            toolArea.innerHTML = `
                <div style="color:#aaa;font-size:13px;margin-bottom:12px;">步骤 ${stepIdx + 1} / ${sop.steps.length}</div>
                <div style="font-size:16px;font-weight:bold;color:#eee;margin-bottom:8px;">${step.name || '无标题'}</div>
                <div style="font-size:13px;color:#ccc;line-height:1.6;margin-bottom:20px;padding:12px;background:#1a1a2e;border-radius:8px;">${step.description || '无描述'}</div>
                <div style="display:flex;gap:10px;">
                    <button onclick="window.DetailPanel._markStepDone(${stepIdx})" style="padding:8px 16px;border:1px solid #0f3460;border-radius:6px;background:#0f3460;color:#eee;cursor:pointer;font-size:13px;">
                        ${stepIdx < (window.DetailPanel._currentEvent.sop_current_step || 0) ? '已完成 ✓' : '标记完成'}
                    </button>
                </div>
            `;
        };
        
        // ---- 标记步骤完成 ----
        window.DetailPanel._markStepDone = function(stepIdx) {
            var event = window.DetailPanel._currentEvent;
            if (!event) return;
            
            // 调用 API 更新 sop_current_step
            fetch('/api/events/' + event.id + '/sop-step', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({step: stepIdx + 1})
            })
            .then(r => r.json())
            .then(data => {
                if (data.ok) {
                    // 刷新详情面板
                    window.DetailPanel.show(event);
                    // 刷新日历
                    if (window.dp) window.dp.loadEvents();
                }
            });
        };

        // ---- 注册默认渲染器（普通事件 HTML 注入）----
        window.DetailPanel.register('default', function(event, container) {
            window.DetailPanel._currentEvent = event;
            var statusStr = event.status === 'done' ? '✅ 已完成' : '⏳ 进行中';
            var html = `
                <div class="detail-header">
                    <span class="detail-title">${event.text || '无标题'}</span>
                    <span class="detail-kind" style="background:#0f3460;color:#e94560;padding:4px 10px;border-radius:12px;font-size:12px;">${event.kind || 'reminder'}</span>
                </div>
                <div class="detail-body" style="padding:20px;">
                    <div style="font-size:14px;color:#aaa;margin-bottom:12px;">🕐 ${event.start ? event.start.slice(11,16) : ''} - ${event.end ? event.end.slice(11,16) : ''}</div>
                    <div style="font-size:14px;color:#ccc;line-height:1.6;margin-bottom:20px;padding:12px;background:#1a1a2e;border-radius:8px;">${event.description || '无描述'}</div>
                    <div style="display:flex;gap:10px;">
                        <button onclick="window.DetailPanel._toggleStatus('${event.id}')" style="padding:8px 16px;border:1px solid #0f3460;border-radius:6px;background:#0f3460;color:#eee;cursor:pointer;font-size:13px;">${event.status === 'done' ? '标记未完成' : '标记完成'}</button>
                        <button onclick="showEditDialog('${event.id}')" style="padding:8px 16px;border:1px solid #0f3460;border-radius:6px;background:#0f3460;color:#eee;cursor:pointer;font-size:13px;">编辑</button>
                        <button onclick="window.DetailPanel._deleteEvent('${event.id}')" style="padding:8px 16px;border:1px solid #e94560;border-radius:6px;background:transparent;color:#e94560;cursor:pointer;font-size:13px;">删除</button>
                    </div>
                </div>
            `;
            window.DetailPanel.showContent(html);
        });

        // ---- 辅助方法（需要在 register 之后定义）----
        window.DetailPanel._toggleStatus = function(eventId) {
            var ev = window.DetailPanel._currentEvent;
            if (!ev) return;
            var newStatus = ev.status === 'done' ? 'pending' : 'done';
            fetch('/api/events/status', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id: eventId, day: ev.start.slice(0,10), status: newStatus})
            })
            .then(r => r.json())
            .then(data => {
                if (data.ok) {
                    ev.status = newStatus;
                    window.DetailPanel.show(ev);
                    if (window.dp) window.dp.loadEvents();
                }
            });
        };

        window.DetailPanel._deleteEvent = function(eventId) {
            if (!confirm('确定要删除这个事件吗？')) return;
            var ev = window.DetailPanel._currentEvent;
            var day = ev ? ev.start.slice(0,10) : '';
            fetch('/api/events/delete', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id: eventId, day: day})
            })
            .then(r => r.json())
            .then(data => {
                if (data.ok) {
                    window.DetailPanel.hide();
                    if (window.dp) window.dp.loadEvents();
                } else {
                    alert('删除失败：' + (data.error || '未知错误'));
                }
            });
        };

        // ---- DayPilot 日历初始化 ----
            const dp = new DayPilot.Calendar("calendar", {
            viewType:      "Week",
            startDate:     currentStart.format("YYYY-MM-DD"),
            weekStarts:    1,
            cellDuration:  30,
            cellHeight:    30,
            height:        "auto",
            dayBeginHour: 0,
            dayEndHour:   24,
            headerHeight: 40,
            locale:        "zh-cn",
            // 不用 height:auto，用动态 cellHeight 控制网格高度
            timeRangeSelectedHandling: "JavaScript",

            onTimeRangeSelected: function(args) {
                showCreateDialog(args.start, args.end);
            },

            eventClickHandling: "JavaScript",
            onEventClick: function(args) {
                console.log('onEventClick:', args.e);
                var ev = normalizeEvent(args.e);
                // 显示详情面板（根据事件类型自动选择渲染器）
                if (window.DetailPanel) {
                    window.DetailPanel.show(ev);
                }
            },

            eventRightClickHandling: "Disabled",

            eventDeleteHandling: "Disabled",

            onBeforeEventRender: function(args) {
                var d = args.data;
                if (!d) return;
                if (d.readonly && !d.recurring) return;

                args.data.areas = [
                    {
                        right: 60, top: 5, width: 18, height: 18,
                        html: d.status === "done" ? "\u2705" : "\u2B1C",
                        action: "None",
                        onClick: function(areaArgs) {
                            toggleEventStatus(normalizeEvent(areaArgs.source));
                        },
                        visibility: "Visible",
                    },
                    {
                        right: 40, top: 5, width: 18, height: 18,
                        html: d.locked ? "\uD83D\uDD12" : "\uD83D\uDD13",
                        action: "None",
                        onClick: function(areaArgs) {
                            toggleEventLock(normalizeEvent(areaArgs.source));
                        },
                        visibility: "Visible",
                    },
                    {
                        right: 20, top: 5, width: 18, height: 18,
                        html: "\u270F\uFE0F",
                        action: "None",
                        onClick: function(areaArgs) {
                            showEditDialog(normalizeEvent(areaArgs.source));
                        },
                        visibility: "Visible",
                    }
                ];
            },

            onBeforeCellRender: function(args) {
                if (!args.cell || !args.cell.start) return;
                var ds = cellDateStr(args.cell.start);
                if (!ds) return;

                args.cell.properties = args.cell.properties || {};
                args.cell.properties.backColor = "#FFFFFF";

                var bg = cellBackgrounds[ds];
                if (!bg) return;

                var settings = getOverlaySettings();
                if (!settings[typeKey[bg.type] || "sem"]) return;

                if (bg.color) {
                    args.cell.properties.backColor = bg.color;
                }
                args.cell.toolTip = bg.tooltip || bg.text;
            },

            onBeforeHeaderRender: function(args) {
                if (!args.header || !args.header.start) return;
                var ds = cellDateStr(args.header.start);
                if (!ds) return;

                var parts = ds.split('-');
                var dateObj = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
                var dowNames = ['周日','周一','周二','周三','周四','周五','周六'];
                var md = parseInt(parts[1], 10) + '/' + parseInt(parts[2], 10);
                var html = dowNames[dateObj.getDay()] + ' ' + md;

                var bg = cellBackgrounds[ds];
                if (bg) {
                    var settings = getOverlaySettings();
                    if (settings[typeKey[bg.type] || "sem"]) {
                        html += ' ' + bg.text;
                    }
                }
                args.header.html = html;
            },
        });

        // ---- Helper: convert DayPilot.Event to plain JS object ----
        function normalizeEvent(e) {
            var d = e.data || {};
            function getVal(obj, key) {
                var v = obj[key];
                if (typeof v === 'function') v = v();
                if (v && typeof v === 'object' && v.value) return v.value;
                return v;
            }
            var start = getVal(e, 'start') || d.start || '';
            var end   = getVal(e, 'end')   || d.end   || '';
            return {
                id:          getVal(e, 'id')  || d.id  || '',
                text:        getVal(e, 'text')|| d.text|| '',
                start:       typeof start === 'string' ? start : String(start),
                end:         typeof end   === 'string' ? end   : String(end),
                kind:        d.kind        || '',
                description: d.description  || '',
                reminder:    d.reminder     || 'none',
                status:      d.status       || 'pending',
                locked:      d.locked       || false,
                readonly:    d.readonly     || false,
                recurring:   d.recurring    || false,
                schedule_id: d.schedule_id  || '',
                sop_id:      d.sop_id      || ''  // 新增：映射 sop_id 字段
            };
        }

        // ---- 行内按钮：切换完成状态 ----
        function toggleEventStatus(ev) {
            var newStatus = ev.status === "done" ? "pending" : "done";
            var apiUrl = ev.recurring ? "/api/schedules/" + ev.schedule_id + "/occurrence-status"
                                     : "/api/events/status";
            var body = ev.recurring
                ? JSON.stringify({id: ev.id, date: ev.start.slice(0,10), status: newStatus})
                : JSON.stringify({id: ev.id, day: ev.start.slice(0,10), status: newStatus});
            fetch(apiUrl, { method: "POST", headers: {"Content-Type":"application/json"}, body: body })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.ok) loadEvents();
                });
        }

        // ---- 行内按钮：切换锁定状态 ----
        function toggleEventLock(ev) {
            var newLocked = !ev.locked;
            var apiUrl = ev.recurring ? "/api/schedules/" + ev.schedule_id + "/occurrence-lock"
                                     : "/api/events/lock";
            var body = ev.recurring
                ? JSON.stringify({id: ev.id, date: ev.start.slice(0,10), locked: newLocked})
                : JSON.stringify({id: ev.id, day: ev.start.slice(0,10), locked: newLocked});
            fetch(apiUrl, { method: "POST", headers: {"Content-Type":"application/json"}, body: body })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.ok) loadEvents();
                });
        }

        // ---- 点击事件后弹出的编辑菜单（编辑 + 删除）----
        function showEditMenu(ev, x, y) {
            var old = document.getElementById("ctx-menu");
            if (old) old.remove();

            // 如果没有坐标（从 ✏️ 按钮点击），居中显示
            if (x === undefined || y === undefined) {
                x = Math.max(0, (window.innerWidth - 160) / 2);
                y = Math.max(0, (window.innerHeight - 200) / 2);
            }

            var menu = document.createElement("div");
            menu.id = "ctx-menu";
            menu.style.cssText = "position:fixed;top:" + y + "px;left:" + x + "px;background:#1a1a2e;color:#eee;border:1px solid #0f3460;border-radius:10px;padding:6px 0;z-index:1001;min-width:140px;box-shadow:0 8px 24px rgba(0,0,0,0.5);font-size:13px;font-family:Microsoft YaHei,PingFang SC,sans-serif;";

            function addItem(label, fn) {
                var item = document.createElement("div");
                item.innerText = label;
                item.style.cssText = "padding:8px 18px;cursor:pointer;white-space:nowrap;";
                item.addEventListener("mouseenter", function() { item.style.background = "#0f3460"; });
                item.addEventListener("mouseleave", function() { item.style.background = "transparent"; });
                item.addEventListener("click", function() { menu.remove(); fn(); });
                menu.appendChild(item);
            }

            var isDone = ev.status === "done";

            if (ev.recurring) {
                addItem(isDone ? "\u2B6C\uFE0F 标记未完成" : "\u2705 标记完成", function() {
                    toggleEventStatus(ev);
                });
                addItem(ev.locked ? "\uD83D\uDD13 解锁" : "\uD83D\uDD12 锁定", function() {
                    toggleEventLock(ev);
                });
                addItem("\u270F\uFE0F 编辑重复计划", function() {
                    // 编辑 schedule 模板
                    fetch("/api/schedules/" + ev.schedule_id)
                        .then(function(r) { return r.json(); })
                        .then(function(data) {
                            if (data.ok && data.schedule) {
                                showScheduleEditDialog(data.schedule);
                            } else {
                                alert("无法加载重复事件信息");
                            }
                        });
                });
                addItem("\uD83D\uDDE1\uFE0F 删除重复计划", function() {
                    if (!confirm("确定删除此重复计划？所有由它生成的事件将消失。")) return;
                    fetch("/api/schedules/" + ev.schedule_id, { method: "DELETE" })
                        .then(function(r) { return r.json(); })
                        .then(function(data) {
                            if (data.ok) loadEvents();
                            else alert("删除失败");
                        });
                });
            } else {
                addItem(isDone ? "\u2B6C\uFE0F 标记未完成" : "\u2705 标记完成", function() {
                    toggleEventStatus(ev);
                });
                addItem(ev.locked ? "\uD83D\uDD13 解锁" : "\uD83D\uDD12 锁定", function() {
                    toggleEventLock(ev);
                });
                addItem("\u270F\uFE0F 编辑", function() {
                    showEditDialog(ev);
                });
                addItem("\uD83D\uDDE1\uFE0F 删除", function() {
                    if (!confirm("确定删除此事件？")) return;
                    fetch("/api/events/delete", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({id: ev.id, day: ev.start.slice(0,10)})
                    }).then(function(r) { return r.json(); }).then(function(data) {
                        if (data.ok) loadEvents();
                    });
                });
            }

            document.body.appendChild(menu);

            // Click outside closes menu
            setTimeout(function() {
                document.addEventListener("click", function closeMenu(e) {
                    if (!menu.contains(e.target)) {
                        menu.remove();
                        document.removeEventListener("click", closeMenu);
                    }
                });
            }, 0);
        }

        // ---- 分类图标 ----
        var KIND_ICON = {
            "sop": "\uD83D\uDCCB ",
            "tool": "\uD83D\uDD27 ",
            "reminder": "\u23F0 ",
            "external": "\uD83D\uDD17 ",
            "marker": "\uD83C\uDFF7\uFE0F "
        };

        // ---- Helper: add icon prefix to title ----
        function withIcon(title, kind) {
            var icon = KIND_ICON[kind] || "";
            if (title.startsWith(icon)) return title;
            return icon + title;
        }

        // ---- Helper: strip icon prefix from title ----
        function stripIcon(text) {
            for (var k in KIND_ICON) {
                var prefix = KIND_ICON[k];
                if (text.startsWith(prefix)) return text.slice(prefix.length);
            }
            return text;
        }

        // ---- Week range display ----
        function updateWeekRange() {
            const el = document.getElementById("week-range");
            if (!el) return;
            if (currentView === "Week") {
                const startStr = currentStart.format("YYYY年M月D日");
                const endStr   = currentStart.add(6, "day").format("M月D日");
                el.innerText = startStr + " - " + endStr;
            } else {
                el.innerText = currentStart.format("YYYY年M月");
            }
        }

        // ---- Navigation ----
        window.navWeek   = function(delta) {
            cellBackgrounds = {};  // 清空旧数据，避免旧颜色闪烁
            currentStart = currentStart.add(delta, "week");
            dp.startDate = currentStart.format("YYYY-MM-DD");
            loadEvents();
            updateWeekRange();
        };
        window.navToday  = function() {
            cellBackgrounds = {};
            currentStart = dayjs().startOf("week").add(1, "day"); // 周日+1=周一
            dp.startDate = currentStart.format("YYYY-MM-DD");
            loadEvents();
            updateWeekRange();
        };
        window.switchView = function() {
            cellBackgrounds = {};
            if (currentView === "Week") {
                currentView  = "Month";
                dp.viewType = "Month";
            } else {
                currentView  = "Week";
                dp.viewType = "Week";
            }
            loadEvents();
            updateWeekRange();
        };

        // ---- Load events + cell backgrounds (single dp.update) ----
        function loadEvents() {
            const s = currentStart.format("YYYY-MM-DD");
            const e = currentStart.add(6, "day").format("YYYY-MM-DD"); // 周一+6=周日
            Promise.all([
                fetch("/api/events?start=" + s + "&end=" + e).then(function(r) {
                    if (!r.ok) throw new Error("HTTP " + r.status);
                    return r.json();
                }),
                fetch("/api/cell-backgrounds?start=" + s + "&end=" + e).then(function(r) {
                    if (!r.ok) throw new Error("HTTP " + r.status);
                    return r.json();
                })
            ]).then(function(results) {
                var events = results[0];
                var bgData = results[1];

                cellBackgrounds = bgData.dates || {};

                // 统一事件颜色为中性紫色（用户事件）
                events.forEach(function(ev) {
                    if (!ev.backColor) {
                        ev.backColor = "#7F77DD";
                        ev.barColor = "#6C63FF";
                    }
                });
                dp.events.list = events;
                dp.update();

                var userEvents = events.filter(function(ev) {
                    return ev.kind !== "marker" || (ev.id && ev.id.startsWith("marker-user-"));
                });
                var guide = document.getElementById("empty-guide");
                if (guide) guide.style.display = userEvents.length === 0 ? "block" : "none";
            }).catch(function() {
                cellBackgrounds = {};
                dp.events.list = [];
                dp.update();
            });
        }

        // ---- Create dialog (replaces prompt()) ----
        function showCreateDialog(start, end) {
            var existing = document.getElementById("dlg-overlay-create");
            if (existing) existing.remove();

            var overlay = document.createElement("div");
            overlay.id = "dlg-overlay-create";
            overlay.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.55);display:flex;align-items:center;justify-content:center;z-index:1000;";

            var html = '';
            html += '<div style="background:#16213e;color:#eee;padding:28px;border-radius:14px;min-width:340px;max-width:420px;box-shadow:0 8px 32px rgba(0,0,0,0.5);font-family:Microsoft YaHei,PingFang SC,sans-serif;">';
            html +=   '<div style="font-size:18px;font-weight:bold;color:#e94560;margin-bottom:18px;">新建事项</div>';
            html +=   '<div style="margin-bottom:14px;">';
            html +=     '<div style="font-size:13px;color:#aaa;margin-bottom:5px;">标题</div>';
            html +=     '<input id="dlg-create-title" type="text" style="width:100%;padding:9px 12px;border:1px solid #0f3460;background:#1a1a2e;color:#eee;border-radius:8px;font-size:14px;box-sizing:border-box;" placeholder="输入事项标题">';
            html +=   '</div>';
            html +=   '<div style="display:flex;gap:10px;margin-bottom:14px;">';
            html +=     '<div style="flex:1;">';
            html +=       '<div style="font-size:13px;color:#aaa;margin-bottom:5px;">开始时间</div>';
            html +=       '<input id="dlg-create-start" type="datetime-local" style="width:100%;max-width:100%;padding:7px 10px;border:1px solid #0f3460;background:#1a1a2e;color:#eee;border-radius:8px;font-size:13px;box-sizing:border-box;">';
            html +=     '</div>';
            html +=     '<div style="flex:1;min-width:0;">';
            html +=       '<div style="font-size:13px;color:#aaa;margin-bottom:5px;">结束时间</div>';
            html +=       '<input id="dlg-create-end" type="datetime-local" style="width:100%;max-width:100%;padding:7px 10px;border:1px solid #0f3460;background:#1a1a2e;color:#eee;border-radius:8px;font-size:13px;box-sizing:border-box;">';
            html +=     '</div>';
            html +=   '</div>';
            html +=   '<div style="margin-bottom:18px;">';
            html +=     '<div style="font-size:13px;color:#aaa;margin-bottom:5px;">分类</div>';
            html +=     '<select id="dlg-create-kind" style="width:100%;padding:9px 12px;border:1px solid #0f3460;background:#1a1a2e;color:#eee;border-radius:8px;font-size:14px;">';
            html +=       '<option value="reminder">提醒</option>';
            html +=       '<option value="sop">酷家乐SOP</option>';
            html +=       '<option value="tool">工具</option>';
            html +=       '<option value="external">外部事件</option>';
            html +=       '<option value="marker">标记日</option>';
            html +=     '</select>';
            html +=   '</div>';
            html +=   '<div style="margin-bottom:18px;">';
            html +=     '<div style="font-size:13px;color:#aaa;margin-bottom:5px;">备注</div>';
            html +=     '<textarea id="dlg-create-desc" style="width:100%;height:60px;padding:9px 12px;border:1px solid #0f3460;background:#1a1a2e;color:#eee;border-radius:8px;font-size:14px;box-sizing:border-box;resize:vertical;" placeholder="可选：添加备注或描述"></textarea>';
            html +=   '</div>';
            html +=   '<div style="margin-bottom:18px;">';
            html +=     '<div style="font-size:13px;color:#aaa;margin-bottom:5px;">提醒</div>';
            html +=     '<select id="dlg-create-reminder" style="width:100%;padding:9px 12px;border:1px solid #0f3460;background:#1a1a2e;color:#eee;border-radius:8px;font-size:14px;">';
            html +=       '<option value="none">无</option>';
            html +=       '<option value="at_time">事件开始时</option>';
            html +=       '<option value="15_min">提前 15 分钟</option>';
            html +=       '<option value="30_min">提前 30 分钟</option>';
            html +=       '<option value="1_hour">提前 1 小时</option>';
            html +=     '</select>';
            html +=   '</div>';
            html +=   '<div style="margin-bottom:18px;">';
            html +=     '<div style="font-size:13px;color:#aaa;margin-bottom:5px;">重复</div>';
            html +=     '<select id="dlg-create-repeat" style="width:100%;padding:9px 12px;border:1px solid #0f3460;background:#1a1a2e;color:#eee;border-radius:8px;font-size:14px;">';
            html +=       '<option value="none">不重复</option>';
            html +=       '<option value="daily">每天</option>';
            html +=       '<option value="weekly">每周</option>';
            html +=       '<option value="monthly">每月</option>';
            html +=       '<option value="yearly">每年</option>';
            html +=       '<option value="preheat">节假日前X天</option>';
            html +=     '</select>';
            html +=   '</div>';
            html +=   '<div id="dlg-create-preheat" style="display:none;margin-bottom:18px;padding:14px;background:#1a1a2e;border-radius:8px;border:1px solid #0f3460;">';
            html +=     '<div style="font-size:14px;font-weight:bold;color:#FF5722;margin-bottom:12px;">⏰ 节假日前预热设置</div>';
            html +=     '<div style="margin-bottom:10px;">';
            html +=       '<div style="font-size:12px;color:#aaa;margin-bottom:4px;">特殊日子类型</div>';
            html +=       '<select id="dlg-preheat-type" style="width:100%;padding:7px 10px;border:1px solid #0f3460;background:#16213e;color:#eee;border-radius:6px;font-size:13px;">';
            html +=         '<option value="shopping_festival">购物节</option>';
            html +=         '<option value="holiday">法定节假日</option>';
            html +=         '<option value="custom_holiday">自定义节假日</option>';
            html +=       '</select>';
            html +=     '</div>';
            html +=     '<div style="margin-bottom:10px;">';
            html +=       '<div style="font-size:12px;color:#aaa;margin-bottom:4px;">选择特殊日子</div>';
            html +=       '<select id="dlg-preheat-target" style="width:100%;padding:7px 10px;border:1px solid #0f3460;background:#16213e;color:#eee;border-radius:6px;font-size:13px;">';
            html +=         '<option value="">加载中...</option>';
            html +=       '</select>';
            html +=     '</div>';
            html +=     '<div style="margin-bottom:10px;">';
            html +=       '<div style="font-size:12px;color:#aaa;margin-bottom:4px;">提前天数</div>';
            html +=       '<input id="dlg-preheat-days" type="number" value="7" min="1" max="365" style="width:100%;padding:7px 10px;border:1px solid #0f3460;background:#16213e;color:#eee;border-radius:6px;font-size:13px;box-sizing:border-box;">';
            html +=     '</div>';
            html +=     '<div style="margin-bottom:10px;">';
            html +=       '<div style="font-size:12px;color:#aaa;margin-bottom:4px;">重复范围</div>';
            html +=       '<select id="dlg-preheat-scope" style="width:100%;padding:7px 10px;border:1px solid #0f3460;background:#16213e;color:#eee;border-radius:6px;font-size:13px;">';
            html +=         '<option value="yearly">每年</option>';
            html +=         '<option value="once">仅今年</option>';
            html +=       '</select>';
            html +=     '</div>';
            html +=   '</div>';
            html +=   '<div style="display:flex;gap:10px;justify-content:flex-end;">';
            html +=     '<button id="dlg-create-cancel" style="padding:8px 20px;background:transparent;color:#aaa;border:1px solid #444;border-radius:8px;cursor:pointer;font-size:14px;">取消</button>';
            html +=     '<button id="dlg-create-ok" style="padding:8px 20px;background:#e94560;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:bold;">创建</button>';
            html +=   '</div>';
            html += '</div>';

            overlay.innerHTML = html;
            document.body.appendChild(overlay);
            setTimeout(function() {
                var input = document.getElementById("dlg-create-title");
                if (input) input.focus();
            }, 80);

            overlay.addEventListener("click", function(e) {
                if (e.target === overlay) overlay.remove();
            });
            document.getElementById("dlg-create-cancel").addEventListener("click", function() {
                overlay.remove();
            });

            // Preheat fields show/hide
            document.getElementById("dlg-create-repeat").addEventListener("change", function() {
                var preheatDiv = document.getElementById("dlg-create-preheat");
                if (this.value === "preheat") {
                    preheatDiv.style.display = "block";
                    loadSpecialDays();
                } else {
                    preheatDiv.style.display = "none";
                }
            });

            // Load special days when preheat type changes
            document.getElementById("dlg-preheat-type").addEventListener("change", function() {
                loadSpecialDays();
            });

            function loadSpecialDays() {
                var type = document.getElementById("dlg-preheat-type").value;
                var year = new Date().getFullYear();
                fetch("/api/special-days?year=" + year)
                    .then(function(r) { return r.json(); })
                    .then(function(data) {
                        var select = document.getElementById("dlg-preheat-target");
                        select.innerHTML = "";
                        if (!data.ok) {
                            select.innerHTML = "<option value=''>加载失败</option>";
                            return;
                        }
                        var days = [];
                        if (type === "shopping_festival") days = data.special_days.shopping_festivals;
                        else if (type === "holiday") days = data.special_days.holidays;
                        else if (type === "custom_holiday") days = data.special_days.custom_holidays;

                        if (days.length === 0) {
                            select.innerHTML = "<option value=''>无数据</option>";
                            return;
                        }
                        days.forEach(function(day) {
                            var opt = document.createElement("option");
                            opt.value = day.date;
                            opt.setAttribute("data-name", day.name);
                            opt.setAttribute("data-mmdd", day.mmdd || day.date.slice(5,10));
                            opt.innerText = day.name + " (" + day.date + ")";
                            select.appendChild(opt);
                        });
                    })
                    .catch(function() {
                        document.getElementById("dlg-preheat-target").innerHTML = "<option value=''>加载失败</option>";
                    });
            }

            // Fill start/end time inputs with drag-selected values
            var startVal = start.toString ? start.toString() : new Date(start).toISOString();
            var endVal   = end.toString ? end.toString() : new Date(end).toISOString();
            // Convert to datetime-local format: "2026-07-03T14:30"
            startVal = startVal.replace('T', ' ').substring(0, 16).replace(' ', 'T');
            endVal   = endVal.replace('T', ' ').substring(0, 16).replace(' ', 'T');
            document.getElementById("dlg-create-start").value = startVal;
            document.getElementById("dlg-create-end").value   = endVal;

            // 开始时间变化时，自动调整结束时间（如果结束时间更早或为空）
            document.getElementById("dlg-create-start").addEventListener("change", function() {
                var startVal = this.value;
                var endInput = document.getElementById("dlg-create-end");
                if (!startVal) return;
                var startDate = new Date(startVal);
                if (isNaN(startDate)) return;
                startDate.setHours(startDate.getHours() + 1);
                var newEndVal = startDate.toISOString().slice(0, 16);
                if (!endInput.value || endInput.value <= startVal) {
                    endInput.value = newEndVal;
                }
            });

            // 结束时间不能早于开始时间（用户手动改结束时也联动）
            document.getElementById("dlg-create-end").addEventListener("change", function() {
                var startVal = document.getElementById("dlg-create-start").value;
                if (!startVal || !this.value) return;
                if (this.value <= startVal) {
                    alert("结束时间必须晚于开始时间，已自动调整。");
                    var startDate = new Date(startVal);
                    startDate.setHours(startDate.getHours() + 1);
                    this.value = startDate.toISOString().slice(0, 16);
                }
            });

            document.getElementById("dlg-create-ok").addEventListener("click", function() {
                var titleInput = document.getElementById("dlg-create-title");
                var kindSelect = document.getElementById("dlg-create-kind");
                var startInput = document.getElementById("dlg-create-start");
                var endInput   = document.getElementById("dlg-create-end");
                var title = titleInput.value.trim();
                var kind  = kindSelect.value;
                var desc  = document.getElementById("dlg-create-desc").value.trim();
                var reminder = document.getElementById("dlg-create-reminder").value;
                var repeat = document.getElementById("dlg-create-repeat").value;
                var startStr = startInput.value ? startInput.value + ":00" : (start.toString ? start.toString() : new Date(start).toISOString());
                var endStr   = endInput.value   ? endInput.value + ":00"   : (end.toString   ? end.toString()   : new Date(end).toISOString());
                if (!title) { alert("请输入标题"); return; }

                // 时间校验：结束时间必须晚于开始时间，自动调整
                if (startInput.value && endInput.value && endInput.value <= startInput.value) {
                    var startDate = new Date(startInput.value);
                    startDate.setMinutes(startDate.getMinutes() + 30);
                    endInput.value = startDate.toISOString().slice(0, 16);
                }
                // 从开始/结束时间计算实际时长（分钟）
                var durMinutes = 60;
                if (startInput.value && endInput.value) {
                    var startH = parseInt(startInput.value.slice(11,13)) || 0;
                    var startM = parseInt(startInput.value.slice(14,16)) || 0;
                    var endH = parseInt(endInput.value.slice(11,13)) || 0;
                    var endM = parseInt(endInput.value.slice(14,16)) || 0;
                    var diff = (endH * 60 + endM) - (startH * 60 + startM);
                    if (diff > 0) durMinutes = diff;
                }

                // Handle preheat mode
                if (repeat === "preheat") {
                    var targetSelect = document.getElementById("dlg-preheat-target");
                    var selectedOpt = targetSelect.options[targetSelect.selectedIndex];
                    if (!selectedOpt || !selectedOpt.value) {
                        alert("请选择特殊日子");
                        return;
                    }
                    var targetDate = selectedOpt.value;
                    var targetName = selectedOpt.getAttribute("data-name");
                    var targetMmdd = selectedOpt.getAttribute("data-mmdd") || targetDate.slice(5,10);
                    var preheatDays = parseInt(document.getElementById("dlg-preheat-days").value) || 7;
                    var scope = document.getElementById("dlg-preheat-scope").value;
                    var targetType = document.getElementById("dlg-preheat-type").value;

                    var scheduleData = {
                        title: withIcon(title, kind),
                        repeat_mode: "preheat",
                        target_type: targetType,
                        target_id: targetName,
                        target_date: targetMmdd,
                        target_name: targetName,
                        preheat_days: preheatDays,
                        start_time: startInput.value ? startInput.value.slice(11,16) : "09:00",
                        duration_minutes: durMinutes,
                        kind: kind,
                        description: desc,
                        reminder: reminder,
                        exec_mode: "manual",
                        scope: scope,
                        year: scope === "once" ? new Date().getFullYear() : 0,
                    };

                    fetch("/api/schedules", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify(scheduleData)
                    }).then(async function(r) {
                        if (!r.ok) {
                            var text = await r.text();
                            throw new Error("HTTP " + r.status + "：" + text.substring(0, 400));
                        }
                        return r.json();
                    }).then(function(data) {
                        if (data.ok) {
                            overlay.remove();
                            loadEvents();
                            alert("✅ 预热事件已创建！每年节假日前" + preheatDays + "天将自动生成事件。");
                        } else {
                            alert("创建失败：" + (data.error || "未知错误"));
                        }
                    }).catch(function(err) {
                        alert("❌ " + err.toString());
                    });
                    return;
                }

                // Handle recurring (daily/weekly/monthly/yearly) mode
                if (repeat === "daily" || repeat === "weekly" || repeat === "monthly" || repeat === "yearly") {
                    var startDateStr = startInput.value ? startInput.value.slice(0, 10) : new Date().toISOString().slice(0, 10);
                    var startTimeStr = startInput.value ? startInput.value.slice(11, 16) : "09:00";

                    var recurringData = {
                        title: withIcon(title, kind),
                        repeat_mode: repeat,
                        start_date: startDateStr,
                        start_time: startTimeStr,
                        duration_minutes: durMinutes,
                        kind: kind,
                        description: desc,
                        reminder: reminder,
                        exec_mode: "manual",
                        scope: "yearly",
                        year: 0,
                    };

                    var repeatLabel = {"daily": "每天", "weekly": "每周", "monthly": "每月", "yearly": "每年"}[repeat];

                    fetch("/api/schedules", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify(recurringData)
                    }).then(async function(r) {
                        if (!r.ok) {
                            var text = await r.text();
                            throw new Error("HTTP " + r.status + "：" + text.substring(0, 400));
                        }
                        return r.json();
                    }).then(function(data) {
                        if (data.ok) {
                            overlay.remove();
                            loadEvents();
                            alert("✅ " + repeatLabel + "重复事件已创建！从 " + startDateStr + " 起按周期自动生成。");
                        } else {
                            alert("创建失败：" + (data.error || "未知错误"));
                        }
                    }).catch(function(err) {
                        alert("❌ " + err.toString());
                    });
                    return;
                }

                // Regular event creation
                // SOP 事件：设置 sop_id（当前仅支持酷家乐）
                var sopId = (kind === "sop") ? "kujiale" : "";
                fetch("/api/events/create", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({
                        text: withIcon(title, kind),
                        start: startStr,
                        end:   endStr,
                        kind: kind,
                        description: desc,
                        reminder: reminder,
                        exec_mode: "manual",
                        sop_id: sopId  // 新增：SOP ID
                    })
                }).then(async function(r) {
                    if (!r.ok) {
                        var text = await r.text();
                        throw new Error("HTTP " + r.status + "：" + text.substring(0, 400));
                    }
                    return r.json();
                }).then(function(data) {
                    if (data.ok) {
                        overlay.remove();
                        loadEvents();
                        // T4: 创建 SOP 事件后引导到 SOP 页面
                        if (kind === "sop") {
                            if (confirm("✅ SOP 事件已创建！\n\n是否打开 SOP 流程页？")) {
                                window.open("/sop/" + sopId, "_blank");
                            }
                        }
                    } else {
                        alert("创建失败：" + (data.error || "未知错误"));
                    }
                }).catch(function(err) {
                    alert("❌ " + err.toString());
                });
            });
        }

        // ---- Helper: generate time select options (30-min intervals) ----
        // minTime: "HH:MM" — 只显示 >= minTime + 30min 的选项
        // maxTime: "HH:MM" — 只显示 <= maxTime - 30min 的选项
        function getTimeSelectHtml(selectedTime, minTime, maxTime) {
            // 四舍五入到最近的 30 分钟
            var selMin = 0;
            if (selectedTime) {
                var parts = selectedTime.split(":");
                var h = parseInt(parts[0]) || 0;
                var m = parseInt(parts[1]) || 0;
                if (m < 15)      selMin = h * 60 + 0;
                else if (m < 45) selMin = h * 60 + 30;
                else               selMin = ((h + 1) % 24) * 60 + 0;
            }
            // 计算最小允许时间（分钟数）
            var minMin = 0;
            if (minTime) {
                var mp = minTime.split(":");
                minMin = parseInt(mp[0]) * 60 + parseInt(mp[1]) + 30; // 至少比开始时间晚30分钟
            }
            // 计算最大允许时间（分钟数）
            var maxMin = 1439;
            if (maxTime) {
                var xp = maxTime.split(":");
                maxMin = parseInt(xp[0]) * 60 + parseInt(xp[1]) - 30; // 至少比结束时间早30分钟
                if (maxMin < 0) maxMin = -1; // 不允许任何选项
            }
            var options = '';
            for (var totalMin = 0; totalMin < 1440; totalMin += 30) {
                if (totalMin < minMin) continue;       // 早于最小允许时间，跳过
                if (maxMin >= 0 && totalMin > maxMin) continue; // 晚于最大允许时间，跳过
                var hh = Math.floor(totalMin / 60);
                var mm = totalMin % 60;
                var val = (hh < 10 ? "0" : "") + hh + ":" + (mm < 10 ? "0" : "") + mm;
                var selected = (totalMin === selMin) ? " selected" : "";
                // 如果选中的时间被过滤掉了，自动选第一个可用选项
                if (selectedTime && totalMin === selMin && (totalMin < minMin || (maxMin >= 0 && totalMin > maxMin))) {
                    selected = ""; // 原来选中的时间现在不合法，不选中
                }
                options += '<option value="' + val + '"' + selected + '>' + val + '</option>';
            }
            // 如果没有选中任何选项，选中第一个
            if (options && !options.includes('selected')) {
                options = options.replace('<option', '<option selected', 1);
            }
            return options;
        }

        // ---- Edit dialog (replaces prompt()) ----
        function showEditDialog(ev) {
            var existing = document.getElementById("dlg-overlay-edit");
            if (existing) existing.remove();

            var overlay = document.createElement("div");
            overlay.id = "dlg-overlay-edit";
            overlay.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.55);display:flex;align-items:center;justify-content:center;z-index:1000;";

            var html = '';
            html += '<div style="background:#16213e;color:#eee;padding:28px;border-radius:14px;min-width:340px;max-width:420px;box-shadow:0 8px 32px rgba(0,0,0,0.5);font-family:Microsoft YaHei,PingFang SC,sans-serif;">';
            html +=   '<div style="font-size:18px;font-weight:bold;color:#2196F3;margin-bottom:18px;">编辑事项</div>';

            html +=   '<div style="margin-bottom:14px;">';
            html +=     '<div style="font-size:13px;color:#aaa;margin-bottom:5px;">标题</div>';
            html +=     '<input id="dlg-edit-title" type="text" value="' + escapeHtml(ev.text) + '" style="width:100%;padding:9px 12px;border:1px solid #0f3460;background:#1a1a2e;color:#eee;border-radius:8px;font-size:14px;box-sizing:border-box;">';
            html +=   '</div>';

            html +=   '<div style="margin-bottom:14px;">';
            html +=     '<div style="font-size:13px;color:#aaa;margin-bottom:5px;">开始时间</div>';
            html +=     '<div style="display:flex;gap:8px;">';
            html +=       '<input id="dlg-edit-start-date" type="date" value="' + (ev.start ? ev.start.slice(0,10) : '') + '" style="flex:1;padding:9px 12px;border:1px solid #0f3460;background:#1a1a2e;color:#eee;border-radius:8px;font-size:14px;box-sizing:border-box;" onchange="syncEndDateMin()">';
            html +=       '<select id="dlg-edit-start-time" style="width:120px;padding:9px 12px;border:1px solid #0f3460;background:#1a1a2e;color:#eee;border-radius:8px;font-size:14px;box-sizing:border-box;" onchange="syncEndTimeMin()">' + getTimeSelectHtml(ev.start ? ev.start.slice(11,16) : null, null, null) + '</select>';
            html +=     '</div>';
            html +=   '</div>';
            html +=   '<div style="margin-bottom:14px;">';
            html +=     '<div style="font-size:13px;color:#aaa;margin-bottom:5px;">结束时间</div>';
            html +=     '<div style="display:flex;gap:8px;">';
            html +=       '<input id="dlg-edit-end-date" type="date" value="' + (ev.end ? ev.end.slice(0,10) : '') + '" style="flex:1;padding:9px 12px;border:1px solid #0f3460;background:#1a1a2e;color:#eee;border-radius:8px;font-size:14px;box-sizing:border-box;" onchange="syncStartDateMax()">';
            html +=       '<select id="dlg-edit-end-time" style="width:120px;padding:9px 12px;border:1px solid #0f3460;background:#1a1a2e;color:#eee;border-radius:8px;font-size:14px;box-sizing:border-box;" onchange="syncStartTimeMax()">' + getTimeSelectHtml(ev.end ? ev.end.slice(11,16) : null, ev.start ? ev.start.slice(11,16) : null, null) + '</select>';
            html +=     '</div>';
            html +=   '</div>';

            html +=   '<div style="margin-bottom:14px;">';
            html +=     '<div style="font-size:13px;color:#aaa;margin-bottom:5px;">备注</div>';
            html +=     '<textarea id="dlg-edit-desc" style="width:100%;height:60px;padding:9px 12px;border:1px solid #0f3460;background:#1a1a2e;color:#eee;border-radius:8px;font-size:14px;box-sizing:border-box;resize:vertical;">' + escapeHtml(ev.description || '') + '</textarea>';
            html +=   '</div>';
            html +=   '<div style="margin-bottom:18px;">';
            html +=     '<div style="font-size:13px;color:#aaa;margin-bottom:5px;">分类</div>';
            html +=     '<select id="dlg-edit-kind" style="width:100%;padding:9px 12px;border:1px solid #0f3460;background:#1a1a2e;color:#eee;border-radius:8px;font-size:14px;">';
            html +=       '<option value="reminder"' + (ev.kind === 'reminder' ? ' selected' : '') + '>提醒</option>';
            html +=       '<option value="sop"' + (ev.kind === 'sop' ? ' selected' : '') + '>酷家乐SOP</option>';
            html +=       '<option value="tool"' + (ev.kind === 'tool' ? ' selected' : '') + '>工具</option>';
            html +=       '<option value="external"' + (ev.kind === 'external' ? ' selected' : '') + '>外部事件</option>';
            html +=       '<option value="marker"' + (ev.kind === 'marker' ? ' selected' : '') + '>标记日</option>';
            html +=     '</select>';
            html +=   '</div>';
            html +=   '<div style="margin-bottom:18px;">';
            html +=     '<div style="font-size:13px;color:#aaa;margin-bottom:5px;">提醒</div>';
            html +=     '<select id="dlg-edit-reminder" style="width:100%;padding:9px 12px;border:1px solid #0f3460;background:#1a1a2e;color:#eee;border-radius:8px;font-size:14px;">';
            html +=       '<option value="none"' +   ((ev.reminder||'none') === 'none'   ? ' selected' : '') + '>无</option>';
            html +=       '<option value="at_time"' + ((ev.reminder||'none') === 'at_time' ? ' selected' : '') + '>事件开始时</option>';
            html +=       '<option value="15_min"' +  ((ev.reminder||'none') === '15_min'  ? ' selected' : '') + '>提前 15 分钟</option>';
            html +=       '<option value="30_min"' +  ((ev.reminder||'none') === '30_min'  ? ' selected' : '') + '>提前 30 分钟</option>';
            html +=       '<option value="1_hour"' +  ((ev.reminder||'none') === '1_hour'  ? ' selected' : '') + '>提前 1 小时</option>';
            html +=     '</select>';
            html +=   '</div>';

            html +=   '<div style="display:flex;gap:10px;justify-content:space-between;">';
            html +=     '<button id="dlg-edit-delete" style="padding:8px 20px;background:transparent;color:#F44336;border:1px solid #F44336;border-radius:8px;cursor:pointer;font-size:14px;">🗑️ 删除</button>';
            html +=     '<div style="display:flex;gap:10px;">';
            html +=       '<button id="dlg-edit-cancel" style="padding:8px 20px;background:transparent;color:#aaa;border:1px solid #444;border-radius:8px;cursor:pointer;font-size:14px;">取消</button>';
            html +=       '<button id="dlg-edit-ok" style="padding:8px 20px;background:#2196F3;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:bold;">保存</button>';
            html +=     '</div>';
            html +=   '</div>';
            html += '</div>';

            overlay.innerHTML = html;
            document.body.appendChild(overlay);
            setTimeout(function() {
                var input = document.getElementById("dlg-edit-title");
                if (input) input.focus();
            }, 80);

            // 时间联动：选开始时间后，结束时间自动过滤掉早于开始时间的选项，并自动修正无效选择
            window.syncEndTimeMin = function() {
                var startSel = document.getElementById("dlg-edit-start-time");
                var endSel   = document.getElementById("dlg-edit-end-time");
                if (!startSel || !endSel) return;
                var startTime = startSel.value;
                // 重刷结束时间选项（只显示 >= 开始时间+30分钟 的选项）
                var newOptions = getTimeSelectHtml(null, startTime, null);
                endSel.innerHTML = newOptions;
                // 如果结束时间现在早于开始时间+30分钟，自动选第一个合法选项
                if (endSel.value && startTime) {
                    var endMin   = parseInt(endSel.value.slice(0,2)) * 60 + parseInt(endSel.value.slice(3,5));
                    var startMin = parseInt(startTime.slice(0,2)) * 60 + parseInt(startTime.slice(3,5)) + 30;
                    if (endMin < startMin) {
                        // 选第一个合法选项
                        var firstOpt = endSel.querySelector('option');
                        if (firstOpt) endSel.value = firstOpt.value;
                    }
                }
            };
            // 时间联动：选结束时间后，开始时间自动过滤掉晚于结束时间的选项，并自动修正无效选择
            window.syncStartTimeMax = function() {
                var startSel = document.getElementById("dlg-edit-start-time");
                var endSel   = document.getElementById("dlg-edit-end-time");
                if (!startSel || !endSel) return;
                var endTime = endSel.value;
                // 重刷开始时间选项（只显示 <= 结束时间-30分钟 的选项）
                var newOptions = getTimeSelectHtml(null, null, endTime);
                startSel.innerHTML = newOptions;
                // 如果开始时间现在晚于结束时间-30分钟，自动选最后一个合法选项
                if (startSel.value && endTime) {
                    var startMin = parseInt(startSel.value.slice(0,2)) * 60 + parseInt(startSel.value.slice(3,5));
                    var endMin   = parseInt(endTime.slice(0,2)) * 60 + parseInt(endTime.slice(3,5)) - 30;
                    if (startMin > endMin) {
                        // 选最后一个合法选项
                        var opts = startSel.querySelectorAll('option');
                        if (opts.length > 0) startSel.value = opts[opts.length - 1].value;
                    }
                }
            };

            // 日期联动：选开始日期后，结束日期不能早于开始日期
            window.syncEndDateMin = function() {
                var startDateInput = document.getElementById("dlg-edit-start-date");
                var endDateInput   = document.getElementById("dlg-edit-end-date");
                if (!startDateInput || !endDateInput) return;
                var startDate = startDateInput.value;
                if (!startDate) return;
                // 如果结束日期早于开始日期，自动调整为开始日期
                if (endDateInput.value && endDateInput.value < startDate) {
                    endDateInput.value = startDate;
                }
                // 设置结束日期的 min 属性
                endDateInput.min = startDate;
            };

            // 日期联动：选结束日期后，开始日期不能晚于结束日期
            window.syncStartDateMax = function() {
                var startDateInput = document.getElementById("dlg-edit-start-date");
                var endDateInput   = document.getElementById("dlg-edit-end-date");
                if (!startDateInput || !endDateInput) return;
                var endDate = endDateInput.value;
                if (!endDate) return;
                // 如果开始日期晚于结束日期，自动调整为结束日期
                if (startDateInput.value && startDateInput.value > endDate) {
                    startDateInput.value = endDate;
                }
                // 设置开始日期的 max 属性
                startDateInput.max = endDate;
            };

            // 初始联动：对话框打开时立即过滤不合法选项
            setTimeout(function() {
                if (window.syncEndTimeMin) window.syncEndTimeMin();
                if (window.syncStartTimeMax) window.syncStartTimeMax();
                if (window.syncEndDateMin) window.syncEndDateMin();
                if (window.syncStartDateMax) window.syncStartDateMax();
            }, 0);

            overlay.addEventListener("click", function(e) {
                if (e.target === overlay) overlay.remove();
            });
            document.getElementById("dlg-edit-cancel").addEventListener("click", function() {
                overlay.remove();
            });
            document.getElementById("dlg-edit-delete").addEventListener("click", function() {
                // 区分普通事件和重复事件
                var isRecurring = ev.recurring || false;
                var scheduleId  = ev.schedule_id || "";
                var eventTitle  = stripIcon(ev.text || "");

                if (isRecurring && scheduleId) {
                    // 重复事件：删除整个调度模板
                    var msg = "确认删除重复事件「" + eventTitle + "」？\n\n删除后，以后所有天都不会再生成这个事件。\n此操作不可撤销！";
                    if (!confirm(msg)) return;
                    fetch("/api/schedules/" + encodeURIComponent(scheduleId), {
                        method: "DELETE",
                        headers: {"Content-Type": "application/json"}
                    }).then(function(r) { return r.json(); }).then(function(data) {
                        if (data.ok) { overlay.remove(); loadEvents(); }
                        else alert("删除失败：" + (data.error || "未知错误"));
                    }).catch(function(err) {
                        alert("删除出错：" + err);
                    });
                } else {
                    // 普通事件：直接删除
                    if (!confirm("确认删除事件「" + eventTitle + "」？")) return;
                    fetch("/api/events/delete", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({id: ev.id, day: ev.start.slice(0,10)})
                    }).then(function(r) { return r.json(); }).then(function(data) {
                        if (data.ok) { overlay.remove(); loadEvents(); }
                        else alert("删除失败：" + (data.error || "未知错误"));
                    }).catch(function(err) {
                        alert("删除出错：" + err);
                    });
                }
            });
            document.getElementById("dlg-edit-ok").addEventListener("click", function() {
                var titleInput = document.getElementById("dlg-edit-title");
                var kindSelect = document.getElementById("dlg-edit-kind");
                var descInput  = document.getElementById("dlg-edit-desc");
                var reminderSelect = document.getElementById("dlg-edit-reminder");
                var startDateInput = document.getElementById("dlg-edit-start-date");
                var startTimeSelect = document.getElementById("dlg-edit-start-time");
                var endDateInput   = document.getElementById("dlg-edit-end-date");
                var endTimeSelect   = document.getElementById("dlg-edit-end-time");
                var newTitle = titleInput.value.trim();
                var newKind  = kindSelect.value;
                var newDesc  = descInput.value.trim();
                var newReminder = reminderSelect.value;
                if (!newTitle) { alert("请输入标题"); return; }

                var newStart = null;
                var newEnd   = null;
                if (startDateInput.value && startTimeSelect.value) {
                    newStart = startDateInput.value + "T" + startTimeSelect.value + ":00";
                }
                if (endDateInput.value && endTimeSelect.value) {
                    newEnd = endDateInput.value + "T" + endTimeSelect.value + ":00";
                }

                // 时间校验：结束时间不能早于开始时间，自动调整
                if (newStart && newEnd && newEnd <= newStart) {
                    var startDate = new Date(newStart);
                    startDate.setMinutes(startDate.getMinutes() + 30);
                    newEnd = startDate.toISOString().slice(0, 19);
                    // 更新界面显示
                    var endDateInput = document.getElementById("dlg-edit-end-date");
                    var endTimeSelect = document.getElementById("dlg-edit-end-time");
                    if (endDateInput) endDateInput.value = newEnd.slice(0, 10);
                    if (endTimeSelect) endTimeSelect.value = newEnd.slice(11, 16);
                }

                // 判断是否为重复事件
                var isRecurring = ev.recurring || false;
                var scheduleId  = ev.schedule_id || "";

                if (isRecurring && scheduleId) {
                    // 重复事件：调 update 接口，后端写入 occurrence_overrides
                    var body = {
                        id: ev.id,
                        day: ev.start.slice(0,10),
                        text: withIcon(stripIcon(newTitle), newKind),
                        kind: newKind,
                        description: newDesc,
                        reminder: newReminder,
                        recurring: true,
                        schedule_id: scheduleId,
                    };
                    if (newStart) body.start = newStart;
                    if (newEnd)   body.end   = newEnd;
                    fetch("/api/events/update", {
                        method: "PUT",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify(body)
                    }).then(function(r) { return r.json(); }).then(function(data) {
                        if (data.ok) { overlay.remove(); loadEvents(); }
                        else alert("修改失败：" + (data.error || "未知错误"));
                    }).catch(function(err) {
                        alert("修改出错：" + err);
                    });
                } else {
                    // 普通事件：判断日期是否改变
                    var oldDay = ev.start.slice(0,10);
                    var newDay = newStart ? newStart.slice(0,10) : oldDay;
                    var dayChanged = (newDay !== oldDay);

                    if (dayChanged) {
                        // 日期改变 → 用 /api/events/move
                        var moveBody = {
                            old_day: oldDay,
                            old_id:  ev.id,
                            event:   {start: newStart, end: newEnd}
                        };
                        fetch("/api/events/move", {
                            method: "POST",
                            headers: {"Content-Type": "application/json"},
                            body: JSON.stringify(moveBody)
                        }).then(function(r) { return r.json(); }).then(function(data) {
                            if (data.ok) {
                                var updBody = {id: ev.id, day: newDay, text: withIcon(stripIcon(newTitle), newKind), kind: newKind, description: newDesc, reminder: newReminder};
                                fetch("/api/events/update", {
                                    method: "PUT",
                                    headers: {"Content-Type": "application/json"},
                                    body: JSON.stringify(updBody)
                                }).then(function(r) { return r.json(); }).then(function(data2) {
                                    if (data2.ok) { overlay.remove(); loadEvents(); }
                                    else alert("时间已更新，但其他字段修改失败：" + (data2.error || "未知错误"));
                                });
                            } else {
                                alert("移动事件失败：" + (data.error || "未知错误"));
                            }
                        }).catch(function(err) {
                            alert("移动事件出错：" + err);
                        });
                    } else {
                        // 日期未变 → 直接用 update
                        var body = {id: ev.id, day: oldDay, text: withIcon(stripIcon(newTitle), newKind), kind: newKind, description: newDesc, reminder: newReminder};
                        if (newStart) body.start = newStart;
                        if (newEnd)   body.end   = newEnd;
                        fetch("/api/events/update", {
                            method: "PUT",
                            headers: {"Content-Type": "application/json"},
                            body: JSON.stringify(body)
                        }).then(function(r) { return r.json(); }).then(function(data) {
                            if (data.ok) { overlay.remove(); loadEvents(); }
                            else alert("修改失败：" + (data.error || "未知错误"));
                        }).catch(function(err) {
                            alert("修改出错：" + err);
                        });
                    }
                }
            });
        }

        // ---- Event detail dialog ----
        function showEventDetailDialog(ev) {
            var existing = document.getElementById("dlg-overlay-detail");
            if (existing) existing.remove();

            var KNAME = {"sop":"酷家乐SOP","tool":"工具","reminder":"提醒","external":"外部事件","marker":"标记日"};
            var kname   = KNAME[ev.kind] || ev.kind;
            var isDone  = ev.status === "done";
            var statusStr = isDone ? "\u2705 已完成" : (ev.status === "skipped" ? "\u23F3 已跳过" : "\u23F3 待完成");

            var overlay = document.createElement("div");
            overlay.id = "dlg-overlay-detail";
            overlay.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.55);display:flex;align-items:center;justify-content:center;z-index:1000;";

            var html = '';
            html += '<div style="background:#16213e;color:#eee;padding:28px;border-radius:14px;min-width:340px;max-width:420px;box-shadow:0 8px 32px rgba(0,0,0,0.5);font-family:Microsoft YaHei,PingFang SC,sans-serif;">';
            html +=   '<div style="font-size:17px;font-weight:bold;color:#E0E0E0;margin-bottom:6px;">' + escapeHtml(ev.text) + '</div>';
            html +=   '<div style="font-size:13px;color:#aaa;margin-bottom:4px;">' + dayjs(ev.start).format("YYYY-MM-DD HH:mm") + ' - ' + dayjs(ev.end).format("HH:mm") + '</div>';
            html +=   '<div style="font-size:13px;color:#aaa;margin-bottom:4px;">分类：' + kname + '</div>';
            html +=   '<div style="font-size:13px;color:#aaa;margin-bottom:4px;">状态：' + statusStr + '</div>';
            if (ev.description) {
            html +=   '<div style="font-size:13px;color:#ccc;margin-bottom:18px;padding:8px;background:#1a1a2e;border-radius:8px;">' + escapeHtml(ev.description) + '</div>';
            } else {
            html +=   '<div style="font-size:13px;color:#666;margin-bottom:18px;">（无备注）</div>';
            }
            // T6: SOP 事件显示"打开 SOP 流程页"按钮
            if (ev.kind === "sop") {
                var sopId = ev.sop_id || 'kujiale';  // 兼容旧数据
                html +=   '<div style="margin-bottom:14px;">';
                html +=     '<button onclick="window.open(\'/sop/' + sopId + '\', \'_blank\');" style="width:100%;padding:10px;background:#4CAF50;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:bold;">🚀 打开 SOP 流程页</button>';
                html +=   '</div>';
            }
            html +=   '<div style="display:flex;gap:10px;justify-content:flex-end;flex-wrap:wrap;">';
            if (!ev.readonly) {
                html +=     '<button id="dlg-detail-mark" style="padding:8px 16px;background:transparent;color:#e94560;border:1px solid #e94560;border-radius:8px;cursor:pointer;font-size:13px;">' + (isDone ? "标记未完成" : "标记完成") + '</button>';
                html +=     '<button id="dlg-detail-edit" style="padding:8px 16px;background:transparent;color:#2196F3;border:1px solid #2196F3;border-radius:8px;cursor:pointer;font-size:13px;">编辑</button>';
                html +=     '<button id="dlg-detail-lock" style="padding:8px 16px;background:transparent;color:#FF9800;border:1px solid #FF9800;border-radius:8px;cursor:pointer;font-size:13px;">' + (ev.locked ? "🔓 解锁" : "🔒 锁定") + '</button>';
                html +=     '<button id="dlg-detail-delete" style="padding:8px 16px;background:transparent;color:#F44336;border:1px solid #F44336;border-radius:8px;cursor:pointer;font-size:13px;">删除</button>';
            } else {
                var roMsg = ev.recurring ? "重复事件（请在设置中管理）" : "只读事件（节假日/节气）";
                html +=     '<span style="font-size:12px;color:#666;padding:8px 16px;">' + roMsg + '</span>';
            }
            html +=     '<button id="dlg-detail-close" style="padding:8px 16px;background:#0f3460;color:#eee;border:1px solid #0f3460;border-radius:8px;cursor:pointer;font-size:13px;">关闭</button>';
            html +=   '</div>';
            html += '</div>';

            overlay.innerHTML = html;
            document.body.appendChild(overlay);

            overlay.addEventListener("click", function(e) {
                if (e.target === overlay) overlay.remove();
            });
            document.getElementById("dlg-detail-close").addEventListener("click", function() {
                overlay.remove();
            });
            // Only bind mark/edit/delete for non-readonly events
            if (!ev.readonly) {
                document.getElementById("dlg-detail-mark").addEventListener("click", function() {
                    var newStatus = isDone ? "pending" : "done";
                    fetch("/api/events/status", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({id: ev.id, day: ev.start.slice(0,10), status: newStatus})
                    }).then(function(r) { return r.json(); }).then(function(data) {
                        if (data.ok) { overlay.remove(); loadEvents(); }
                    });
                });
                document.getElementById("dlg-detail-edit").addEventListener("click", function() {
                    overlay.remove();
                    showEditDialog(ev);
                });
                document.getElementById("dlg-detail-lock").addEventListener("click", function() {
                    var newLocked = !ev.locked;
                    fetch("/api/events/lock", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({id: ev.id, day: ev.start.slice(0,10), locked: newLocked})
                    }).then(function(r) { return r.json(); }).then(function(data) {
                        if (data.ok) {
                            overlay.remove();
                            loadEvents();
                            alert(newLocked ? "✅ 事件已锁定" : "✅ 事件已解锁");
                        } else {
                            alert("操作失败：" + (data.error || "未知错误"));
                        }
                    });
                });
                document.getElementById("dlg-detail-delete").addEventListener("click", function() {
                    if (!confirm("确定删除此事件？")) return;
                    fetch("/api/events/delete", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({id: ev.id, day: ev.start.slice(0,10)})
                    }).then(function(r) { return r.json(); }).then(function(data) {
                        if (data.ok) { overlay.remove(); loadEvents(); }
                    });
                });
            }
        }

        // ---- Right-click context menu ----
        // ---- Helper: escape HTML ----
        function escapeHtml(text) {
            var div = document.createElement("div");
            div.appendChild(document.createTextNode(text));
            return div.innerHTML;
        }

        // ---- Settings dialog ----
        window.showSettings = function() {
            var existing = document.getElementById('dlg-overlay-settings');
            if (existing) existing.remove();

            var settings = localStorage.getItem('rubedo-overlays');
            if (!settings) settings = '{"solar":true,"fest":true,"holiday":true,"sem":true}';
            try { settings = JSON.parse(settings); } catch(e) { settings = {"solar":true,"fest":true,"holiday":true,"sem":true}; }

            var overlay = document.createElement('div');
            overlay.id = 'dlg-overlay-settings';
            overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.55);display:flex;align-items:center;justify-content:center;z-index:1000;';

            var html = '';
            html += '<div style="background:#16213e;color:#eee;padding:28px;border-radius:14px;min-width:400px;max-width:520px;max-height:85vh;overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,0.5);font-family:Microsoft YaHei,PingFang SC,sans-serif;">';
            html +=   '<div style="font-size:18px;font-weight:bold;color:#e94560;margin-bottom:18px;">设置</div>';

            // Overlay toggles
            html +=   '<div style="margin-bottom:14px;">';
            html +=     '<label style="display:flex;align-items:center;gap:10px;cursor:pointer;padding:8px 0;">';
            html +=       '<input type="checkbox" id="settings-solar" ' + (settings.solar ? "checked" : "") + ' style="width:18px;height:18px;">';
            html +=       '<span style="font-size:14px;">🌿 显示节气</span>';
            html +=     '</label>';
            html +=   '</div>';

            html +=   '<div style="margin-bottom:14px;">';
            html +=     '<label style="display:flex;align-items:center;gap:10px;cursor:pointer;padding:8px 0;">';
            html +=       '<input type="checkbox" id="settings-fest" ' + (settings.fest ? "checked" : "") + ' style="width:18px;height:18px;">';
            html +=       '<span style="font-size:14px;">🛒 显示购物节</span>';
            html +=     '</label>';
            html +=   '</div>';

            html +=   '<div style="margin-bottom:14px;">';
            html +=     '<label style="display:flex;align-items:center;gap:10px;cursor:pointer;padding:8px 0;">';
            html +=       '<input type="checkbox" id="settings-holiday" ' + (settings.holiday ? "checked" : "") + ' style="width:18px;height:18px;">';
            html +=       '<span style="font-size:14px;">🎌 显示法定节假日</span>';
            html +=     '</label>';
            html +=   '</div>';

            html +=   '<div style="margin-bottom:18px;">';
            html +=     '<label style="display:flex;align-items:center;gap:10px;cursor:pointer;padding:8px 0;">';
            html +=       '<input type="checkbox" id="settings-sem" ' + (settings.sem ? "checked" : "") + ' style="width:18px;height:18px;">';
            html +=       '<span style="font-size:14px;">📚 显示学期</span>';
            html +=     '</label>';
            html +=   '</div>';

            // Divider
            html +=   '<hr style="border:none;border-top:1px solid #0f3460;margin:18px 0;">';

            // Custom holidays section
            html +=   '<div style="font-size:15px;font-weight:bold;color:#e94560;margin-bottom:12px;">⭐ 自定义节假日</div>';
            html +=   '<div id="custom-holiday-list" style="margin-bottom:14px;max-height:180px;overflow-y:auto;">加载中...</div>';
            html +=   '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">';
            html +=     '<input id="custom-h-name" type="text" placeholder="名称" style="flex:1;min-width:100px;padding:8px 10px;border:1px solid #0f3460;background:#1a1a2e;color:#eee;border-radius:8px;font-size:13px;box-sizing:border-box;">';
            html +=     '<input id="custom-h-date" type="date" style="padding:8px 10px;border:1px solid #0f3460;background:#1a1a2e;color:#eee;border-radius:8px;font-size:13px;">';
            html +=     '<button id="custom-h-add" style="padding:8px 16px;background:#e94560;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:13px;white-space:nowrap;">添加</button>';
            html +=   '</div>';

            // Divider
            html +=   '<hr style="border:none;border-top:1px solid #0f3460;margin:18px 0;">';

            // Schedules (repeat events) management
            html +=   '<div style="font-size:15px;font-weight:bold;color:#e94560;margin-bottom:12px;">🔄 重复事件管理</div>';
            html +=   '<div id="schedules-list" style="margin-bottom:14px;max-height:220px;overflow-y:auto;">加载中...</div>';

            // Divider
            html +=   '<hr style="border:none;border-top:1px solid #0f3460;margin:18px 0;">';

            // All events management
            html +=   '<div style="font-size:15px;font-weight:bold;color:#e94560;margin-bottom:12px;">📅 一次性事件</div>';
            html +=   '<div style="display:flex;gap:8px;margin-bottom:12px;">';
            html +=     '<input id="event-mgr-search" type="text" placeholder="搜索标题..." style="flex:1;padding:7px 10px;border:1px solid #0f3460;background:#1a1a2e;color:#eee;border-radius:8px;font-size:13px;box-sizing:border-box;">';
            html +=     '<select id="event-mgr-filter" style="padding:7px 10px;border:1px solid #0f3460;background:#1a1a2e;color:#eee;border-radius:8px;font-size:13px;">';
            html +=       '<option value="">全部</option>';
            html +=       '<option value="reminder">提醒</option>';
            html +=       '<option value="sop">酷家乐SOP</option>';
            html +=       '<option value="tool">工具</option>';
            html +=       '<option value="external">外部事件</option>';
            html +=     '</select>';
            html +=   '</div>';
            html +=   '<div id="event-mgr-list" style="max-height:250px;overflow-y:auto;margin-bottom:14px;">加载中...</div>';

            // Bottom buttons
            html +=   '<div style="display:flex;gap:10px;justify-content:flex-end;margin-top:22px;">';
            html +=     '<button id="settings-cancel" style="padding:8px 20px;background:transparent;color:#aaa;border:1px solid #444;border-radius:8px;cursor:pointer;font-size:14px;">取消</button>';
            html +=     '<button id="settings-save" style="padding:8px 20px;background:#e94560;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:bold;">保存</button>';
            html +=   '</div>';
            html += '</div>';

            overlay.innerHTML = html;
            document.body.appendChild(overlay);

            // Load custom holidays
            fetch('/api/custom-holidays')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    var list = document.getElementById('custom-holiday-list');
                    if (!data.ok || !data.holidays || data.holidays.length === 0) {
                        list.innerHTML = '<div style="font-size:13px;color:#666;">暂无自定义节假日</div>';
                        return;
                    }
                    var items = '';
                    data.holidays.forEach(function(h) {
                        items += '<div style="display:flex;align-items:center;gap:8px;padding:6px 0;font-size:13px;border-bottom:1px solid #0f3460;">';
                        items +=   '<span style="flex:1;">⭐ ' + escapeHtml(h.name) + ' — ' + h.date + '</span>';
                        items +=   '<button data-name="' + escapeHtml(h.name) + '" data-date="' + h.date + '" class="custom-h-del" style="padding:3px 10px;background:#f44336;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12px;">删除</button>';
                        items += '</div>';
                    });
                    list.innerHTML = items;
                    // Bind delete buttons
                    list.querySelectorAll('.custom-h-del').forEach(function(btn) {
                        btn.addEventListener('click', function() {
                            var name = this.getAttribute('data-name');
                            var dt = this.getAttribute('data-date');
                            fetch('/api/custom-holidays', { method: 'DELETE', headers: {'Content-Type':'application/json'}, body: JSON.stringify({name:name, date:dt}) })
                                .then(function() { window.showSettings(); });
                        });
                    });
                })
                .catch(function() {
                    document.getElementById('custom-holiday-list').innerHTML = '<div style="font-size:13px;color:#f44336;">加载失败</div>';
                });

            // Load schedules (repeat events)
            fetch('/api/schedules')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    var list = document.getElementById('schedules-list');
                    if (!data.ok || !data.schedules || data.schedules.length === 0) {
                        list.innerHTML = '<div style="font-size:13px;color:#666;">暂无重复事件</div>';
                        return;
                    }
                    var items = '';
                    data.schedules.forEach(function(sch) {
                        var statusColor = sch.enabled ? '#4CAF50' : '#f44336';
                        var statusText = sch.enabled ? '启用' : '禁用';
                        items += '<div style="display:flex;align-items:center;gap:8px;padding:8px 0;font-size:13px;border-bottom:1px solid #0f3460;">';
                        items +=   '<div style="flex:1;overflow:hidden;">';
                        items +=     '<div style="font-weight:bold;color:' + statusColor + ';">' + escapeHtml(sch.title) + '</div>';
                        items +=     '<div style="font-size:11px;color:#aaa;">';
                        if (sch.repeat_mode === 'preheat') {
                            items += (sch.target_name || sch.target_date || '') + ' 前' + sch.preheat_days + '天';
                            if (sch.scope === 'once') items += ' (仅今年)';
                        } else if (sch.repeat_mode === 'daily') {
                            items += '每天重复';
                        } else if (sch.repeat_mode === 'weekly') {
                            items += '每周重复';
                        } else if (sch.repeat_mode === 'monthly') {
                            items += '每月重复';
                        } else if (sch.repeat_mode === 'yearly') {
                            items += '每年重复';
                        } else {
                            items += (sch.repeat_mode || '重复');
                        }
                        items +=     '</div>';
                        items +=   '</div>';
                        items +=   '<button data-id="' + sch.id + '" data-enabled="' + (sch.enabled ? 'true' : 'false') + '" class="sch-toggle" style="padding:3px 10px;background:' + statusColor + ';color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12px;">' + statusText + '</button>';
                        items +=   '<button data-id="' + sch.id + '" class="sch-del" style="padding:3px 10px;background:#f44336;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12px;">删除</button>';
                        items += '</div>';
                    });
                    list.innerHTML = items;
                    // Bind toggle buttons
                    list.querySelectorAll('.sch-toggle').forEach(function(btn) {
                        btn.addEventListener('click', function() {
                            var id = this.getAttribute('data-id');
                            var enabled = this.getAttribute('data-enabled') !== 'true';
                            fetch('/api/schedules/' + id, {
                                method: 'PUT',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({enabled: enabled})
                            }).then(function() { window.showSettings(); });
                        });
                    });
                    // Bind delete buttons
                    list.querySelectorAll('.sch-del').forEach(function(btn) {
                        btn.addEventListener('click', function() {
                            var id = this.getAttribute('data-id');
                            if (!confirm('确定删除此重复事件？')) return;
                            fetch('/api/schedules/' + id, { method: 'DELETE' })
                                .then(function() { window.showSettings(); });
                        });
                    });
                })
                .catch(function() {
                    document.getElementById('schedules-list').innerHTML = '<div style="font-size:13px;color:#f44336;">加载失败</div>';
                });

            // Load all events for management
            function loadEventManagement() {
                var search = document.getElementById('event-mgr-search').value.toLowerCase();
                var filter = document.getElementById('event-mgr-filter').value;
                // Load current week's events
                var s = currentStart.format("YYYY-MM-DD");
                var e = currentStart.add(6, "day").format("YYYY-MM-DD");
                fetch("/api/events?start=" + s + "&end=" + e)
                    .then(function(r) { return r.json(); })
                    .then(function(events) {
                        var list = document.getElementById('event-mgr-list');
                        // 排除重复事件（它们由"重复事件管理"单独管理）
                        events = (events || []).filter(function(ev) { return !ev.recurring; });
                        if (events.length === 0) {
                            list.innerHTML = '<div style="font-size:13px;color:#666;">本周暂无事件</div>';
                            return;
                        }
                        var filtered = events;
                        if (search) {
                            filtered = filtered.filter(function(ev) {
                                return (ev.text || '').toLowerCase().indexOf(search) >= 0;
                            });
                        }
                        if (filter) {
                            filtered = filtered.filter(function(ev) { return ev.kind === filter; });
                        }
                        if (filtered.length === 0) {
                            list.innerHTML = '<div style="font-size:13px;color:#666;">无匹配事件</div>';
                            return;
                        }
                        var items = '';
                        filtered.forEach(function(ev) {
                            var kindLabel = {"sop":"SOP","tool":"工具","reminder":"提醒","external":"外部","marker":"标记"}[ev.kind] || ev.kind;
                            items += '<div style="display:flex;align-items:center;gap:8px;padding:6px 0;font-size:13px;border-bottom:1px solid #0f3460;">';
                            items +=   '<div style="flex:1;overflow:hidden;">';
                            items +=     '<div>' + escapeHtml(ev.text) + ' <span style="font-size:11px;color:#aaa;">[' + kindLabel + ']</span></div>';
                            items +=     '<div style="font-size:11px;color:#666;">' + (ev.start || '').slice(0,16).replace('T',' ') + '</div>';
                            items +=   '</div>';
                            items +=   '<button data-id="' + ev.id + '" data-day="' + (ev.start||'').slice(0,10) + '" class="ev-mgr-del" style="padding:3px 10px;background:#f44336;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12px;">删除</button>';
                            items += '</div>';
                        });
                        list.innerHTML = items;
                        list.querySelectorAll('.ev-mgr-del').forEach(function(btn) {
                            btn.addEventListener('click', function() {
                                var id = this.getAttribute('data-id');
                                var day = this.getAttribute('data-day');
                                if (!confirm('确定删除此事件？')) return;
                                fetch('/api/events/delete', {
                                    method: 'POST',
                                    headers: {'Content-Type':'application/json'},
                                    body: JSON.stringify({id:id, day:day})
                                }).then(function(r) { return r.json(); }).then(function(data) {
                                    if (data.ok) loadEventManagement();
                                });
                            });
                        });
                    })
                    .catch(function() {
                        document.getElementById('event-mgr-list').innerHTML = '<div style="font-size:13px;color:#f44336;">加载失败</div>';
                    });
            }
            loadEventManagement();
            document.getElementById('event-mgr-search').addEventListener('input', function() { loadEventManagement(); });
            document.getElementById('event-mgr-filter').addEventListener('change', function() { loadEventManagement(); });

            // Add custom holiday
            document.getElementById('custom-h-add').addEventListener('click', function() {
                var name = document.getElementById('custom-h-name').value.trim();
                var dt = document.getElementById('custom-h-date').value;
                if (!name || !dt) { alert('请填写名称和日期'); return; }
                fetch('/api/custom-holidays', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({name:name, date:dt}) })
                    .then(function(r) { return r.json(); })
                    .then(function(data) {
                        if (data.ok) {
                            document.getElementById('custom-h-name').value = '';
                            document.getElementById('custom-h-date').value = '';
                            window.showSettings(); // refresh list
                        } else {
                            alert('添加失败：' + (data.error || '未知错误'));
                        }
                    });
            });

            overlay.addEventListener('click', function(e) {
                if (e.target === overlay) overlay.remove();
            });
            document.getElementById('settings-cancel').addEventListener('click', function() {
                overlay.remove();
            });
            document.getElementById('settings-save').addEventListener('click', function() {
                var newSettings = {
                    solar:   document.getElementById('settings-solar').checked,
                    fest:    document.getElementById('settings-fest').checked,
                    holiday: document.getElementById('settings-holiday').checked,
                    sem:     document.getElementById('settings-sem').checked,
                };
                localStorage.setItem('rubedo-overlays', JSON.stringify(newSettings));
                overlay.remove();
                loadEvents();
            });
        };

        // ---- 编辑重复事件模板 ----
        function showScheduleEditDialog(schedule) {
            var existing = document.getElementById("dlg-overlay-sched-edit");
            if (existing) existing.remove();

            var overlay = document.createElement("div");
            overlay.id = "dlg-overlay-sched-edit";
            overlay.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.55);display:flex;align-items:center;justify-content:center;z-index:1000;";

            var html = '';
            html += '<div style="background:#16213e;color:#eee;padding:28px;border-radius:14px;min-width:340px;max-width:420px;box-shadow:0 8px 32px rgba(0,0,0,0.5);font-family:Microsoft YaHei,PingFang SC,sans-serif;">';
            html +=   '<div style="font-size:18px;font-weight:bold;color:#e94560;margin-bottom:18px;">编辑重复事件</div>';
            html +=   '<div style="margin-bottom:14px;">';
            html +=     '<div style="font-size:13px;color:#aaa;margin-bottom:5px;">标题</div>';
            html +=     '<input id="sched-edit-title" type="text" value="' + escapeHtml(schedule.title || '') + '" style="width:100%;padding:9px 12px;border:1px solid #0f3460;background:#1a1a2e;color:#eee;border-radius:8px;font-size:14px;box-sizing:border-box;">';
            html +=   '</div>';
            html +=   '<div style="margin-bottom:18px;">';
            html +=     '<div style="font-size:13px;color:#aaa;margin-bottom:5px;">分类</div>';
            html +=     '<select id="sched-edit-kind" style="width:100%;padding:9px 12px;border:1px solid #0f3460;background:#1a1a2e;color:#eee;border-radius:8px;font-size:14px;">';
            html +=       '<option value="reminder"' + (schedule.kind === "reminder" ? " selected" : "") + '>提醒</option>';
            html +=       '<option value="sop"' + (schedule.kind === "sop" ? " selected" : "") + '>酷家乐SOP</option>';
            html +=       '<option value="tool"' + (schedule.kind === "tool" ? " selected" : "") + '>工具</option>';
            html +=       '<option value="external"' + (schedule.kind === "external" ? " selected" : "") + '>外部事件</option>';
            html +=     '</select>';
            html +=   '</div>';
            html +=   '<div style="margin-bottom:18px;">';
            html +=     '<div style="font-size:13px;color:#aaa;margin-bottom:5px;">备注</div>';
            html +=     '<textarea id="sched-edit-desc" style="width:100%;height:60px;padding:9px 12px;border:1px solid #0f3460;background:#1a1a2e;color:#eee;border-radius:8px;font-size:14px;box-sizing:border-box;resize:vertical;" placeholder="可选">' + escapeHtml(schedule.description || '') + '</textarea>';
            html +=   '</div>';
            html +=   '<div style="display:flex;gap:10px;justify-content:flex-end;">';
            html +=     '<button id="sched-edit-cancel" style="padding:8px 20px;background:transparent;color:#aaa;border:1px solid #444;border-radius:8px;cursor:pointer;font-size:14px;">取消</button>';
            html +=     '<button id="sched-edit-ok" style="padding:8px 20px;background:#e94560;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:bold;">保存</button>';
            html +=   '</div>';
            html += '</div>';

            overlay.innerHTML = html;
            document.body.appendChild(overlay);

            overlay.addEventListener("click", function(e) {
                if (e.target === overlay) overlay.remove();
            });
            document.getElementById("sched-edit-cancel").addEventListener("click", function() {
                overlay.remove();
            });
            document.getElementById("sched-edit-ok").addEventListener("click", function() {
                var newTitle = document.getElementById("sched-edit-title").value.trim();
                var newKind = document.getElementById("sched-edit-kind").value;
                var newDesc = document.getElementById("sched-edit-desc").value.trim();
                if (!newTitle) { alert("请输入标题"); return; }
                fetch("/api/schedules/" + schedule.id, {
                    method: "PUT",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({title: newTitle, kind: newKind, description: newDesc})
                }).then(function(r) { return r.json(); }).then(function(data) {
                    if (data.ok) { overlay.remove(); loadEvents(); }
                    else { alert("保存失败：" + (data.error || "未知错误")); }
                });
            });
        }

        // 先暴露到全局（在 init() 之前），确保诊断工具一定能读到
        window.dp = dp;

        dp.init();

        // 底部面板填满空白——不改 DayPilot，只调整底部面板高度
        function fillBlank() {
            var cal = document.getElementById('calendar');
            var panel = document.getElementById('detail-panel');
            if (!cal || !panel) return;
            
            // DayPilot 渲染的实际高度（读取 DOM，不修改 DayPilot）
            var dpEl = cal.firstElementChild;
            var dpH = dpEl ? dpEl.offsetHeight : 0;
            if (dpH < 50) return; // DayPilot 还没渲染好
            
            var calH = cal.offsetHeight;
            var blank = calH - dpH;
            
            if (blank > 5) {
                // 底部面板向上延伸，盖住日历内部的空白
                panel.style.height = (280 + blank) + 'px';
                console.log('[FillBlank] 空白:', blank, 'px, 底部面板:', (280 + blank), 'px');
            } else {
                panel.style.height = '280px';
            }
        }
        setTimeout(fillBlank, 500);
        setTimeout(fillBlank, 1500); // 二次确认 DayPilot 渲染完毕
        window.addEventListener('resize', function() { setTimeout(fillBlank, 200); });

        loadEvents();
        updateWeekRange();
    });
    
    // ---- 日历布局诊断工具 ----
    window.showDiagnostics = function() {
        var cal = document.getElementById('calendar');
        var dp = window.dp;
        if (!cal || !dp) { alert('日历未初始化'); return; }

        var cellH     = dp.config.cellHeight || 30;
        var headerH   = dp.config.headerHeight || 40;
        var gridH     = cellH * 48 + headerH;
        var containerH = cal.offsetHeight;
        var gap       = containerH - gridH;

        var mainH  = document.querySelector('.main-layout')?.offsetHeight || 0;
        var panelH = document.getElementById('detail-panel')?.offsetHeight || 0;
        var vh      = window.innerHeight;

        var rows = [
            ['视口高度 (window.innerHeight)', vh + 'px'],
            ['main-layout 高度', mainH + 'px'],
            ['#calendar 容器高度', containerH + 'px'],
            ['#detail-panel 高度', panelH + 'px'],
            ['DayPilot cellHeight', cellH + 'px'],
            ['DayPilot headerHeight', headerH + 'px'],
            ['网格理论高度 (cellH×48+header)', gridH + 'px'],
            ['底部空白 (容器−网格)', gap + 'px', gap > 10 ? 'bad' : gap < -10 ? 'warn' : 'ok'],
            ['DayPilot config.height', JSON.stringify(dp.config.height)],
            ['DayPilot 实际渲染高度', (cal.querySelector('.daypilot-calendar-inner')?.offsetHeight || '?') + 'px'],
        ];

        var html = '<table><tr><th>项目</th><th>值</th></tr>';
        rows.forEach(function(r) {
            var cls = r[2] || '';
            html += '<tr><td>' + r[0] + '</td><td class="' + cls + '">' + r[1] + '</td></tr>';
        });
        html += '</table>';
        html += '<p style="margin-top:12px;color:#aaa;">💡 如果"底部空白">10px，说明网格高度 < 容器高度，需要增大 cellHeight。</p>';

        document.getElementById('diag-body').innerHTML = html;
        document.getElementById('diag-overlay').classList.add('show');
    };

    // Ctrl+Shift+D 打开诊断（调用内联在 HTML 里的 showDiag）
    document.addEventListener("keydown", function(e) {
        if (e.ctrlKey && e.shiftKey && e.key === "D") {
            e.preventDefault();
            if (window.showDiag) window.showDiag();
        }
        if (e.key === "Escape") {
            var overlay = document.getElementById("diag-overlay");
            if (overlay) overlay.classList.remove("show");
        }
    });
