
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

        const dp = new DayPilot.Calendar("calendar", {
            viewType:      "Week",
            startDate:     currentStart.format("YYYY-MM-DD"),
            weekStarts:    1,
            cellDuration:  30,
            cellHeight:    30,
            dayBeginHour: 0,
            dayEndHour:   24,
            headerHeight: 40,
            locale:        "zh-cn",
            timeRangeSelectedHandling: "JavaScript",

            onTimeRangeSelected: function(args) {
                showCreateDialog(args.start, args.end);
            },

            eventClickHandling: "JavaScript",
            onEventClick: function(args) {
                showEventDetailDialog(normalizeEvent(args.e));
            },

            eventRightClickHandling: "JavaScript",
            onEventRightClick: function(args) {
                showContextMenu(normalizeEvent(args.e), args.x, args.y);
            },

            eventDeleteHandling: "Disabled",

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
                recurring:   d.recurring    || false
            };
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
                        exec_mode: "manual"
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
                                window.open("/sop/kujiale", "_blank");
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

            html +=   '<div style="display:flex;gap:10px;justify-content:flex-end;">';
            html +=     '<button id="dlg-edit-cancel" style="padding:8px 20px;background:transparent;color:#aaa;border:1px solid #444;border-radius:8px;cursor:pointer;font-size:14px;">取消</button>';
            html +=     '<button id="dlg-edit-ok" style="padding:8px 20px;background:#2196F3;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:bold;">保存</button>';
            html +=   '</div>';
            html += '</div>';

            overlay.innerHTML = html;
            document.body.appendChild(overlay);
            setTimeout(function() {
                var input = document.getElementById("dlg-edit-title");
                if (input) input.focus();
            }, 80);

            overlay.addEventListener("click", function(e) {
                if (e.target === overlay) overlay.remove();
            });
            document.getElementById("dlg-edit-cancel").addEventListener("click", function() {
                overlay.remove();
            });
            document.getElementById("dlg-edit-ok").addEventListener("click", function() {
                var titleInput = document.getElementById("dlg-edit-title");
                var kindSelect = document.getElementById("dlg-edit-kind");
                var descInput  = document.getElementById("dlg-edit-desc");
                var reminderSelect = document.getElementById("dlg-edit-reminder");
                var newTitle = titleInput.value.trim();
                var newKind  = kindSelect.value;
                var newDesc  = descInput.value.trim();
                var newReminder = reminderSelect.value;
                if (!newTitle) { alert("请输入标题"); return; }
                fetch("/api/events/update", {
                    method: "PUT",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({id: ev.id, day: ev.start.slice(0,10), text: withIcon(stripIcon(newTitle), newKind), kind: newKind, description: newDesc, reminder: newReminder})
                }).then(function(r) { return r.json(); }).then(function(data) {
                    if (data.ok) { overlay.remove(); loadEvents(); }
                    else alert("修改失败：" + (data.error || "未知错误"));
                });
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
                html +=   '<div style="margin-bottom:14px;">';
                html +=     '<button onclick="window.open(\'/sop/kujiale\', \'_blank\');" style="width:100%;padding:10px;background:#4CAF50;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:bold;">🚀 打开 SOP 流程页</button>';
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

        dp.init();
        loadEvents();
        updateWeekRange();
    });
    