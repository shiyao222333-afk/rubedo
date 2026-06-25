# Rubedo · 凝华 — 项目进度

> 更新于：2026-06-25

---

## 版本状态

| 版本 | 状态 | 内容 | 完成日期 |
|------|:--:|------|:--:|
| v0.1.0 | ✅ | 蓝图 + 管理文件 | 2026-06-25 |
| v0.2.0 | ✅ | 平台基建：主界面 + 时间审计 | 2026-06-25 |
| v0.3.0 | 🔮 | 酷家乐 SOP 建立 | — |

---

## v0.2.0 交付物

### 核心功能
- DayPilot Lite 周视图日历（30分钟粒度、24小时覆盖、双色卡片）
- 重复事件（daily/weekly/weekday/monthly，模板 + 运行时展开）
- 时间审计计时器（开始/暂停/继续/结束 + 收入输入 + 自动时薪）
- APScheduler 持久化（SQLite JobStore，schedule 自动同步 cron job）

### API 端点
| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /api/events | 日历事件（含重复展开） |
| POST | /api/events | 创建/更新事件 |
| POST | /api/events/delete | 删除事件 |
| GET | /api/schedules | 重复事件模板 |
| POST | /api/schedules | 创建/更新模板 |
| POST | /api/schedules/delete | 删除模板 |
| GET | /api/timelog/today | 今日时间审计 |

### 页面
- `/` — 主界面日历
- `/sop/kujiale` — 酷家乐 SOP（骨架）
- `/sop/general` — 通用 SOP（骨架）

---

## 已知限制（v0.2.0）
- 拖拽 schedule 实例到不同日期时覆盖行为不完整（边缘情况，v0.3.0 处理）
- APScheduler job 仅记录日志，未连接实际 SOP 执行（v0.3.0+）
- SOP 页面为骨架

---

## 下一步
1. **用户本地测试**：`run.bat` 启动，验证日历/计时器/重复事件
2. **Git push**：沙箱无法推送，需用户本地执行
3. **v0.3.0 规划**：酷家乐 SOP 需求确认清单 + 环节定义 + 手动/自动标注
