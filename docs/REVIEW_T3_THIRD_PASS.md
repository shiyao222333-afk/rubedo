# 代码审查报告（第三轮）— T3 重构后代码

> 审查对象：v0.4 T3 重构全部改动（含前两轮修复：`find_event_by_id` 契约、busy_timeout、日志底座接线、死代码清理、KIND_COLORS/EXEC_MODES 导入补全）
> 审查时间：2026-07-07
> 审查者：Code Reviewer Agent

## 总体结论

**重构后代码现在是健康的，没有阻塞使用的致命 bug。**

本轮用「静态分析 + 全 23 个路由函数真实调用（隔离临时库）」双保险兜底，确认了上一轮最后一颗雷（KIND_COLORS 漏导入导致创建事件必崩）已彻底排除，且没有同类「漏导入 / 运行时才炸」的隐藏问题残留。

唯一值得修的是一个**边界场景的静默失败**（拖拽改日期的极端情况），不阻塞日常使用。

---

## 验证方法（通俗说明）

1. **静态分析**：扫描 `api.py` 每个函数，找出「引用了但既没导入、也没定义、也不是内置」的符号。结果：除误报（异常变量 `e`、闭包引用）外，**无真实漏导入**。
2. **全接口真实调用**：把日历后台的 23 个接口挨个真实调一遍（创建/改/删/移动/锁定/状态、节假日、时间表、重复模板、SOP 步骤等），用独立的临时数据库跑、并屏蔽了网络请求（不污染你真实数据）。结果：**0 个崩溃、0 个漏导入**。其中创建事件 `ok:True`、列表能读回刚建的事件，证明读写链路完全通。
3. **前端一致性核对**：创建对话框的「事件类型」选项与后台校验用的类型表完全一致，不会互相拒。

---

## 🟡 建议修：拖拽改日期的边界静默失败

**位置**：`api_move_event`（api.py L255-277）

**问题**：当 `old_id` 在 `old_day` 当天事件里找不到时（例如事件 `day` 字段与 `start` 日期不一致等边界情况），`moved` 为 `None`，但函数仍返回 `{"ok": True, "event": null}`。

**后果**：前端看到 `ok:True` 就以为移动成功，接着发「更新」请求并刷新日历——但事件**实际没被移动**，刷新后它仍停在老位置。表现就是「拖了没反应、也不报错」。

**为什么现在大多没事**：正常拖拽时 `old_day` 由事件自身的 `start` 算出，事件一定在那一天里，能正常找到并移动。只有 `day` 与 `start` 不一致的脏数据才会触发。但既然能静默失败，就应该改对。

**建议修复**：移动失败时返回 `ok:False` 让前端弹错，而不是假装成功：

```python
    moved = None
    for i, ev in enumerate(events):
        if ev["id"] == data["old_id"]:
            moved = events.pop(i)
            break
    if not moved:
        return JSONResponse({"ok": False, "error": f"事件 {data['old_id']} 在 {data['old_day']} 未找到，移动失败"})
    moved["start"] = data["event"]["start"]
    moved["end"]   = data["event"]["end"]
    new_day = date.fromisoformat(moved["start"][:10])
    write_day(old_day, events)
    new_events = read_day(new_day)
    new_events.append(moved)
    write_day(new_day, new_events)
    return JSONResponse({"ok": True, "event": moved})
```

> 注意：`api_move_event` 的 `except` 块目前会吞掉所有异常返回 `ok:False`，所以即便不改，最坏也只是「移动失败弹错」，不会崩。但当前 `moved=None` 分支在 `try` 内、且没返回错误，所以才会静默成功。上面的改动是把它从「静默成功」变成「明确失败」。

---

## 💭 已知限制 / 优化（不阻塞，记在此备查）

1. **重复事件进度写不进（已规避）**：每周自动生成的重复任务是程序临时算出来的，不在数据库里，SOP 步骤保存时查不到它。但前端把这些任务标成灰色只读、不显示「记进度」按钮，所以当前点不到——问题被前端挡住了。等将来想让重复任务也能记进度时再补。
2. **并发覆盖（理论）**：保存机制是「读出来→改一下→整批写回」，同一毫秒两个保存可能后者覆盖前者。单人桌面工具几乎不可能触发。
3. **时间记录写死「今天」**：`store.write_timelog_entry` 用 `date.today()` 归日期，跨午夜（23:30 记一笔到次日 00:30）会计错天。正常用几乎不触发。
4. **`find_event_by_id` 全表扫**：按 id 定位事件时遍历所有有事件的日期。数据量大时会慢，可加 `event_id` 索引优化（纯性能，非 bug）。
5. **`api.py` 三个冗余兼容导入**：`DATA_DIR / SCHEDULES_FILE / OCCURRENCE_OVERRIDES_FILE` 仅出现在导入行、函数体内未使用（历史兼容保留）。可清理，不影响功能。

---

## ✅ 已确认正确（不要回头改）

- **数据层切换**：`utils/api/holidays` 全部数据读写改走 `modules.shared.store`（SQLite DAL），对外接口签名与行为不变，用户无感。
- **数据分裂陷阱已堵死**：原本直读 JSON 的 5 处全部改走 DAL，`pages/` 下零直读。
- **并发保护**：`store._connect()` 已设 `PRAGMA busy_timeout=5000`，并发写不再立即报 `database is locked` 丢数据。
- **日志底座已接线**：`setup_logging` 在 `app.py` 顶层调用，`app_log = get_logger("rubedo.app")` 已定义；`utils/api/holidays/store` 的日志均写 `data/rubedo.log`。
- **前端类型枚举一致**：创建对话框的 kind 选项与 `KIND_COLORS` 完全对应。
- **死代码已清理**：根 `timelog.py`（直读旧 JSON 的地雷）已删除。

---

## 下一步建议

地基已稳。两个方向你拍板：

1. **顺手修 `api_move_event` 的静默 ok:True**（约 5 行改动，零风险），其余已知限制记入文档暂缓。
2. **直接转入 v0.4.x 业务功能** —— 把酷家乐 SOP 里已跑通的环节逐个从「手动」换「自动」（离赚钱最近的一步）。

你说往哪走？
