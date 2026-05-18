# AI-Data-Engineer
End-to-End AI Data Platform - RAG + AWS(Azure) + Terraform + Docker

---

下面是把课程学习 + 项目搭建 + 简历改写合并成的两到三周冲刺清单。我按"周"拆,每个阶段标清楚做什么、对应课程哪个模块、对应项目哪一层、产出是什么。

## 三周冲刺总表

| 阶段 | 时间 | 课程任务 | 项目任务 | 对应项目层 | 产出 |
|---|---|---|---|---|---|
| **第 1 周:打地基** | Day 1-2 | 跳过课程,先动手 | 用 Xiaomi/Tencent 现成经验搭数据底座:造一份模拟支付/交易数据,建 ODS→DWD→DM→ADS 分层,加 DQC 校验 | 🔵 蓝色层(治理数据层) | 一个可信、有质量校验的数据库 |
| | Day 3 | **M4 evals 实战(精学+跑 notebook)** | 暂停项目,吃透 evals 方法论 | 🟠 琥珀色层 | evals 笔记 + 跑通的 notebook |
| | Day 4 | **M1 仅 task decomposition + evals 两节(精学)**;M1 其余 1.5x 速过 | 设计 agent 的任务拆解逻辑(把"为什么失败率涨"拆成步骤) | 🟣 紫色层(规划部分) | agent 任务拆解设计文档 |
| | Day 5 | 复盘本周课程 | 把数据层 + evals 框架接起来,写第一版质量门禁 | 🔵+🟠 | 数据层 + evals 门禁打通 |
| **第 2 周:搭 agent** | Day 6-7 | **M5 规划工作流(认真看视频)** | 搭 orchestrator agent 主框架(规划 + 调度) | 🟣 紫色层 | agent 能接收问题并规划步骤 |
| | Day 8 | **M2 Reflection(看+跑一次 notebook)** | 给 agent 加 reflection 循环(自我批判、重试) | 🟣 紫色层 | agent 能自我修正 |
| | Day 9 | **M3 Tool Use(2x 速扫,别花时间)** | 把 SQL 工具、分析工具、洞察工具包装成 agent 可调用 | 🟢 青色层(工具层) | 三个工具接入 agent |
| | Day 10 | 课程全部学完,无新模块 | 打通端到端:自然语言提问 → agent 规划 → 调工具 → 出报告 | 🟣+🟢+⚪ 全链路 | 第一个能跑的完整闭环 demo |
| **第 3 周:打磨+简历** | Day 11-12 | — | 把 evals 套在 agent 输出上,做 error analysis,建回归测试套件 | 🟠 琥珀色层 | 有评估体系的生产级版本 |
| | Day 13 | — | (可选加分)LLM 部分接 Google ADK / Gemini,命中 JD 的 Google 生态偏好 | 🟣 紫色层 | 命中 JD 偏好项 |
| | Day 14 | — | 整理项目 README、架构图、关键指标 | 全部 | 可展示的项目包 |
| | Day 15 | — | **改简历**(见下方两个 bullet 模板) | — | 更新后的简历 |

## 第 3 周要写进简历的两个 bullet(模板)

| 位置 | 改写方向 | 模板(你按真实数据填) |
|---|---|---|
| **mi 经验段那一行 agentic** | 从"我编排了一个 workflow"扩写成"我设计了一个带方法论的系统" | "Designed a production-grade agentic analytics system with task decomposition, reflection loops, tool orchestration, and an evals harness; automated insight generation over payment/transaction data, eliminating XX% of ad-hoc analytics requests." |
| **新增 "Selected Project" 板块** | 单独列这个 Payments Copilot,对着 JD 语言写 | "Payments Agentic Analytics Copilot — Built an AI-native analytics workflow: NL question → planning agent → SQL/analysis/insight tools → governed Iceberg data layer (ODS→DWD→DM→ADS) → evals-gated reporting. Tech: Python, SQL, LLM (ADK/Gemini), Iceberg." |

## 三个关键提醒

| 提醒 | 说明 |
|---|---|
| **别按 M1→M5 顺序学** | 学习顺序是 M4 → M1(两节)→ M5 → M2 → M3,把时间砸在 evals 上 |
| **第 1 周先动手再学课** | 蓝色层是你的强项,不依赖课程,先搭起来建立信心和地基 |
| **课程不拿证书,拿方法论** | 简历价值在项目本身,不在 certificate;面试能用 task decomposition / reflection / evals 这套语言对话才是真加分 |

如果时间只有两周,砍掉 Day 13(ADK 可选项)和 Day 11-12 压缩成一天,核心闭环和简历两个 bullet 必须保留。

