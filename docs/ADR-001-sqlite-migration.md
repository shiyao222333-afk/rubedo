# ADR-001 · 存储：JSON 文件 → 单文件 SQLite

| 字段 | 内容 |
|------|------|
| **状态** | ✅ 已采纳并實施（v0.4 地基已完成） |
| **提出** | 2026-06（ARCHITECTURE.md v1.0） |
| **实施** | 2026-07-05 ~ 2026-07-07（T3 任务） |
| **决策人** | shiyao222333-afk（五器工坊） |
| **相关** | ARCHITECTURE.md §2.3 / §8 L2 / L7；BLUEPRINT.md 核心原则 |

---

## 1. 背景（Context）

v0.3.0 的凝华是单体桌面程序，所有数据存在 `data/` 下的 JSON 文件（事件、计时、SOP、重复模板、自定义节日各自一个 JSON），靠文件锁（`filelock`）防并发冲突。随着使用，暴露出 ARCHITECTURE.md 第 1 节列的五条"长不大"隐患，其中与存储直接相关的两条：

1. **数据越积越慢** — JSON 文件随记录增多整体读写变慢；想查"某范围的事件"只能逐天读文件。
2. **文件锁并发脆弱** — 文件锁在异常处理/进程退出时易残留，导致后续写被永久阻塞。

此外，v0.4 的目标是把混在一起的逻辑拆成 5 个边界清晰的模块（日程/SOP/审计/自动化/集成），需要一个**统一、隔离、可被任意模块安全调用**的数据访问层，而不是让每个模块各自 `open(json)`。

## 2. 决策（Decision）

**v0.4 起，内部存储从 JSON 文件迁移到单文件 SQLite（WAL 模式）。** 所有读写经由统一的数据访问层 `modules/shared/store.py`（DAL），上层领域模块（日程/SOP/审计）只调用 DAL 接口，绝不直接碰存储文件。

关键设计取舍：

- **JSON blob 列**：表结构极简（`events(day, seq, data)`、`sop(sop_id, data)` 等），事件/计时等易变结构以整段 JSON 存 `data TEXT` 列 + 必要索引（`day`、`event_id`）。避免"加一个字段就要跑 ALTER 迁移"。
- **标准库 `sqlite3`**：不引入 SQLAlchemy，保持轻量、零额外依赖；DAL 用上下文管理器自动 commit/rollback。
- **依赖方向铁律**：`shared` 是最底层，绝不 import 上层 `utils`/`api`，避免循环依赖。
- **并发**：开 WAL + `PRAGMA busy_timeout=5000`，写冲突时等待而非立即报 `database is locked`。
- **迁移**：一次性 `migrate.py`（先备份 `data/` 再灌库）+ `rollback.py`（删库 + 恢复备份）。

## 3. 备选方案（Considered Alternatives）

| 方案 | 为什么没选 |
|------|-----------|
| 保持 JSON + 优化文件锁 | 治标不治本；查询/范围扫描仍要逐文件读；文件锁残留风险无解。 |
| 换 Postgres | 过度设计：单人桌面、数据量小，引入一个外部服务反而增加部署负担。ARCHITECTURE.md 明确"未来真遇瓶颈再换"，且存储已隔离，迁移成本低。 |
| 换 TinyDB / 其他嵌入式 DB | 增加外部依赖；SQLite 是 Python 标准库，零部署、生态成熟，性价比最高。 |

## 4. 后果（Consequences）

### 正面（+）
- 可写 SQL 查询（按天索引、`event_id` O(1) 定位、范围扫描秒回），不再逐文件读。
- 并发安全：WAL + busy_timeout，告别文件锁残留死锁。
- 数据访问统一封装，领域模块边界清晰，加新 SOP / 新业务不动存储细节。
- 存储已隔离，未来换 Postgres 是局部改动。

### 负面（−）
- 需一次性迁移脚本（旧 `data/` JSON → SQLite），有数据损坏风险 → 已用 `migrate.py` 先备份 + `rollback.py` 兜底。
- JSON blob 列意味着"结构演进"藏在应用层（读时兼容旧字段），DAL 不强制 schema；需在应用层保持兼容读取。

### 风险与缓解
- **并发写锁死** → `busy_timeout=5000` + 单写者模型（桌面单进程）。已部分验证（L7）。
- **迁移数据丢失** → `migrate.py` 先 `data_backup_*` 再灌库；`rollback.py` 删库恢复。
- **坏数据拖垮整页** → `api_list_events` 过滤缺 `start`/`id` 的坏事件；`expand_recurring_schedules` 单模板容错（见 REVIEW_T3_FINAL.md）。

## 5. 迁移步骤回顾

1. 建 `modules/shared/store.py`（DAL，WAL，6 张表 + 索引）。
2. `utils.py` 等 ~18 个直读 JSON 的函数改走 DAL，签名/行为不变（用户无感）。
3. `api.py` / `holidays.py` 中 5 处直读 JSON 的点同步切 DAL（防数据分裂）。
4. `migrate.py` 备份 `data/` → 逐 JSON 灌 SQLite；`rollback.py` 兜底。
5. 加 `event_id` 列 + 索引（`ALTER TABLE` 移出建表事务，独立连接执行）。
6. 四轮审查修复：KIND_COLORS 导入、busy_timeout、日志接线、坏数据过滤、SOP stages 渲染、kind 枚举一致性。

## 6. 回滚预案

- 若 SQLite 出现不可逆问题：`rollback.py` 删除 `rubedo.db` + WAL/SHM，从 `data_backup_*` 恢复 JSON。
- 代码层回滚：`git revert` 相关提交（遵循项目"永远用 revert，不用 reset --hard"规矩）。

## 7. 后续修订触发点

- 真遇到 SQLite 瓶颈（数据量/并发远超桌面单人） → 启动 ARCHITECTURE.md §2.3 规划的 Postgres 拐点。
- 需要跨进程/后台自动化（脱离桌面跑） → 抽自动化域为独立 worker（v1.x），届时 SQLite 文件锁模型需重新评估。
