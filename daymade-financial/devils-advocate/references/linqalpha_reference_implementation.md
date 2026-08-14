# 被复刻产品的参考实现：LinqAlpha Devil's Advocate

本 skill 复刻并扩展的对象。以下内容全部来自公开一手信源，逐字引用处保留英文原文。
核心信源：AWS Machine Learning Blog 官方客座文章（LinqAlpha 员工撰写，2026-02-11）：
<https://aws.amazon.com/blogs/machine-learning/how-linqalpha-assesses-investment-theses-using-devils-advocate-on-amazon-bedrock/>

## 产品定位（原文）

> "Devil's Advocate is an AI research agent purpose-built to help investors systematically
> pressure-test their investment theses using their own trusted sources at 5–10 times the
> speed of traditional review."

官方四步流程：Define your thesis → Upload reference documents → AI-driven thesis analysis →
Structured critique and counterarguments。

假设分类法的官方定义出处（第三步）：

> "Devil's Advocate deconstructs the thesis into explicit assertions and implicit assumptions.
> It scans the evidence base to find content that challenges or contradicts those assumptions."

## 生产环境 Prompt 模板（AWS 博客逐字公开，一字未改）

```
You are an institutional research assistant designed to act as a Devil's Advocate.
Your task is to challenge investment theses with structured, evidence-linked counterarguments.
Always use provided documents (expert calls, broker reports, 10-Ks, transcripts).
If no relevant evidence exists, clearly state "no counter-evidence found".
Thesis: {user_thesis}
Step 1. Identify Assumptions
- Extract all explicit assumptions (stated directly in the thesis).
- Extract implicit assumptions (unstated but required for the thesis to hold).
- Label each assumption with an ID (A1, A2, A3...).
Step 2. Retrieve and Test
- For each assumption, issue retrieval queries against uploaded sources (OpenSearch index, RDS, S3).
- Prioritize authoritative sources in this order:
   1. SEC filings (10-K, 10-Q, 8-K)
   2. Expert call transcripts
   3. Broker/analyst reports
- Identify passages that directly weaken, contradict, or raise uncertainty about the assumption.
Step 3. Structured Output
For each assumption, output in JSON with the following fields:
{
  "assumption_id": "A1",
  "assumption": "<concise restatement of assumption>",
  "counter_argument": "<evidence-backed critique, phrased in analyst style>",
  "citation": {
       "doc_type": "10-K",
       "doc_id": "ABCD_10K_2023",
       "page": "47",
       "excerpt": "Management noted that monetization of Product features remains exploratory, with no committed pricing model."
  },
  "risk_flag": "<High | Medium | Low> (relative importance of this counterpoint to the thesis)"
}
Step 4. Output Formatting
- Return all assumptions and critiques as a JSON array.
- Ensure every counter_argument has at least one citation.
- If no evidence found, set counter_argument = "No counter-evidence found in provided sources" and citation = null.
- Keep tone factual and neutral (avoid speculation).
- Avoid duplication of evidence across assumptions unless highly relevant.
Step 5. Analyst Voice Calibration
- Write counter_arguments in the style of an institutional equity research analyst.
- Be concise (2–3 sentences per counter_argument).
- Focus on material risks to the investment case (competitive dynamics, regulation, margin compression, technology adoption).
```

## 架构要点（对本地复刻有直接意义的）

- **三个专职 agent 迭代式协同**（非线性流水线）：Parsing agent（文档结构化）→ Retrieval agent
  （逐假设检索反证）→ Synthesis agent（生成结构化反驳，可触发新一轮检索）。原文强调
  "This iterative back-and-forth is what makes the system agentic rather than a static workflow."
- **双层输出**：博客里的 JSON schema 是后端中间表示；真实产品界面渲染成「分主题小标题 +
  行内引用编号 + 右侧参考文献卡片（含逐字摘录）」的叙事层。复刻时同样分两层：
  结构化条目供审计，人读层供决策。
- **专家访谈是设计时的核心输入类型**：产品界面副标题为 "Upload expert interviews to challenge
  your investment thesis with evidence-based reasoning"；演示语料的文件名带结构化元数据
  （`tegus_{公司代号}_{编号}_{受访者头衔}-at-{公司描述}.pdf`）——证据文件名/元数据里带上「谁说的、什么身份、哪家公司」
  能显著提升 citation 的可信度呈现。
- **准确性设计哲学**（LinqAlpha 官方博客另文）："our technology employs both probabilistic and
  deterministic models in tandem to leverage their strengths"——发散交给 LLM，数值与引用完整性交给确定性检查。

## 已知的公开评估缺口（第三方 ZenML LLMOps 案例库的批判性评估）

- "5-10x 提速"缺乏基线定义；反方论据质量、引用准确率、检索精确率/召回率均未披露；
  没有证据表明系统找到的是「新颖盲点」还是「检索已存在的反方信息」。
- 本 skill 因此补了三层原厂没有的东西：基础比率外部视角（Mauboussin）、可监测信号标
  （RAND ABP signpost）、以及「材料构成偏性」的覆盖面声明。

## 采用与效果口径（引用时注意标注性质）

- "over 170 hedge funds and asset managers worldwide"（AWS 博客口径，2026-02）；
  同年 7 月 A 轮新闻稿口径为 "70+ financial institutions"——两个数字并存，官方未解释差异。
- 客户案例（Third Square Capital，官网案例页）：早期研究提速 5-6 倍；其基金 13 个月净回报
  52.5% vs 标普 500 的 16%——案例页的相关性叙事，非因果声明。
- Tiger Cub 系基金经理证言（AWS 博客）："This helped me objectively gut-check my bullish
  thesis ahead of IC. Instead of wasting hours stuck in my own confirmation bias, I quickly
  surfaced credible pushbacks, making my pitch tighter and more balanced."
