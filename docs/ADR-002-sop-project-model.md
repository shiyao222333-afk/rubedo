# ADR-002: 手动 SOP 工作流 — 项目模型与工具分发决策

## Status
Accepted（2026-07-08，用户拍板）

## Context
v0.4 地基完成后转入"手动 SOP 工作流补全"。设计研究（DESIGN-Manual-SOP-Workflow.md、DESIGN-SOP-Tools-Model.md、GAP-ANALYSIS-SOP-Tools.md）暴露出 5 个"动手前不定量就会返工/崩溃"的决策点，经用户确认如下。本 ADR 把它们钉死，避免后续实现漂移。

## Decision

### D1 — 进度用 step_id 字符串，不用整数序号（G1）
`projects.sop_current_step` 与 `step_data` 的键都用 SOP 步骤 id（如 `"1.3"`），不存第 N 步整数。
**理由**：SOP YAML 必然增删步骤，整数序号会全错位，进行中项目进度直接乱。step_id 稳定。
**后果（+）**：改 SOP 不影响在途项目。**（-）**：显示"第几步/共几步"需数一下；UI 偶尔要把 step_id 映射回序号。

### D2 — 计时进行中状态持久化（G2）
点"开始计时"后，进行中计时写入库（project.step_data 的 `active_timer:{step_id, started_at}`），关面板/刷新后重开能恢复续算。
**理由**：真实接单常中途关面板，纯内存计时会归零导致时长错误。
**后果（+）**：计时正确。**（-）**：timer 启停各多一次写库（可接受）；需防同项目多标签并发起多个进行中（G29，后期单项目强制只有一个 active_timer）。

### D3 — 计时写入 timelog，不写事件 JSON（G3）
计时结束 → 写 `timelog`（带 project_id / step_id / occurrence_id）+ 更新 `project.step_data` 该步 duration；事件 JSON 不再存计时。
**理由**：此前底部面板计时写进了事件 JSON（`sop_step_timings`），与"进度归项目 + 统一 timelog"冲突，正是 T3 反复修的"数据分裂"毛病。
**后果（+）**：单一审计表、无分裂、旧 `audit_page` 不受影响。**（-）**：需改计时写入代码路径（大类二 L10 落地）。

### D4 — SOP YAML 加载器加 schema 校验 + 安全降级（G4）
加载器校验 SOP 文件必须有 `id / tools / stages`，出错 → 红字提示 + 用上一次好版本兜底，不崩面板；声明了但代码未实现的工具 → 跳过 + 日志（G25）。
**理由**：YAML 写错会让加载器抛异常、点事件面板直接崩。
**后果（+）**：文件改错不崩。**（-）**：加一个校验函数 + 缓存上一次好版本。

### D5 — 回写蓝图，工具按 SOP 分发（G18）
BLUEPRINT.md 当前重心改为"手动 SOP 工作流补全"，核心原则加"工具按 SOP 分发（通用/独有，时间审计=酷家乐独有）"。
**理由**：蓝图是宪法，设计大半天未同步会漂移。
**后果（+）**：方向固化，后续模块有锚点。**（-）**：蓝图需随三大类推进持续回写。

## 明确不做的范围（本轮）
- 酷家乐 `time-audit` 时间审计工具：列入规划、**本轮不实现**（仅 timer 通用工具）。
- `sop_step_logs` 新表：废弃，统一到现有 `timelog`（P2 修订）。
- 项目状态机自动流转细节、接单按天绑定 UI、时薪聚合：留待对应大类/阶段。

## 关联
- 上游：ADR-001（SQLite 迁移，单库 rubedo.db）
- 下游：大类一 P0–P4、大类二 L2/L4/L10、大类三 U1–U4
