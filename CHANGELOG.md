# Changelog

> 所有值得记录的变更（Keep a Changelog 格式）

---

## [Unreleased]

### Added
- **A2 SOP 计时器**：SOP 页面"开始计时"按钮真正记录时间（客户端 JS 计时，写入 `data/timelog/`）
- **A1 时间审计页面**：新增 `/audit` 页面，显示时薪、总收入、按 SOP 统计
- **T4 SOP 事件引导**：创建 SOP 事件后弹窗引导打开 SOP 流程页
- **T6 SOP 页面入口**：SOP 事件详情对话框显示"打开 SOP 流程页"按钮
- **T3 设置入口**：导航栏新增"设置"按钮，弹出设置对话框，可切换叠加层显示（节气/购物节/节假日/学期）
- **T2 叠加层事件显示**：日历现在显示节气、购物节、法定节假日、学期开学日（只读全天事件）

### Changed
- **T1 编辑对话框**：替换浏览器原生 `prompt()` 为自定义美观对话框，支持标题+分类编辑
- **T5 节假日数据**：启动时后台自动获取当年法定节假日数据（timor.peanut API），存本地缓存

### Fixed
- `generate_overlay_events()` 年份判断错误（非 2025 年数据错误显示）

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
