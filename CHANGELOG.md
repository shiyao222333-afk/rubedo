# Changelog

> 所有值得记录的变更（Keep a Changelog 格式）

---

## [Unreleased]

### Added

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
