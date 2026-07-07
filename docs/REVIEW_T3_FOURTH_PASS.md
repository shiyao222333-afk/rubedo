# 第四轮代码审查报告（重构后 / 三个限制修复之后）

> 审查对象：`D:/rubedo` 当前 `main`（commit df41862 + cf7a2dd 之后）
> 视角：代码审查专家（火眼眼）—— 正确性 / 健壮性 / 可维护性，不抠风格
> 方法：逐文件读源码 + 前端渲染链路核对 + 前三轮已验证结论的回归复核

---

## 一、总体结论

**健康度：良好，无新增阻断性 bug。**

- 上一轮修的三个限制（event_id 索引、timelog 按事件日期、重复事件 SOP 步骤）经代码核对与历史测试**确认正确**，未引入回归。
- 之前几轮修的 `KIND_COLORS` 导入、`find_event_by_id` 契约、`busy_timeout`、日志接线、死代码清理都仍然成立。
- 本轮新发现**1 个值得修的中危隐患**（沉默空日历），+ 2 个前三轮已提但用户本轮未点名修的遗留项，+ 几个 💭 可选项。

一句话：**地基稳，但"静默失败"这种你最反感的模式还剩一个没堵死。**

---

## 二、发现清单

### 🟡（建议修）沉默空日历：`api_list_events` 吞掉一切异常返回 `[]`

**位置**：`api.py:233-235`

```python
except Exception as e:
    log.exception(f"api_list_events: {e}")
    return JSONResponse([])
```

**为什么这是真问题**
这正是你之前遇到的"创建了没反应"的同一种失败模式——**后端报错，前端零提示，用户看到的就是空/没变化**。

`api_list_events` 内部会调 `expand_recurring_schedules(start, end)`。这个函数对每个 `repeat_mode` 有一段日期展开逻辑，其中有**会抛异常**的路径，且没有任何内层保护：

- `yearly`：`current = start.replace(month=month, day=day)` —— 若用户建了一个"每年 2 月 30 日"的提醒（`month=2, day=30`），`date.replace` 直接 `ValueError`。
- 任意分支：若某条 schedule 模板缺 `id`，`s["id"]` 抛 `KeyError`。

一旦抛异常 → 被 `api_list_events` 的 `except` 接住 → **整周日历静默返回空数组**。一个配置错的重复计划，就能让整个日历变空白，且控制台可能都没人看。

**更关键**：上一轮的三个限制修复，给 `expand_recurring_schedules` 内部**新增了**读 `occurrence_overrides`、`s.get("sop_id")` 等逻辑，相当于把"可能抛异常"的代码路径又 widen 了一圈——这个隐患的爆炸半径变大了。

**建议修法（二选一，推荐第一个）**
1. **让 `expand_recurring_schedules` 自身有韧性**：在循环里对单条 schedule 包 `try/except`，记日志、跳过坏的那条、返回其余。这样"一个坏计划"不会拖垮整周。
2. 或至少把 `api_list_events` 的 `except` 收窄到具体异常，让真正的程序错误继续上抛而不是被吞成空列表。

> 这是本轮唯一我建议现在就动手的修改。

---

### 🟡（遗留，前三轮已提）`api_move_event` 找不到事件时仍返回 `ok:True, event:null`

**位置**：`api.py:255-277`

```python
moved = None
for i, ev in enumerate(events):
    if ev["id"] == data["old_id"]:
        moved = events.pop(i); break
if moved:
    ...
return JSONResponse({"ok": True, "event": moved})   # moved 为 None 也返回 ok:True
```

`old_id` 在 `old_day` 找不到时，`moved` 保持 `None`，却仍返回 `{"ok": True, "event": null}`。前端拖拽 handler（init.js）只判断 `data.ok`，于是误判成功、不弹错、刷新后事件停在原地——又是"拖了没反应"的模式。

**修法**：`if not moved: return {"ok": False, "error": "事件未找到"}`。（约 2 行）

---

### 🟡（遗留，P2）同一天事件的"读-改-写"非原子，存在丢失更新

**位置**：`api_update_sop_step` + `save_event_day`（DELETE+INSERT 整天）；同类 `api_move_event` / `api_update_status`

`find_event_by_id` 读整天 → 改一个事件 → `save_event_day` 把整天 DELETE 再 INSERT。同一天两个编辑并发发生时，后提交的会盖掉先提交的（"丢失更新"）。`busy_timeout` 只防 `database is locked` 报错，防不了这种逻辑覆盖。

单人桌面工具几乎不触发；但属已知架构债，未来做多用户/后台任务时需改成单事件 `UPDATE` 或乐观锁。

---

### 💭（可选）枚举不一致：`KIND_COLORS` 被当成 kind 校验表

**位置**：`api_create_event:63` vs `api_update_event:134`

- 创建：`if kind not in KIND_COLORS` → 只接受 `sop/tool/reminder/external/marker`。
- 更新：`if data["kind"] not in ("reminder","work","personal","holiday","sop")` → 接受 `work/personal/holiday`。

于是**你没法创建 `work` 事件，却能把已有事件改成 `work`**。而且用"颜色字典"当枚举源是代码异味：将来加一种事件类型若忘了配颜色，创建会静默拒绝。

**建议**：抽一个 `EVENT_KINDS = set(KIND_COLORS) | {...}` 之类，两处共用。当前前端创建对话框只给 `KIND_COLORS` 那 5 种，所以更新多出的几种 UI 上还点不到——但这是颗潜伏的雷。

---

### 💭（可选）`api_update_sop_step` 不校验 `step`

**位置**：`api.py:723,738`

`new_step = data.get("step")` 原样写入。前端永远发 int，但手工/craft 请求可发字符串、负数、超大值。防御性：`if not isinstance(new_step, int) or new_step < 0: return 错误`。低优先级。

---

### 💭（可选）API 路由无鉴权

所有 `/api/*` 完全开放。按蓝图边界"单人桌面工具、不面向多用户 SaaS"是可接受的（NiceGUI native 模式本地绑定）。仅提示：一旦把端口暴露到网络，接口可被任意写入。建议在文档里记一笔。

---

## 三、确认正确的部分（值得表扬）

- **三个限制修复经核对正确**：`event_id` 索引走 `find_day_by_event_id` O(1) 替代全表天扫描；`write_timelog_entry` 优先用 `entry["start_time"][:10]` 推算日期（异常回退今天，安全）；`expand_recurring_schedules` 给重复事件带 `sop_id`（默认 kujiale）并从 `occurrence_overrides` 读回 `sop_current_step`，`api_update_sop_step` 识别 `recurring-` 前缀正确拆出日期写回——逻辑自洽，历史功能测试已 PASS。
- **`find_event_by_id` 的唯一调用方就是 `api_update_sop_step`**，修复范围安全（已 grep 确认）。
- **`write_occurrence_override` 的 merge 逻辑干净**：status / locked / sop_current_step 共存于同一行 override，互不覆盖。
- **`busy_timeout` + 统一日志 + `setup_logging` 接线**全部就位且正确。
- **`write_schedules` 的 id 守卫**避免了主键冲突导致整批回滚。
- **前端 SOP 渲染器的兜底默认值**（`event.sop_id || 'kujiale'`、`event.sop_current_step || 0`）使得"手动在日历建的 sop 事件"也能正常显示酷家乐 SOP 并记录步骤，没有预想中的断链。

---

## 四、建议的下一步

只修一处就能消除"同源静默失败"：给 `expand_recurring_schedules` 加单条 schedule 的异常隔离（或收窄 `api_list_events` 的 except）。其余为遗留/可选项，不阻塞使用。

是否要我顺手修：
1. 🟡 沉默空日历（推荐，约 10 行）
2. 🟡 `api_move_event` 找不到时返回失败（约 2 行）

两处一起改 + 提交？
