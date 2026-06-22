# ✨ Rubedo · 凝华

> *红化是最后的蜕变。哲人石诞生，一滴即可点石成金。*

---

## 这是什么

**Rubedo**（凝华）是一人公司 AI 工具链的**副业 SOP 自动化平台**。

它不只是发布内容——而是让整个副业 SOP 自动运转：

```
副业 SOP 执行
    │
    ├── 接单阶段：AI 需求确认清单生成器 + RPA 抢单脚本
    ├── 执行阶段：时间记录工具（点几下记录完成）
    ├── 交付阶段：AI 内容生成器（过程录屏 → B站脚本）
    └── 经营阶段：数据分析工具 + 自动化任务调度
```

---

## 定位架构

Rubedo 采用**两层架构**：

### 🔧 共用工具层（任何 SOP 都能用）

| 工具名 | 功能 | 服务 SOP |
|--------|------|---------|
| **时间记录工具** | 做完一单点几下，自动计算耗时 | 所有计时类 SOP |
| **AI 对话工具箱** | 需求确认清单、报价计算、合同生成 | 所有接单类 SOP |
| **数据分析工具** | 自动汇总时间/利润/流量数据，生成周报 | 所有数据类 SOP |
| **自动化任务调度** | 定时提醒记录、定时跑数据分析 | 所有需要提醒的 SOP |

### 🎯 SOP 独特工具层（每个副业项目自己的专属工具包）

| SOP 工具包 | 包含工具 |
|--------------|----------|
| **酷家乐 SOP 工具包** | RPA 抢单脚本、2D 布局模板生成器、效果图渲染批量处理器 |
| **小红书 SOP 工具包** | AI 选品工具、AI 笔记生成器、RPA 自动发布工具 |
| **（未来其他 SOP）** | 每个新 SOP 一套工具包 |

---

## 与其他项目的关系

Rubedo 是 **OpusMagnum（巨作）** 五器工坊的其中一环：

| 项目 | Emoji | 功能 | 关系 |
|------|-------|------|------|
| **Citrinitas · 熔知** | 🏭 | 知识引擎（存储、检索、管理） | Rubedo 从 Citrinitas 检索知识来生成内容 |
| **Nigredo · 馏析** | ⚗️ | 视频→知识提炼（下载→字幕→AI 文档化） | Rubedo 的过程录屏可交给 Nigredo 处理 |
| **Albedo · 炼真** | 🔬 | 矛盾检测（跨源声明提取 + 可信度评分） | Rubedo 生成的内容可经 Albedo 验证可信度 |
| **Rubedo · 凝华** | ✨ | 副业 SOP 自动化平台 | 本仓库 |
| **OpusMagnum · 巨作** | ⚛️ | 总指挥部（健康检测 + GitHub 同步） | Rubedo 的状态被 OpusMagnum 监控 |

> 完整蓝图见 [OpusMagnum/BLUEPRINT.md](https://github.com/shiyao222333-afk/opus-magnum/blob/main/BLUEPRINT.md)

---

## 开发状态

| 阶段 | 状态 | 说明 |
|------|------|------|
| 规划 | 📋 规划中 | 工具平台架构设计完成，待开发 |
| MVP | 🔴 高优先级 | 时间记录工具 + AI 需求确认清单生成器先做起 |

### MVP 优先级（按你的副业 SOP）

| 优先级 | 工具 | 对应 MVP 阶段 | 说明 |
|--------|------|-------------|------|
| 🔴 P0 | **时间记录工具**（最小化版） | 酷家乐 MVP 第1周 | 第1周就要做时间审计，有个工具比手动填表快很多 |
| 🔴 P0 | **AI 需求确认清单生成器**（手动版） | 酷家乐 MVP 第1周 | 客户来了就能用，不需要写代码 |
| 🟡 P1 | RPA 抢单脚本 | 酷家乐 MVP 第5-6周 | 需要月20单，RPA 提醒能提高效率 |
| 🟡 P1 | AI 选品工具 + AI 笔记生成器 | 小红书 MVP 第1周 | 和小红书 MVP 同步开始 |
| 🟢 P2 | RPA 自动发布工具 | 小红书 MVP 第二刀通过后 | 第一刀手动发，验证流量后引入 |
| 🟢 P2 | 数据分析工具 + 自动化任务调度 | MVP 全部通过后 | 规模化阶段才需要 |

---

## 快速开始（等开发完成后）

### 1. 克隆项目

```bash
git clone https://github.com/shiyao222333-afk/rubedo.git
cd rubedo
```

### 2. 安装依赖

```bash
python -m venv venv
venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

### 3. 配置环境变量

复制 `.env.example` 为 `.env`，填写配置：

```bash
# .env
DEEPSEEK_API_KEY=sk-xxxxxxxxxx
QDRANT_URL=http://localhost:6333
```

### 4. 运行（等开发完成后）

```bash
python run.py
```

---

## 工具平台架构图

> 详细 Mermaid 架构图见 [docs/rubedo-architecture.md](docs/rubedo-architecture.md)

```
┌──────────────────────────────────────────────────┐
│            ✨ Rubedo · 凝华                     │
│          AI 辅助副业 SOP 自动化平台               │
└────────────────────┬─────────────────────────────┘
                         │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   ┌──────────┐  ┌──────────┐  ┌──────────┐
   │ 🔧 共用    │  │ 🎯 酷家乐  │  │ 🎯 小红书  │
   │ 工具层    │  │ SOP 工具 │  │ SOP 工具 │
   │          │  │ 包        │  │ 包        │
   └──────────┘  └──────────┘  └──────────┘
```

---

## 目录结构（等开发开始后）

```
rubedo/
├── README.md               # 本文件
├── docs/
│   └── rubedo-architecture.md   # 工具平台架构图（Mermaid）
├── shared/                  # 🔧 共用工具层
│   ├── time-tracker/      #   时间记录工具
│   ├── ai-dialogue/      #   AI 对话工具箱
│   ├── data-analyzer/    #   数据分析工具
│   └── scheduler/        #   自动化任务调度
├── sop-kujiale/           # 🎯 酷家乐 SOP 工具包
│   ├── rpa-order-monitor/
│   ├── layout-template/
│   └── batch-render/
├── sop-xiaohongshu/      # 🎯 小红书 SOP 工具包
│   ├── ai-product-selector/
│   ├── ai-note-generator/
│   └── rpa-auto-publish/
└── requirements.txt
```

---

## 参考资料

- [OpusMagnum 总指挥部](https://github.com/shiyao222333-afk/opus-magnum)
- [Citrinitas 知识引擎](https://github.com/shiyao222333-afk/citrinitas)
- [Nigredo 内容提炼](https://github.com/shiyao222333-afk/nigredo)
- [Albedo 矛盾检测](https://github.com/shiyao222333-afk/albedo)

---

## 许可证

MIT License —— 自由使用、修改、分发。

---

*Build in public. Think in private. Ship relentlessly.*
