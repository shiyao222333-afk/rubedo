# Rubedo 日历技术栈研究报告

> 研究日期：2026-07-01
> 研究人：AI Assistant
> 目的：确认日历技术栈选型是否需要调整（原方案：DayPilot Lite）

---

## 一、原决策回顾（PROJECT_PLAN.md 设计决策 #6）

**结论**：DayPilot Lite 是**唯一方案，不设备选**。

6 个候选方案逐项对比后，DayPilot Lite（Apache 2.0）是唯一同时满足以下三个硬约束的方案：
1. **cellHeight 硬锁定**（每格高度固定为 30px，不可弹性伸缩）
2. **日历日期模式**（周视图，横轴周一~周日，纵轴 0~24h）
3. **内建编辑弹窗/右键菜单**（原生支持，无需自定义）

---

## 二、当前问题

DayPilot Lite 从 CDN 加载（`jsdelivr.net` / `daypilot.org`），**国内网络无法访问**，导致：
- 浏览器打开后**黑屏**（JS 加载失败）
- 无法离线使用

---

## 三、方案对比

### 方案 A：DayPilot Lite + 本地离线部署（推荐 ✅）

**原理**：DayPilot Lite 使用 Apache 2.0 许可证，**允许下载 JS/CSS 文件到本地使用**。

**实施步骤**：
1. 获取 `daypilot-lite.min.js` 和 `daypilot-lite.min.css` 文件
2. 放入 `D:\rubedo\static\` 目录
3. 修改 `app.py` 的 `add_head_html()` 从本地加载

**优点**：
- ✅ 完全还原原设计（横轴星期、纵轴时间、卡片事件）
- ✅ 所有功能原生支持（cellHeight 锁定、右键菜单、事件点击）
- ✅ 离线可用，不依赖任何 CDN
- ✅ 许可证合规（Apache 2.0）

**缺点**：
- ❓ 需要获取 DayPilot Lite 的 JS/CSS 文件（官方 CDN 在国内不可访问）

**文件获取途径**：
1. npm 安装（`npm install daypilot-lite`，然后复制 `node_modules/daypilot-lite/dist/` 下的文件）
2. GitHub 直接下载（https://github.com/daypilot/daypilot-lite）
3. 官方下载页（https://daypilot.org/，需翻墙）

---

### 方案 B：切换到 FullCalendar

**原理**：FullCalendar 是更流行的日历库，有国内 CDN 镜像（BootCDN）。

**功能对比**：

| 功能 | DayPilot Lite | FullCalendar (Standard/MIT) |
|------|---------------|-------------------------------|
| cellHeight 硬锁定 | ✅ 原生支持 | ❌ 不支持（`expandRows` 是弹性扩展） |
| 周视图（横轴星期） | ✅ 原生支持 | ✅ `timeGridWeek` |
| 30min 粒度 | ✅ `cellDuration: 30` | ✅ `slotDuration: '00:30'` |
| 事件颜色 | ✅ `backColor`/`barColor` | ✅ `backgroundColor`/`borderColor` |
| 事件点击 → 页面跳转 | ✅ 原生支持 | ✅ `eventClick` 回调 |
| 右键菜单 | ✅ 内建 `contextMenu` | ❌ 需自定义（JS 手动实现） |
| 0~24h 范围 | ✅ `dayBeginsHour`/`dayEndsHour` | ✅ `slotMinTime`/`slotMaxTime` |
| 国内 CDN 可访问 | ❌ | ✅ BootCDN 镜像 |
| 许可证 | Apache 2.0 | MIT（标准功能）/ 商业授权（高级功能） |

**关键缺陷**：FullCalendar **不支持 cellHeight 硬锁定**。行高会根据容器大小弹性调整，无法实现"每格固定 30px"的设计要求。

**结论**：FullCalendar **不满足原设计约束**，不推荐。

---

### 方案 C：用 NiceGUI 原生组件自建日历

**原理**：用 `ui.grid()` + `ui.card()` + `ui.label()` 手写一个周视图时间表。

**优点**：
- ✅ 无 CDN 依赖
- ✅ 完全可控

**缺点**：
- ❌ 开发量大（需要实现时间网格、事件渲染、拖拽、点击交互等）
- ❌ 视觉效果不如专业日历库
- ❌ 不支持 cellHeight 硬锁定（需要用 CSS 手动实现）

**结论**：不推荐（投入产出比低）。

---

## 四、结论与建议

| 方案 | 是否满足原设计 | 实施难度 | 推荐度 |
|------|:--------------:|:--------:|:------:|
| A：DayPilot + 本地离线 | ✅ 完全满足 | 低（获取文件+改路径） | ⭐⭐⭐⭐⭐ |
| B：切换到 FullCalendar | ❌ 不满足 cellHeight | 中（需重新集成） | ⭐ |
| C：NiceGUI 原生自建 | ❌ 功能不完整 | 高（大量开发） | ⭐ |

**建议**：**坚持原方案（DayPilot Lite），通过本地离线部署解决 CDN 访问问题**。

**下一步行动**（需用户确认）：
1. 通过 npm 或 GitHub 获取 DayPilot Lite 的 JS/CSS 文件
2. 放入 `D:\rubedo\static\`
3. 修改 `app.py` 的 `add_head_html()` 从本地加载
4. 测试验证

---

## 五、参考资料

- DayPilot Lite 官网：https://daypilot.org/
- DayPilot Lite 许可证：Apache 2.0（允许本地部署）
- FullCalendar 文档：https://fullcalendar.io/docs
- FullCalendar 许可证：MIT（标准功能）/ 商业授权（高级功能）
- BootCDN FullCalendar 镜像：https://www.bootcdn.cn/fullcalendar/

---

> 待用户确认后执行。未经确认不得修改方案。
