
    document.addEventListener("DOMContentLoaded", function() {
        let currentView  = "Week";
        let currentStart = dayjs().startOf("week");

        const dp = new DayPilot.Calendar("calendar", {
            viewType:      "Week",
            cellDuration:  30,
            cellHeight:    30,
            dayBeginHour: 0,
            dayEndHour:   24,
            locale:        "zh-cn",
            timeRangeSelectedHandling: "JavaScript",

            onTimeRangeSelected: function(args) {
                showCreateDialog(args.start, args.end);
            },

            eventClickHandling: "JavaScript",
            onEventClick: function(args) {
                showEventDetailDialog(args.e);
            },

            eventRightClickHandling: "JavaScript",
            onEventRightClick: function(args) {
                showContextMenu(args.e, args.x, args.y);
            },

            eventDeleteHandling: "Disabled",
        });

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
            currentStart = currentStart.add(delta, "week");
            dp.startDate = currentStart.format("YYYY-MM-DD");
            loadEvents();
            updateWeekRange();
        };
        window.navToday  = function() {
            currentStart = dayjs().startOf("week");
            dp.startDate = currentStart.format("YYYY-MM-DD");
            loadEvents();
            updateWeekRange();
        };
        window.switchView = function() {
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

        // ---- Load events from API ----
        function loadEvents() {
            const s = dp.visibleStart().toString("YYYY-MM-DD");
            const e = dp.visibleEnd().toString("YYYY-MM-DD");
            fetch("/api/events?start=" + s + "&end=" + e)
                .then(r => r.json())
                .then(events => {
                    dp.events.list = events;
                    dp.update();
                    const userEvents = events.filter(function(ev) {
                        return ev.kind !== "marker" || (ev.id && ev.id.startsWith("marker-user-"));
                    });
                    var guide = document.getElementById("empty-guide");
                    if (guide) guide.style.display = userEvents.length === 0 ? "block" : "none";
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
            document.getElementById("dlg-create-ok").addEventListener("click", function() {
                var titleInput = document.getElementById("dlg-create-title");
                var kindSelect = document.getElementById("dlg-create-kind");
                var title = titleInput.value.trim();
                var kind  = kindSelect.value;
                if (!title) { alert("请输入标题"); return; }
                fetch("/api/events/create", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({
                        text: title,
                        start: start.toString("YYYY-MM-DDTHH:mm:ss"),
                        end:   end.toString("YYYY-MM-DDTHH:mm:ss"),
                        kind: kind,
                        exec_mode: "manual"
                    })
                }).then(function(r) { return r.json(); }).then(function(data) {
                    if (data.ok) { overlay.remove(); loadEvents(); }
                    else alert("创建失败：" + (data.error || "未知错误"));
                });
            });
        }

        // ---- Event detail dialog ----
        function showEventDetailDialog(ev) {
            var existing = document.getElementById("dlg-overlay-detail");
            if (existing) existing.remove();

            var KCOL  = {"sop":"#4CAF50","tool":"#2196F3","reminder":"#9E9E9E","external":"#FF9800","marker":"#F44336"};
            var KNAME = {"sop":"酷家乐SOP","tool":"工具","reminder":"提醒","external":"外部事件","marker":"标记日"};
            var col     = KCOL[ev.kind] || "#9E9E9E";
            var kname   = KNAME[ev.kind] || ev.kind;
            var isDone  = ev.status === "done";
            var statusStr = isDone ? "\u2705 已完成" : (ev.status === "skipped" ? "\u23F3 已跳过" : "\u23F3 待完成");

            var overlay = document.createElement("div");
            overlay.id = "dlg-overlay-detail";
            overlay.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.55);display:flex;align-items:center;justify-content:center;z-index:1000;";

            var html = '';
            html += '<div style="background:#16213e;color:#eee;padding:28px;border-radius:14px;min-width:340px;max-width:420px;box-shadow:0 8px 32px rgba(0,0,0,0.5);font-family:Microsoft YaHei,PingFang SC,sans-serif;">';
            html +=   '<div style="font-size:17px;font-weight:bold;color:' + col + ';margin-bottom:6px;">' + escapeHtml(ev.text) + '</div>';
            html +=   '<div style="font-size:13px;color:#aaa;margin-bottom:4px;">' + dayjs(ev.start).format("YYYY-MM-DD HH:mm") + ' - ' + dayjs(ev.end).format("HH:mm") + '</div>';
            html +=   '<div style="font-size:13px;color:#aaa;margin-bottom:4px;">分类：' + kname + '</div>';
            html +=   '<div style="font-size:13px;color:#aaa;margin-bottom:18px;">状态：' + statusStr + '</div>';
            html +=   '<div style="display:flex;gap:10px;justify-content:flex-end;flex-wrap:wrap;">';
            html +=     '<button id="dlg-detail-mark" style="padding:8px 16px;background:transparent;color:#e94560;border:1px solid #e94560;border-radius:8px;cursor:pointer;font-size:13px;">' + (isDone ? "标记未完成" : "标记完成") + '</button>';
            html +=     '<button id="dlg-detail-edit" style="padding:8px 16px;background:transparent;color:#2196F3;border:1px solid #2196F3;border-radius:8px;cursor:pointer;font-size:13px;">编辑</button>';
            html +=     '<button id="dlg-detail-delete" style="padding:8px 16px;background:transparent;color:#F44336;border:1px solid #F44336;border-radius:8px;cursor:pointer;font-size:13px;">删除</button>';
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
                var newText = prompt("修改标题：", ev.text);
                if (newText === null) return;
                var newKind = prompt("修改分类 (sop/tool/reminder/external/marker)：", ev.kind);
                if (newKind === null) return;
                fetch("/api/events/update", {
                    method: "PUT",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({id: ev.id, day: ev.start.slice(0,10), text: newText, kind: newKind})
                }).then(function(r) { return r.json(); }).then(function(data) {
                    if (data.ok) { overlay.remove(); loadEvents(); }
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

        // ---- Right-click context menu ----
        function showContextMenu(ev, x, y) {
            var old = document.getElementById("ctx-menu");
            if (old) old.remove();

            var menu = document.createElement("div");
            menu.id = "ctx-menu";
            menu.style.cssText = "position:fixed;top:" + y + "px;left:" + x + "px;background:#1a1a2e;color:#eee;border:1px solid #0f3460;border-radius:10px;padding:6px 0;z-index:1001;min-width:150px;box-shadow:0 8px 24px rgba(0,0,0,0.5);font-size:13px;font-family:Microsoft YaHei,PingFang SC,sans-serif;";

            function addItem(label, fn) {
                var item = document.createElement("div");
                item.innerText = label;
                item.style.cssText = "padding:9px 20px;cursor:pointer;color:#eee;transition:background 0.15s;";
                item.addEventListener("mouseenter", function() { item.style.background = "#0f3460"; });
                item.addEventListener("mouseleave", function() { item.style.background = "transparent"; });
                item.addEventListener("click", function() { menu.remove(); fn(); });
                menu.appendChild(item);
            }

            if (ev.status !== "done") {
                addItem("\u2705 标记完成", function() {
                    fetch("/api/events/status", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({id: ev.id, day: ev.start.slice(0,10), status: "done"})
                    }).then(function(r) { return r.json(); }).then(function(data) {
                        if (data.ok) loadEvents();
                    });
                });
            } else {
                addItem("\u23F3 标记未完成", function() {
                    fetch("/api/events/status", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({id: ev.id, day: ev.start.slice(0,10), status: "pending"})
                    }).then(function(r) { return r.json(); }).then(function(data) {
                        if (data.ok) loadEvents();
                    });
                });
            }
            addItem("\u270F\uFE0F 编辑",   function() { showEventDetailDialog(ev); });
            addItem("\uD83D\uDDE1\uFE0F 删除",   function() {
                if (!confirm("确定删除此事件？")) return;
                fetch("/api/events/delete", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({id: ev.id, day: ev.start.slice(0,10)})
                }).then(function(r) { return r.json(); }).then(function(data) {
                    if (data.ok) loadEvents();
                });
            });

            document.body.appendChild(menu);
            setTimeout(function() {
                function closeFn(e) {
                    if (!menu.contains(e.target)) {
                        menu.remove();
                        document.removeEventListener("click", closeFn);
                    }
                }
                document.addEventListener("click", closeFn);
            }, 0);
        }

        // ---- Helper: escape HTML ----
        function escapeHtml(text) {
            var div = document.createElement("div");
            div.appendChild(document.createTextNode(text));
            return div.innerHTML;
        }

        dp.init();
        loadEvents();
        updateWeekRange();
    });
    