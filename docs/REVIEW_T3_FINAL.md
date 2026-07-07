# v0.4 地基 · 最终封顶审查（REVIEW_T3_FINAL）

> 审查对象：T3（JSON→SQLite 迁移）完成 + 四轮 bug 修复 + SOP 详情修复之后的完整地基代码
> 审查范围：`modules/shared/store.py`、`api.py`、`utils.py`、`app.py`、`holidays.py`、`pages/index_page.py`、`static/init.js`
> 审查视角：Code Review Expert（火眼眼）—— 正确性 / 安全性 / 可维护性 / 性能 / 测试
> 日期：2026-07-07

---

## 一、总体印象

地基现在是**稳的**。经过 T3 迁移和多轮修复，数据层职责清晰、路由输入校验到位、最致命的"静默失败"一类 bug 已被系统性堵住（前端错误横幅 + 自动上报 + `api_list_events` 坏数据过滤 + `expand_recurring_schedules` 单模板容错）。本轮再发现并修复了一处真实的契约 bug（kind 枚举创建/更新不一致）。

**结论：地基已可放心往上盖业务功能。** 本报告列出的剩余项多为一致性 / 文档 / 健壮性建议，无未解决的阻断级问题。

---

## 二、亮点（值得保持）

- **`store.py` 是干净的 DAL**：上下文管理器自动 commit/rollback、`busy_timeout=5000` 防并发写锁死、`ALTER TABLE` 移出事务、加 `event_id` 列+索引实现 O(1) 按 id 定位。依赖方向正确（shared 不反向 import 上层）。
- **`api_list_events` 坏数据过滤**：缺 `start`/`id` 的坏事件被跳过并告警，直接关掉"一条脏数据拖垮整本日历"的爆炸半径（这正是用户此前"创建没反应"的真凶）。
- **`expand_recurring_schedules` 单模板 try/except**：一条配置错的重复模板只跳过并记日志，不再让整页空白。
- **输入校验扎实**：`api_create_event` / `api_update_event` / `api_write_timelog` / `api_add_custom_holiday` 都对必需字段、枚举、时间格式、非负值做了校验。
- **前端错误可见化**：全局 `error`/`unhandledrejection` 监听 + `loadEvents` 失败横幅 + 红字自动上报后端日志。把"非程序员无法排查"的死局变成"红字自动飞给 AI"。
- **`find_event_by_id` 返回 `(day, events)`** 与 `save_event_day(day, events)` 契约一致——修掉了最早那轮 P0 的"返回单事件 vs 调用方按列表遍历"陷阱。

---

## 三、问题清单

### 🟡 建议修复（Should Fix）

**1. `api_list_events` 吞异常返回 `[]` —— 仍是"静默空日历"同类隐患**
`api_list_events` 外层 `except` 当前 `return JSONResponse([])`。若数据库故障 / 参数解析失败，前端拿到 200 + 空数组 → 日历静默空白、无红字横幅。这与用户此前"创建没反应"是同一失败模式。
- **Why**：范围解析失败或 DB 异常本应让用户/AI 看到，现在被悄悄抹成"没事件"。
- **Suggestion**：范围参数为空时仍返回 `[]`（合理）；但其余异常应**抛出**或返回 `ok:false`，让前端 `.catch` 显示红字横幅。前端 `loadEvents` 已处理 fetch 失败分支，改动风险低。

**2. `write_day` 全量 DELETE + INSERT —— 并发写可能丢事件**
每次写某天都先 `DELETE FROM events WHERE day=?` 再整表重插。单人桌面罕见并发，但若同一天两个写操作交错（读→改→写），后写可能覆盖先写。
- **Suggestion**：改为按 `event_id` UPSERT（SQLite `ON CONFLICT`），或加轻量进程内锁。当前单人可接受，列为已知局限。

**3. 连接未复用**
`read_day`/`write_day` 每次操作新建一个 sqlite3 连接。单人低数据量无碍；未来日事件多 / 范围大时，连接开销累积。
- **Suggestion**：引入单连接或短连接池（如 `sqlite3` 连接缓存），或确认 `check_same_thread=False` 后复用。

**4. `preheat` 重复模式不被展开**
`api_create_schedule` 默认 `repeat_mode="preheat"`，但 `expand_recurring_schedules` 没有 `preheat` 分支，创建的预热 schedule 永远不会出现在日历。
- **Suggestion**：若预热是未来功能，在 `expand_preheat_schedules`（当前返回 `[]`）实现并在注释说明；若已弃用，把默认值改为 `none` 或明确告知前端。

**5. 重复事件 `event_id` 日期解析脆弱**
`api_update_sop_step` 用 `event_id.split("-")` 取末三段拼日期。当前 `schedule_id` 形如 `schedule-xxxx`（恰含一个 `-`），解析碰巧正确；一旦 `schedule_id` 含更多 `-` 就会解析错。
- **Suggestion**：`event_id` 改用固定分隔符（如 `recurring::{sid}::{date}`），或在 occurrence_overrides 表存结构化 `schedule_id` + `date` 字段，不再从 id 反解。

### 💭 小建议（Nit）

- **过时注释**：`utils.all_events_in_range` docstring 仍写 "from daily JSON files"；`daily_file()`/`timelog_file()` 标注 legacy 但仍保留——若确无引用可删，减少误导。（本轮已修 `api_update_event` 的 "JSON" 注释。）
- **缺自动化测试**：`ARCHITECTURE.md` L6 标记的"无测试层"仍未补。我们手动用真实路由函数 + 真实 DB 验证过关键路径，但未固化成可重复跑的测试。建议至少为 `store` 层 + 关键路由加冒烟测试，防回归。
- **`api_cell_backgrounds` 内联常量**：`PRIORITY`/`COLORS` 映射每次请求重建，可提为模块级常量。

---

## 四、本轮已修复项（封顶附带）

| # | 文件 | 改动 | 类型 |
|---|------|------|------|
| 1 | `api.py` `api_update_event` | kind 校验从硬编码元组改为 `KIND_COLORS` 单一真相源，与 `api_create_event` 一致 | 🟡 契约 bug |
| 2 | `api.py` `api_update_event` | docstring / 注释中过时的 "JSON" 表述改为 SQLite | 💭 文档 |

> 修复验证：`py_compile` 通过；`KIND_COLORS` 键 = `[sop, tool, reminder, external, marker]`，更新接口现已能接收创建接口允许的全部 kind。

---

## 五、封顶交付清单（本批）

- [x] 本轮修复 kind 枚举不一致 + 过时注释
- [x] 本审查报告（`docs/REVIEW_T3_FINAL.md`）
- [x] ADR-001 正式文档（`docs/ADR-001-sqlite-migration.md`）
- [x] `ARCHITECTURE.md`：ADR-001 状态 → 已采纳；L2 迁移脚本 → 已实施；L7 并发 → 部分验证
- [x] `FLOWCHART.md`：节点 TE 存储引用 → SQLite
- [x] `BLUEPRINT.md`：当前重心补注 v0.4 地基已完成，转向业务功能

---

## 六、下一步建议

地基封顶完成，**优先进入业务功能**：时间审计（量化每单耗时/时薪）、酷家乐 SOP 环节自动化推进。🟡 建议项（尤其 #1 静默空日历、#5 event_id 解析）可在做业务功能时一并收掉。
