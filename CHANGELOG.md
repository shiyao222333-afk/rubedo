# Changelog

> 所有值得记录的变更（Keep a Changelog 格式）

---

## [Unreleased]

### Added
- **编辑对话框新增时间字段**：编辑事件时现在可以修改开始时间和结束时间
- **后端 API 支持更新时间**：`/api/events/update` 现在接受 `start` 和 `end` 字段
- **utils.py 补回缺失函数**：`all_events_in_range()`, `load_sop()`, `calc_hourly_rate()`（上次重构时丢失，本次补回）

### Changed
- **重构：拆分 app.py 减少 AI 点数消耗**：
  - `app.py` 从 ~1023 行精简到 ~90 行（薄入口）
  - 新建 `api.py`（全部 API 路由，~410 行）
  - 新建 `pages/index_page.py`（主页日历）
  - 新建 `pages/sop_page.py`（SOP 页面）
  - 新建 `pages/audit_page.py`（时间审计页面）
- **事件卡片点击行为改进**：点 SOP 事件打开 SOP 流程页，点非 SOP 事件空白区域什么都不做
- **右键菜单已移除**：不再弹出右键菜单，所有操作通过卡片上的行内按钮完成
- **编辑按钮功能明确**：点✏️按钮弹出编辑对话框（含标题/时间/备注/分类/提醒）

### Removed
- **`showContextMenu` 函数**：右键菜单相关代码已清理

### Fixed
- **并发安全**：所有文件 I/O（`read_day`, `write_day`, `read_schedules`, `write_schedules`, `read_occurrence_overrides`, `write_occurrence_override`, `read_timelog`, `write_timelog_entry`）添加 `filelock` 锁，防止多请求并发写入数据损坏
- **异常处理**：所有 API 路由的 `except Exception` 块添加错误日志（`print` + `traceback.print_exc()`），方便调试
- **硬编码年份修复**：`holidays.py` 中 `SOLAR_TERMS_2025` 改为 `SOLAR_TERMS_BY_YEAR`（支持 2024-2026 年），`api.py` 同步更新
- **输入验证**：关键 API 端点添加输入验证（`api_create_event`, `api_update_event`, `api_write_timelog`, `api_add_custom_holiday`）
- **时间选择联动（新建对话框）**：开始时间变化自动调整结束时间（如果结束时间更早或为空）
- **时间选择联动（编辑对话框）**：日期输入框加联动（`syncEndDateMin()`, `syncStartDateMax()`），结束日期不能早于开始日期
- **时间选择联动修复**（编辑对话框）：`syncEndTimeMin()` 和 `syncStartTimeMax()` 现在在重刷选项后自动修正无效选择（结束时间早于开始时间时自动选第一个合法选项，开始时间晚于结束时间时自动选最后一个合法选项）
- **新建对话框时间校验**（新建对话框）：新增时间校验——保存时检查结束时间必须晚于开始时间，否则 alert 并拒绝保存（之前无校验，`diff<=0` 时默认 60 分钟，导致可创建非法事件）
- **重复事件更新无效**（关键修复）：`api_update_event` 现在正确处理重复事件——检测到 `recurring=True` 时改 `schedules.json` 模板（影响所有 occurrence），而不是改 daily JSON（重复事件不在 daily 文件里）
- **API 返回 500 错误**（关键修复）：所有 API 处理函数改为返回 `JSONResponse(...)`（Starlette 要求），之前直接返回 dict 导致 `TypeError: 'dict' object is not callable`
- **部分路由 500 错误**（修复）：`api_list_schedules` 等无参数路由处理函数补充了 `request: Request` 参数（Starlette 要求所有路由处理函数必须接受 request 参数）
- **`api_list_events` 返回 500**（修复）：改为返回 `JSONResponse(events)` 而不是 `events` list
- **重复事件时长计算**：新建重复事件（每天/每周/每月/每年）时，现在根据对话框中选择的时间段计算实际时长，不再硬编码 60 分钟
- **A3 事件锁定 UI**：事件详情对话框新增"锁定/解锁"按钮，锁定后事件不可被重复事件展开覆盖
- **A4 重复事件管理 UI**：设置对话框新增"重复事件模板"列表，支持启用/禁用/删除模板
- **预热重复事件（Preheat）**：新增 `preheat` 重复模式——在购物节/法定节假日/自定义节假日前 N 天自动生成事件，支持"每年"或"仅今年"范围
- **通用重复事件展开**：新增 `expand_recurring_schedules()` 函数，支持 daily/weekly/monthly/yearly 四种重复模式按周期展开虚拟事件；schedule 模板新增 `start_date` 字段
- **新增 5 个电商节日**：情人节(2/14)、520(5/20)、88会员节(8/8)、教师节(9/10)、圣诞节(12/25)，全部兼容日历背景色 + 预热模式
- **动态节日引擎**：新增 `get_all_festivals_for_year()` 统一入口（替换散弹式 SHOPPING_FESTIVALS 引用），支持母亲节（5月第2个周日）、父亲节（6月第3个周日）、七夕（农历七月初七，通过 `lunar-python` 库）
- **特殊日子管理**：`/api/special-days?year=YYYY` 端点返回购物节、法定节假日、自定义节假日；设置页面支持添加/删除自定义节假日
- **创建事件字段完善**：新增日期/时间选择器（`datetime-local`）、备注（`textarea`）、提醒时间选择（事件开始时/提前15分钟/提前30分钟/提前1小时）
- **A2 SOP 计时器**：SOP 页面"开始计时"按钮真正记录时间（客户端 JS 计时，写入 `data/timelog/`）
- **A1 时间审计页面**：新增 `/audit` 页面，显示时薪、总收入、按 SOP 统计
- **T4 SOP 事件引导**：创建 SOP 事件后弹窗引导打开 SOP 流程页
- **T6 SOP 页面入口**：SOP 事件详情对话框显示"打开 SOP 流程页"按钮
- **T3 设置入口**：导航栏新增"设置"按钮，弹出设置对话框，可切换叠加层显示（节气/购物节/节假日/学期）
- **T2 叠加层事件显示**：日历现在显示节气、购物节、法定节假日、学期开学日（只读全天事件）

### Changed
- **T1 编辑对话框**：替换浏览器原生 `prompt()` 为自定义美观对话框，支持标题+分类编辑
- **T5 节假日数据**：启动时后台自动获取当年法定节假日数据（timor.tech API），存本地缓存；支持任意年份查询
- **API 地址修正**：timor.peanut.com → timor.tech，响应格式自动适配（含旧缓存格式兼容）
- **节假日缓存格式容灾**：`_normalize_holiday_data()` 统一处理 3 种输入格式（旧版 date-keyed / timor.tech v2 / 已规范化），缓存优先读取时也走规范化
- **重复事件数据层**：`data/schedules.json` 存储重复事件模板，`expand_preheat_schedules()` 在 `/api/events` 中运行时展开

### Fixed
- **节气/学期不再有背景色**：节气和学期改为只显示列头文字（如"🌿小暑"），格子背景保持白色；默认格子背景统一设为白色
- **重复事件不重复展开**：daily/weekly/monthly/yearly 模式此前只创建一次性事件，现改为创建 schedule 模板并运行时展开虚拟事件
- **节假日背景色不显示/错位**：6 个叠加 bug 逐个根因修复
  - `loadEvents()` 用 `dp.visibleStart()` 取日期范围，DayPilot 状态未更新返回旧周 → 改用 `currentStart`（dayjs 同步变量）
  - `dayjs().startOf("isoWeek")` 未加载 isoWeek 插件静默返回当前时刻 → 改纯数学算周一
  - `args.cell.start.toDate()` 在 UTC+8 跨天（16:00 后跳到下一天）→ 改用 `.value.slice(0,10)` 直接取 UTC 日期
  - 学期范围判断只比月份不比日期（`sm <= month <= em`）→ 改精确日期比较 `date(y,sm,sd) <= d <= date(y,em,ed)`
  - DayPilot 默认 `weekStarts=0`（周日开始），`locale:"zh-cn"` 不覆盖 → 显式加 `weekStarts:1`
  - `loadEvents` 日期范围 `add(7,"day")` 多算一天 → 改 `add(6,"day")` 闭区间
- **节日标题不显示**：新增 `onBeforeHeaderRender` 回调，列头格式 `周X M/D 节日文字`（如"周一 7/7 🌿小暑"）
- `generate_overlay_events()` 年份判断错误（非 2025 年数据错误显示）
- `ui.html()` 默认 `sanitize=True` 剥离 `onclick` 属性，导致所有按钮无响应（修复：加 `sanitize=False`）
- 购物节数据硬编码 2025 年（修复：改为按 MM-DD 动态计算任意年份）

## [v0.3.0] — 2026-06-28

### Added
- **酷家乐 SOP 定义**：`data/sops/kujiale.json`，四阶段（接单/私聊接单/需求沟通/酷家乐制作/交付收款），第一阶段含 7 个细化步骤
- **简化计时功能**：每个手动/半自动步骤显示 [▶ 开始] / [⏹ 完成] 按钮，点击后自动记录开始时间和完成时间，计算实际用时
- **时间记录模块**：`timelog.py`，订单数据存为 `data/timelog/YYYY-MM-DD_kujiale_N.json`，一单一文件
- **时间审计统计页**：`/sop/kujiale/stats`，按步骤汇总平均用时/最大用时/累计耗时，瓶颈步骤红色高亮，历史订单列表
- **SOP 页面重构**：从旧版扁平 steps 升级为 stages 分组展示，阶段标题 + 步骤卡片 + 模式标签（自动/手动/半自动）

### Changed
- SOP 页面底栏新增步骤完成进度和累计耗时

### Removed
- 删除 `on_startup()` 中旧版 kujiale.json fallback 代码（与新 stages 结构冲突）

## [v0.2.0] — 2026-06-25

### Added
- **主界面日历**：DayPilot Lite 周视图，30 分钟粒度，24 小时覆盖，双色卡片（紫色=自动，绿色=SOP）
- **数据层**：JSON 每日文件存储（`data/YYYY-MM-DD.json`），事件 CRUD
- **重复事件**：支持 daily/weekly/weekday/monthly 四种模式，模板存 `data/schedules.json`，运行时展开
- **时间审计**：底部计时器（开始/暂停/继续/结束），收入输入对话框，自动时薪计算，存入 `data/timelog/`
- **APScheduler 持久化**：AsyncIOScheduler + SQLite JobStore，schedule 自动同步为 cron job
- **边界状态**：CDN 失败降级提示 + 空日历欢迎引导
- **SOP 页面骨架**：酷家乐/通用 SOP 页面 + 导航桥
- **右键菜单**：完成/跳过/编辑/删除四项操作
- **NiceGUI native 模式**：桌面原生窗口（pywebview）
- 蓝图（BLUEPRINT.md）确立：愿景、5 条核心原则、当前重心、边界、4 条验收标准
- 项目计划（PROJECT_PLAN.md）确立：版本路线 v0.1.0 → v0.6.0，酷家乐 SOP 三阶段演化为主轴
- 流程图（FLOWCHART.md）确立：主干流程 19 节点 + 节点定义表
- 管理文件体系搭建：BLUEPRINT / PROJECT_PLAN / FLOWCHART / CHANGELOG

---

## [v0.1.0] — 2026-06-25

### Added
- 项目初始化：README.md 架构设计
- 时间记录工具 v0.1（tkinter 桌面程序，5 环节计时 + JSON 保存）

---

> 版本号规则：PATCH(0.1.x) = 仅Bug修复 | MINOR(0.x.0) = 新功能 | MAJOR(1.0.0) = 破坏性变更
