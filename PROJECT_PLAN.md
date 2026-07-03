# Rubedo · 凝华 — 项目计划

> 版本：v0.3.0 | 更新于：2026-06-28

---

## 当前状态

- 当前版本：**v0.3.0**（酷家乐 SOP：阶段定义 + 简化计时 + 时间审计 + 日历体验升级）
- 开发中版本：**v0.4.0**（环节自动化）
- 已完成（代码）：T1~T6（日历体验升级）、A1（时间审计页面）、A2（SOP 计时器）、A3（事件锁定 UI）、A4（重复事件管理 UI）、节假日背景色修复（6个根因 + 列头节日文字）
- 新增功能（v0.3.0 代码，待发布）：创建事件字段完善（日期/时间选择器、备注、提醒）、节假日管理（购物节/法定节假日/自定义节假日）、预热重复事件（节假日前X天触发）
- 下一步：v0.4.0 环节自动化（APScheduler + SQLiteJobStore）
- Git 状态：main 分支，节假日背景色修复已 commit + push

---

## 段落索引（grep 关键词）

| 想找什么 | grep 关键词 |
|-----------|-------------|
| 当前状态 | `## 当前状态` |
| 版本路线 | `## 版本路线图` |
| MVP 优先级 | `## MVP 优先级` |
| 设计决策 | `## 设计决策` |
| 远期待办 | `## 远期待办` |

---

## 版本路线图

| 版本 | 状态 | 阶段 | 内容 | 说明 |
|------|:--:|------|------|------|
| v0.1.0 | ✅ | 启动 | 蓝图 + 管理文件 | 项目宪法就位 |
| v0.2.0 | ✅ | 平台基建 | 主界面 + 时间审计 | DayPilot日历 + 时间审计 + 重复事件 + APScheduler |
| v0.3.0 | ✅ | 酷家乐 SOP:1 | **SOP 建立 + 计时** | 四阶段定义(kujiale.json) + 简化计时按钮 + 时间审计统计页 |
| v0.4.0 | 🔮 | 酷家乐 SOP:2 | **环节自动化** | 逐个环节手动→自动，每换一个量化省时 |
| v0.5.0 | 🔮 | 酷家乐 SOP:3 | **数据回流 + AI 优化** | 执行数据→Citrinitas；5单后自动改进清单 |
| v0.6.0 | 🔮 | 扩展 | 小红书 SOP | 模仿酷家乐 SOP 模式：建立→自动化→智 |

---

## MVP 优先级

| 优先级 | 版本 | 内容 | 对应蓝图验收标准 |
|:--:|:--:|------|------|
| 🔴 P0 | v0.2.0 | 平台基建：主界面 + 时间审计 | #2 时薪可见 |
| 🔴 P0 | v0.3.0 | 酷家乐 SOP: 阶段定义 + 简化计时 + 时间审计 | #1 流程搬进来 + #2 时薪可见 |
| 🟡 P1 | v0.4.0 | 酷家乐 SOP: 逐个环节自动化 | #4 切换验证 + 原则 #2 逐步自动化 |
| 🟡 P1 | v0.5.0 | 酷家乐 SOP: 数据回流 + AI 优化 | #3 越用越聪明 + 原则 #5 数据回流 |
| 🟢 P2 | v0.6.0 | 小红书 SOP（模仿酷家乐模式） | 带着做，不占重心 |

---

## 技术选型

| 决策 | 方案 | 理由 | 状态 |
|------|------|------|:--:|
| UI 框架 | **NiceGUI** (native=True) | 桌面原生窗口，Python 全栈，组件丰富，含 FullCalendar 示例可参考集成模式 | ✅ 已定 |
| 主界面日历 | **DayPilot Lite** (Apache 2.0) | 详见设计决策 #6。唯一同时满足 cellHeight 硬锁定 + 日历日期模式 + 内建编辑弹窗/右键菜单的方案 | ✅ 已定 |
| SOP 页面结构 | 每个 SOP 独立页面/模块 | 蓝图原则 #3 "一个 SOP 一个页面" | ✅ 已定 |
| 手动/自动切换 | 环节级开关 + 状态持久化 | 蓝图原则 #2 "逐步自动化" | ✅ 已定 |
| 数据存储 | **本地 JSON**（data/YYYY-MM-DD.json） | 单人工具，每日一文件，轻量可读，无需数据库服务 | ✅ 已定 |
| 任务调度 | **APScheduler** (AsyncIOScheduler) | 紫色卡片到点自动触发，与 NiceGUI asyncio 事件循环天然兼容 | ✅ 已定 |

---

## 设计决策

> 可追溯的设计决策记录。

### v0.1.0 决策（2026-06-25）

| # | 决策 | 理由 |
|---|------|------|
| 1 | 蓝图确立 | 蓝图对话模式创建，经 3 轮讨论定稿 |
| 2 | 酷家乐优先 | SOP 已跑通在赚钱，优化比新建更优先 |
| 3 | SOP 页面而非工作流引擎 | 环节顺序固定，不需要可视化拖拽编排 |
| 4 | 主界面 = 时间日程视图 | 用户设想：打开就看到今天干什么 |
| 5 | SOP 内容理解分工 | 酷家乐微信需求提取 → 凝华调用 Nigredo API 获取消息，自调 LLM 分析内容；小红书/B站仿写 → Nigredo API。自动化采集（企微监控/爬虫）全部走 Nigredo。 |
| 6 | 主界面日历：DayPilot Lite | **唯一方案，不设备选。** 6 候选逐项对比结论：DayPilot Lite（Apache 2.0）是唯一同时满足 cellHeight 硬锁定 + 日历日期模式 + 内建弹窗/右键菜单的方案。详见 v0.2.0 技术架构。 |
| 7 | v0.2.0 遗漏审查（2026-06-25） | 四维度审查（蓝图对照/数据架构/技术集成/状态边界）发现 7 个遗漏，其中 4 个必须在 v0.2.0 解决（详见"7 个遗漏"节），3 个留 Phase 1 拆解时定。 |

### v0.2.1 决策（2026-06-26）

| # | 决策 | 理由 |
|---|------|------|
| 8 | **自动化采集交给 Nigredo** | 用户决策。企微监控/小红书爬虫/B站爬虫/电商数据采集，全部归馏析。凝华专注 SOP 执行和变现，通过 HTTP API 调用 Nigredo 获取外部数据。Nigredo 是"手脚"，凝华是"大脑+执行"。 |

### v0.3.0 决策（2026-06-28）

| # | 决策 | 理由 |
|---|------|------|
| 9 | **简化版计时器** | 用户要求"不用太复杂"：per-step 开始/完成按钮，不做实时倒计时。耗时 = 完成时间戳 - 开始时间戳，写入 timelog 文件 |
| 10 | **一单一文件** | timelog 按 `YYYY-MM-DD_sop_N.json` 存，便于按天查找和统计，单文件不大，无需数据库 |
| 11 | **只对手动/半自动计时** | 自动步骤（`est_min: 0`，由 Nigredo 执行）不显示按钮，不计入用户耗时统计 |

### v0.4.0 设计点（2026-07-04）

| # | 设计点 | 内容 |
|---|--------|------|
| 12 | **自动化执行保障** | 环节自动化（APScheduler + SQLiteJobStore）需要保证程序不运行时也能触发。设计两层保障：① **开机自启**（Windows 注册表/Startup 文件夹，凝华随系统启动 → APScheduler jobs 从 SQLite 自动恢复）；② **兜底扫描**（程序启动时扫描过期的计划任务，标记/补偿执行）。具体实现到 v0.4.0 时定。 |
| 13 | **DayPilot Lite 时区陷阱** | DayPilot 内部用 UTC 时间戳（`toDate()` 返回本地时间，UTC+8 下 16:00 后跨天）。格子日期必须用 `start.value.slice(0,10)` 取 UTC 日期部分，不能用 `toDate()`。`locale:"zh-cn"` 不自动设置 `weekStarts`，必须显式 `weekStarts:1`。dayjs `isoWeek` 需插件，未加载时静默返回当前时刻不报错。 |

## 7 个遗漏（2026-06-25 审查）

> 按蓝图 v0.2.0 = "主界面 + 时间审计"对照审查，发现 7 个缺口。

### 路线 A（v0.2.0 必须补）

| # | 遗漏 | 严重度 | 解决方案 |
|---|------|:--:|------|
| 1 | **时间审计完全缺失** | 严重 | 在日历下方/侧栏增加计时器面板：开始/结束按钮 + 显示当前耗时 + 每单收入输入框 → 自动算时薪。每周汇总统计面板。数据结构见下方"时间审计数据" |
| 2 | **重复事件无设计** | 重要 | 事件增加 `repeat` 字段（daily/weekly/weekday/monthly），数据层按"模板 + 运行时展开"方式——模板存 `data/schedules.json`，运行时按日期范围展开到 `data/YYYY-MM-DD.json`。单次覆盖（改"下周一的时间"）覆盖展开后的副本 |
| 3 | **SOP 环节定义无存储** | 重要 | 每个 SOP 一个 JSON 文件（`data/sops/kujiale.json` 等），定义环节列表 + 每环节的手动/自动默认值 + SOP 页面路由。v0.2.0 先建酷家乐骨架（1 个环节即可），v0.3.0 补全 |
| 4 | **DayPilot JS ↔ NiceGUI Python 通信协议** | 重要 | 采用方案 B（fetch + API）：DayPilot onEventClick → fetch 调用 Python API → NiceGUI 返回数据/指令 → Python 端 `ui.navigate.to()` 切换页面。事件 CRUD 同理：fetch → Python 处理 → 返回 JSON → DayPilot events.update() |

### 路线 B（v0.2.0 拆解时定）

| # | 遗漏 | 严重度 | 方向 |
|---|------|:--:|------|
| 5 | **页面导航/路由结构** | 待补充 | NiceGUI 用 `@ui.page('/')` + `@ui.page('/kujiale')` 等定义路由。日历主页为 `/`，SOP 页面独立路由。导航栏（顶栏或侧栏）在拆解时定。 |
| 6 | **APScheduler 持久化** | 待补充 | 换 SQLAlchemyJobStore（SQLite），重启后自动任务维持。拆解时定。 |
| 7 | **边界状态** | 待补充 | 首次打开空日历显示引导文字 + "新建事件"按钮。CDN 失败降级显示提示。重叠事件 DayPilot 内建处理（并排显示）。拆解时定。 |

### 时间审计数据结构

```json
{
  "sopId": "req-001",
  "sopType": "kujiale",
  "startedAt": "2026-06-25T14:05:00",
  "endedAt": "2026-06-25T15:20:00",
  "durationMin": 75,
  "revenue": 300,
  "hourlyRate": 240
}
```

计时逻辑：用户点 SOP 事件 → 跳转 SOP 页面 → 页面顶部显示计时器 → 用户点"开始"计时 → 完成 SOP 后自动停止 → 弹窗输入收入 → 算时薪 → 存入 data/timelog/YYYY-MM-DD.json。

## v0.2.0 技术架构（DayPilot + NiceGUI 集成）

```
NiceGUI app.py (Python 后端)
    │
    ├── ui.add_head_html() → 加载 DayPilot JS/CSS (CDN)
    ├── ui.html() → <div id="calendar"> 容器
    ├── API 端点 (/api/events?start=X&end=Y) → 返回 JSON 事件列表
    └── ui.run_javascript() → 双向通信

DayPilot Calendar (JS 前端，运行在 NiceGUI webview 中)
    │
    ├── viewType: "Week"          → 周视图（周一~周日 + 具体日期）
    ├── cellDuration: 30          → 30分钟一格子
    ├── cellHeight: 30            → 每格 30px 硬锁定
    ├── dayBeginsHour: 0          → 从凌晨 0 点开始
    ├── dayEndsHour: 24           → 到深夜 24 点结束
    ├── onEventClick → SOP 路由   → 点击卡片跳转对应 SOP 页面
    ├── contextMenu → 快捷操作    → 右键菜单（完成/跳过/编辑/删除）
    └── events 数据              → Python 后端通过 /api/events 提供
```

## 事件卡片数据结构

```json
{
  "id": "evt-001",
  "start": "2026-06-25T09:00:00",
  "end": "2026-06-25T10:30:00",
  "text": "酷家乐需求确认",
  "backColor": "#7F77DD",
  "barColor": "#534AB7",
  "tags": {
    "type": "sop",
    "sopPage": "kujiale",
    "sopId": "req-001",
    "status": "pending"
  }
}
```

| tags 字段 | 值 | 说明 |
|-----------|-----|------|
| type | `"auto"` / `"sop"` | 紫色自动程序 / 绿色 SOP 工具包 |
| sopPage | `"kujiale"` / `"xiaohongshu"` / `"general"` | 路由目标页面 |
| sopId | 字符串 | SOP 实例唯一标识 |
| status | `"pending"` / `"done"` / `"skipped"` | 完成状态 |

---

## 参考项目

| 项目 | 关系 |
|------|------|
| [OpusMagnum](https://github.com/shiyao222333-afk/opus-magnum) | 总指挥部，定义 Rubedo 为阶段 B Route C |
| [Citrinitas](https://github.com/shiyao222333-afk/citrinitas) | 知识引擎，Rubedo 从它检索、向它回流数据 |
| [Nigredo](https://github.com/shiyao222333-afk/nigredo) | 外部数据采集引擎 — 企微自动化/爬虫/数据抓取。Rubedo 通过 HTTP API 调用其采集能力。 |
| [Albedo](https://github.com/shiyao222333-afk/albedo) | 矛盾检测，Rubedo 生成的内容可经它验证 |

---

## 远期待办

| ID | 内容 | 说明 | 优先级 |
|----|------|------|:--:|
| R2 | 效果图批量渲染 | 模板 + 批处理 | 🟢 |
| R4 | 过程录屏 → B 站脚本 | SOP 执行过程录屏自动转内容 | ⚪ |
| R5 | 移动端适配 | 边界暂不做，远期考虑 | ⚪ |

---

## 管理文件体系

| 文件 | 职责 | 状态 |
|------|------|:--:|
| `BLUEPRINT.md` | 项目宪法 | ✅ |
| `PROJECT_PLAN.md` | 本文件 | ✅ |
| `FLOWCHART.md` | 流程图 | ✅ |
| `CHANGELOG.md` | 变更记录 | ✅ |
| `README.md` | 对外介绍 | ✅ |
