# BUGLOG-calendar-blank-0706-FIXED

> 疑难 Bug 归档。原始调试历时 19 轮（方案 1~19），横跨 2026-07-05 晚 ~ 2026-07-06。
> 触发：同症状连续 ≥3 轮未过验收（远超阈值），用户多次显式要求"记录所有失败经验"。
> 流程依据：bug-triage skill（疑难杂症处理流程）。
> 状态：✅ 已修复并验收（提交 `6869719`），本文件即收敛归档。

## 症状
DayPilot 周视图日历网格高度 < 容器，日历内部时间轴下方、以及日历与底部面板之间长期出现空白；
用户原话："从昨晚到现在日历的高度就没有变高哪怕一次"。窗口态 / 最大化态的空白大小还不一致。

## 最终根因
DayPilot `height:"auto"` 只在 `dp.init()` 算一次高度，并给 `#calendar` 写内联 `height:580px !important` 钉死；
resize / 最大化后不重算 → 日历底边缘与底部面板顶之间出现真实空白；
且面板高度若随窗口变化，两态空白大小不同。

## 最终方案（方案 19，提交 6869719）
- 放弃所有"测量后动态调整"的思路，改为**锁定固定常量** `TARGET_PANEL = 360`（一处可调）。
- `pages/index_page.py`：`#calendar { bottom: var(--panel-h, 360px) }`、`#detail-panel { height: var(--panel-h, 360px) }`。
- `static/init.js`：删除 `getCalBottom / isMaximized / 测量 + localStorage 缓存` 整套逻辑，
  `lockPanelHeight()` 直接写 `--panel-h:360px` 并清掉旧缓存；窗口态 / 最大化态都强制同一值。
- 效果：两态高度 100% 一致，窗口态上方日历区被压缩、底部工具条纹丝不动。
- 全程**未修改 DayPilot 的 cellHeight / height 配置**（遵守用户硬约束）。

## 教训（可复用戒律）
1. 同一 Bug 同方向连败 ≥3 轮 → 停手换思路（PM 重试≤3）。本案例拖到第 10 轮才彻底转向。
2. 不猜第三方库内部逻辑；读文档 + 量真实 DOM（`getBoundingClientRect`）拿证据。
3. 测空白用「真实边缘差」（日历底 − 面板顶），别用「容器高 − 渲染高」（被 `!important` 钉成≈0）。
4. CSS `!important` 干不过内联 `!important`；要改第三方库表现，改它的配置，别对抗样式。
5. 全屏 / 绝对定位必须减导航栏高度，否则整体溢出视口、底部被裁到屏外。
6. 测量引发竞态 / 振荡时，**锁定固定常量优于反复测量**。
7. 验证走应用内诊断工具（🔧 按钮，一键复制纯文本），绝不让人看 `console.log`。
> 上述戒律已沉淀进 bug-triage skill 的 `ANTI-PATTERNS.md`（9 条），本案例即其来源，无需重复维护。

## 已排除方向（永不重试）
- 修改 DayPilot `cellHeight` / `height` / 任何高度配置（方案 1~10，×10 轮全败；用户明确禁止）
- 调用 `dp.update()` 触发重绘（方案 2、12，无效，auto 高度不重算）
- 比「容器高 − 渲染高」测空白（方案 13，被钉死永远≈0）
- CSS `!important` 对抗 DayPilot 内联 `!important`（方案 12，优先级干不过）
- 钉死日历高度 / `setInterval` 稳定循环（方案 15，阻止自适应 + 测旧值竞态）
- 面板高度跟窗口变（方案 14~17，窗口 280 / 最大化 332，两态空白不同）
- `console.log` 验证（被用户否决，改用诊断按钮）
- 全页 flexbox 改 HTML 结构导致 UI 全白（方案 8，div 未闭合）
- 误建 `nul` 保留设备名文件阻断 `git add`（工程坑，已加 `.gitignore`）
