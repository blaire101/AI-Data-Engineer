**对，你发现了一个关键问题。**

你现在的架构图少了一条线。

实际上你的项目**不是只有 NLP**，而是**两条 Extraction Pipeline 最后汇合（Merge）**。

也就是说：

> **Textract 之后产生了两种不同的数据。**

---

# 第一条：Financial Values（数字）

例如：

```
Revenue = 638B

Net Income = 59B

Operating Income = 89B
```

这些来自：

```
Income Statement

Balance Sheet

Cash Flow
```

解析出来后就是

```
fields.json
```

例如

```
Revenue

Value

Currency

Page
```

---

# 第二条：Supporting Evidence（句子）

例如：

Revenue

↓

OpenSearch

↓

Top100

↓

SageMaker

↓

Top3

↓

model_out.json

例如：

Revenue increased 11%...

Net sales grew...

Total revenue...

```

---

最后真正生成报告的时候

不是

```

Top3

```

直接输出。

而是

```

fields.json

*

model_out.json

↓

Merge

↓

Report

```

所以真正的数据流应该是：

```

```
                 Upload PDF
                      │
                API Gateway
                      │
                  Lambda
                      │
                      ▼
                  S3 Raw PDF
                      │
                      ▼
              Amazon Textract
                      │
      ┌───────────────┴────────────────┐
      │                                │
      ▼                                ▼
```

Financial Table Parser           Sentence Extraction
(Revenue, Assets...)             (~3,000 Sentences)
│                                │
▼                                ▼
fields.json                   OpenSearch Index
│
▼
Candidate Retrieval
│
▼
SageMaker Endpoint
│
▼
Top-3 Evidence
model_out.json
│                                │
└───────────────┬────────────────┘
▼
Report Assembler
│
▼
Executive Summary + Detailed Report

```

---

## 我觉得这里还能提升一点

其实你的项目有两个不同的 Extraction。

### Pipeline A

Extract

**Financial Values**

例如：

```

Revenue

EPS

Net Income

Cash

Assets

Liabilities

```

这是

**Structured Extraction**

---

### Pipeline B

Extract

**Narrative Evidence**

例如：

```

Revenue increased...

Operating income decreased...

Cash flow improved...

```

这是

**Unstructured Extraction**

---

最后

```

Structured Data

*

Unstructured Evidence

↓

Report

```

这个设计就很漂亮。

---

# 所以你的第三条 Resume 我建议改一下

现在你写的是

> Generated structured financial reports by integrating extracted financial metrics with supporting evidence...

其实有一点没体现出来：

**financial metrics 是从表格里来的。**

所以我建议：

> Generated structured financial reports by combining extracted financial values from financial statements with Top-3 supporting evidence, enabling analysts to validate reported metrics efficiently.

这样面试官马上知道：

```

Financial Statements

↓

Revenue = 638B

```

和

```

Narrative Text

↓

Top3 Evidence

```

最后Merge。

这是整个项目最大的亮点。

---

## 我认为，这也是你项目区别于普通 OCR/NLP 项目的地方

你的系统不是简单做 OCR，而是**同时处理了两类信息**：

1. **Structured financial values**：从财务报表（利润表、资产负债表、现金流量表）提取数值，形成结构化指标。
2. **Unstructured supporting evidence**：从正文中检索并筛选能够解释这些指标变化的关键句子。

最终通过 **Report Assembler** 将两者融合，输出既包含**数值**又包含**证据**的分析报告。这一点在面试时非常有说服力，因为它体现了你不仅做了文档解析，还完成了**数据融合（Data Fusion）**，这是一个比单纯 OCR 或文本分类更完整、更接近企业级文档智能平台的设计。
```

