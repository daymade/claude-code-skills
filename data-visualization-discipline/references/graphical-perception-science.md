# 地基 · 图形感知是实证科学，不是审美偏好

这份文件回答一个问题：**凭什么说"这张图该那样画"不是品味之争。**

可视化有四十年实证研究。下面每条都带出处——skill 里的判据都从这里推出来，改判据前先回来看它站在哪条实证结论上。**凡标「未核实」的，只保留原则、不要在交付物里引用它的出处**（错误的权威引用比没有引用更糟）。

---

## 1. Cleveland & McGill 图形感知精度排序

**出处**：Cleveland, W. S. & McGill, R. (1984). "Graphical Perception: Theory, Experimentation, and Application to the Development of Graphical Methods." *Journal of the American Statistical Association*, 79(387), 531–554.

人判断"量"的准确度，由高到低：

| 级 | 感知任务 |
|---|---|
| 1 | 位置 · 共同基线（position along a common scale） |
| 2 | 位置 · 非对齐基线（positions along nonaligned scales） |
| 3 | **长度 / 方向 / 角度（三者并列）** |
| 4 | 面积 |
| 5 | 体积 / 曲率（并列） |
| 6 | 明暗 / 色饱和度（并列） |

**两个常被写错的细节**：

- **第 3 级是并列的**。"长度优于角度"是流传的误传——原文把 length、direction、angle 放在同一级。所以"条形比饼图好"的依据不是"长度 > 角度"，而是下面 Exp 2 的直接实验结果。
- **color hue 不在这个排序里**。1984 原文明确把它排除，理由是 hue 与定量信息"没有无歧义的对应关系"。"hue 排最后"的说法出自 Cleveland 后来的 *The Elements of Graphing Data*（把 hue / saturation / density 并列置于末级）。引用时说清是哪个版本。

**两个直接支撑判据的实验**：
- **Exp 1（divided bar chart）**：长度判断的平均误差显著大于位置判断 → **堆叠条内部各段的长度比较，天生差于并列条的位置比较**。这是"堆叠图不适合比较各系列"的感知学根据（业务侧根据见 `chart-selection-and-statistics.md` §堆叠）。
- **Exp 2（pie vs bar）**：角度判断误差显著大于位置判断 → 需要比较时用条形图。

**不是古董**：Heer, J. & Bostock, M. (2010). "Crowdsourcing Graphical Perception: Using Mechanical Turk to Assess Visualization Design." *CHI 2010* — 在现代屏幕上用众包复现，结果与 1984 一致，并扩展了矩形面积（treemap）实验。

**可操作规则**
- 要读者**准确读出或比较**量 → 编成位置或长度（条 / 轴 / 点位置）。
- 气泡大小（面积，第 4 级）只适合传达"数量级差异"，不适合精确比较。
- 热图色深（第 6 级）适合看模式，**不适合读值**——要读值就补数字标注。
- 写成文字根本不在这条通道上——那是"读"不是"看"。

**边界（重要，别把这条用过头）**：这个排序衡量的是「**读取或比较数值**」的精度，不是所有可视化任务。看整体分布形态、密度、聚类、异常时，颜色和面积（热图 / 密度图）反而高效。排序否定的是"用热图读精确值"，不是"热图永远错"。

---

## 2. Bertin 视觉变量：哪些通道能编码"量"

**出处**：Jacques Bertin (1967). *Sémiologie graphique: Les diagrammes, les réseaux, les cartes.*

七个视觉变量：position、size、shape、value（明度）、color hue、orientation、texture。Bertin 给每个变量标注四种感知性质：associative / selective / ordered / quantitative。

**两条承重结论**：
- **只有 size 和平面 position 能准确传达定量信息。**
- **表达"序"时，value（明度）远优于 color hue。**

**可操作规则**
- **颜色（hue）不能编码量。** 想用"颜色深浅代表大小"时，用的必须是 value / 明度阶（顺序色板），且只承诺读者看出"序"，不承诺读出"差几倍"。
- 三类映射不许互换：分类变量 → hue；有序变量 → value 梯度；定量变量 → position / size。
- 用多色相渐变（rainbow）编码连续量是双重错误：hue 无序 + 明度不单调。（rainbow colormap 有专门批评文献，本次未检索，此处只作为上面两条的推论。）

**与 §1 的互补/张力**：Bertin 说 size 是 quantitative-capable，Cleveland 把 area 排在第 4 级——两者不矛盾但要合读：size **可以**编码量，但**精度不高**，面积感知有系统性低估。需要精确比较时仍回到位置 / 长度。

**Munzner 的一句话总结**（有效性原则）：**变量的重要性要匹配通道的显著性**——最重要的量用最高效通道（位置 / 长度），次要的才用颜色；**一个通道只编一件事**（别用颜色同时表大小又表类别）。

---

## 3. Tufte：data-ink / chartjunk / lie factor / small multiples

**出处**：Edward Tufte (1983). *The Visual Display of Quantitative Information*（前三条）；*Envisioning Information* (1990)（small multiples）。

### 3a. Data-ink ratio
data-ink = 图形中不可擦除的、随数据变化的非冗余墨水。ratio = data-ink / 总墨水，要最大化。

**可操作规则**：每个视觉元素过一问——**擦掉它会丢数据信息吗？** 不会就擦（网格线减淡或删、外框删、背景色删、3D 效果删、与直接标注重复的图例删）。

### 3b. Chartjunk
不告诉读者任何新东西的墨水：装饰性 3D、纹理填充、无功能插图、彩色边框、大圆角。

**争议（不粉饰）**：Tufte 的极简主义在从业者社区并未被全盘接受（见 arXiv 2009.02634, "Data Visualization Practitioners' Perspectives on Chartjunk"）。也有实验发现装饰图形可能提升长期记忆【未核实——来自记忆，引用前需查证】。
**落地建议**：**分场景分档**——分析 / 监控图从严执行 Tufte；传播 / 叙事图允许有度装饰。但 lie factor 红线两边都不许破。

### 3c. Lie factor
`lie factor = 图形显示的效应大小 ÷ 数据中真实的效应大小`，应落在 **0.95–1.05**。>1 夸大，<1 低估。

**可操作规则**
- **条形图 y 轴必须从 0 开始**——长度编码时截断轴直接推高 lie factor。
- 面积编码时数值翻倍 → **面积**翻倍，不是边长翻倍（边长翻倍 = 面积 4 倍 = lie factor 2）。
- 推论（本 skill 自己的延伸）：任何"长度 = k·值 + 常数"的加性底都破坏比例感，见 SKILL.md 的比例编码判据。
- 推论（本 skill 自己的工程延伸）：lie factor 的「图形显示效应」要看**最终 painted geometry**，不是源码里的 `width`。CSS box model 里的 border 会扩张可见 box；SVG 的 round / square line cap 会越过路径端点继续绘制。因此固定 `min-width`、border、cap、marker 或伪元素即使不改数据公式，也能系统性放大小值。定量 mark 要把这些可见部分纳入实测，或把固定大小的 presence indicator 与长度编码彻底分开。**0.95–1.05 是整幅图呈现效应的诊断区间，不是实现容差**：固定 `+2px` 可能让某一组大值碰巧落在区间内，却仍以同一个加性底把小值放大数倍，违反线性长度编码。

**边界**：**线图的轴不必从 0 开始**——线编码的是位置和斜率而非长度，强制 0 基线会压平有意义的变化。这是社区通行共识【原文出处未核实】，但与 §1 的编码通道分析自洽：零基线约束绑定的是**长度**编码，不是位置编码。

### 3d. Small multiples
同一设计重复多次、每格显示不同数据切片，**所有格共用同一尺度和坐标**。Tufte 的机制解释：设计的恒定让读者的注意力集中在**数据的变化**上，而不是图形框架的变化上。

**可操作规则**
- 系列超过 4–5 条挤在一张线图里 → 拆 small multiples。
- 拆完**所有面板必须同 x/y 范围、同轴、同色映射**——任何一格私改尺度就毁掉整个设计的可比性。
- 这条也是 §5 跨图身份一致性的理论根据：色彩身份漂移 = "设计在变"，直接破坏该机制。

---

## 4. Preattentive attributes（前注意加工）

长度 / 位置 / 色相 / 大小 被视觉皮层在 **<200ms** 内自动处理。**这就是"能不能一眼读出"的科学定义**——文字是串行逐字读，不在这条通道上。

**可操作推论**：验收测试 = **遮住所有文字，光看形状还能读出主要洞察吗？** 读不出 = 还是"文字堆彩色框"，不是可视化。（这是 preattentive 原理的可执行版，见 SKILL.md 遮字自测。）

---

## 5. 跨图身份一致性：同实体同色，不同字段不同色

**出处**：Qu, Z. & Hullman, J. (2018). "Keeping Multiple Views Consistent: Constraints, Validations, and Exceptions in Visualization Authoring." *IEEE TVCG (Proc. InfoVis 2018)*.

约束是**双向**的：
- 相同的定量 / 定类字段应当用**相同的色标**；
- **不同的定量字段应当用不同的色相**；不同定类字段的色板**不应重叠**。

第二条常被忽略：不只是"同一个东西别换色"，还有"**别让两个无关字段共用一套色**"——否则读者会把它们误当同一个。

**最常见的违反方式**：让绘图库按**出场顺序**自动配色。同一实体在图 1 排第 2、在图 3 排第 5，默认配色必然错乱。

**可操作规则**
- 做多图报告**先建"实体 → 颜色"映射表**，全文引用，禁止依赖库的自动配色。
- 语义色（好/坏、涨/跌、达标/未达标）全报告方向一致。
- small multiples 各格同实体**同色同位**。

---

## 6. Stephen Few：dashboard 单屏原则

**出处**：Stephen Few (2006). *Information Dashboard Design*, O'Reilly.

**定义**：dashboard 是"为达成一个或多个目标所需的**最重要**信息的视觉显示，整合安排在**单一屏幕**内，使信息能被**一眼**监控"。

**单屏的理由不是美观，是短期记忆容量限制**——滚动或切屏迫使读者在记忆里搬运数字。

**可操作规则**：监控型 dashboard 不滚动、不翻页；信息按意义分组；每个图为"短暂一瞥"设计而非精读。

**张力**：这条铁律出自 2006 年 BI 语境，与现代交互 dashboard 的 drill-down / 渐进披露有张力【未核实——来自记忆】。**落地表述**：监控视图单屏，探索路径可分层。

---

## 7. 理论之间真实存在的冲突（不粉饰）

写判据时必须知道这些张力在哪，否则会写出**误杀健康输入**的规则——而一条会误杀的规则，代价是整道防线被绕过（见 SKILL.md 判据的措辞纪律）。

| 冲突 | 两方立场 | 本 skill 的落点 |
|---|---|---|
| **Tufte 极简 vs 记忆/传播** | data-ink 最大化 vs 装饰可能助记 | 分场景分档：分析/监控从严，传播/叙事允许有度装饰；lie factor 两边都是红线 |
| **饼图之战** | Few *Save the Pies for Dessert* (2007) 主张几乎永远用条形 vs 反方主张 2–3 类时饼图直觉性好 | Cleveland-McGill 只证明**角度读值**弱于位置，**没有**证明"部分占整体的 gist"任务上饼图更差。落点：**类别 ≤3 且只需传达"大约几成" → 饼图可接受；需要比较或类别多 → 必须条形** |
| **双轴：绝对禁止 vs 条件允许** | Few / Wickham 近乎绝对禁止 vs Springer 2022 有整篇辩护 | 冲突实质是两种情况被混为一谈：**混量纲双轴（收入 vs 增长率）不可辩护；同量异单位双轴（°C/°F）数学等价无害**。判据必须拆开写，不要一刀切 |
| **堆叠图：从严 vs 条件使用** | Few 从严 vs 实务派认为"少时点 + 强调首尾两层"时可用 | 公约数本身就是判据：**堆叠只回答 part-to-whole，且可精读的只有贴基线的那层** |
| **Cleveland 排序的适用范围** | 读值精度排序 vs 找模式/看分布任务 | 判据表述必须带前提：「**当任务是读取或比较数值时**」——否则会被误用成"热图永远错" |
| **单屏 vs 分层披露** | Few 2006 BI 语境 vs 现代交互 dashboard | 监控视图单屏，探索路径可分层 |

---

## 8. 动态图形感知：转场也必须保持数据语义

**出处**：Heer, J. & Robertson, G. G. (2007). "Animated Transitions in Statistical Data Graphics." *IEEE Transactions on Visualization and Computer Graphics*, 13(6), 1240–1247.

这项研究把图形感知从静态 mark 扩展到转场，并给出几条与本 skill 直接相关的结论：

- **中间帧也应尽量是有效的数据图形**，否则观众会对数据作出无依据的归因；
- **语义与图形语法要持续对应**：同一个数据对象跨帧保持身份，不同操作不要复用一套含糊的动作；
- **共同运动会被知觉为同一组操作**（common fate），因此属于同一事件的 mark 应同步变化；
- 简单转场与必要的简单 staging 有助于追踪，过度拆成多段反而增加误差；动画只该长到足够读懂，不该拖长；
- 跨时间尽量保持共同尺度；必须缩放时保留地标并把缩放与数值变化明确分开。

**本 skill 的工程延伸（不是论文逐字处方）**：

1. 把一次定量变化建成正文定义的同一个原子事件；mark、直接标注、累计值和步进锚点都从它派生。字段与连续性断言只在 SKILL.md 定义，这里不复制一份会漂移的 schema。
2. **同一事件用共同时间进度**：动作标签、区间增长、增量与累计值要么一起补间，要么一起在边界帧切换。让 CSS transition、计数器与叙事字幕各跑一只钟，会制造论文所说的 unwarranted attribution。
3. **标签与 mark 直接绑定**：动作文字放在对应区间上，或用括号 / leader line 指向它；标题和旁栏不承担唯一映射。观众不应在两个空间区域间靠工作记忆猜配对。
4. **逐步播放保留因果帧**：开始、必要的中间态、稳定态都必须可到达。若一次按键从原因前直接跳到总量后，动画即使自动播放时顺畅，也不能作为可讲解的证据。

**边界**：简单 staging 不等于把一个原子事件拆成彼此错拍的字幕、几何和数字。可以把「重缩放」与「值变化」分阶段；不能把「这次值变化是什么」与「这次值变化的几何」分开。

---

## 主要来源

- Cleveland & McGill 1984 — https://www.tandfonline.com/doi/abs/10.1080/01621459.1984.10478080 ；排序细节 https://vizdata.org/slides/24/24-graphical-perception.html
- Heer & Bostock 2010 (CHI) — https://dblp.org/rec/conf/chi/HeerB10.html
- Bertin 视觉变量 — https://www.axismaps.com/guide/visual-variables
- Tufte data-ink — https://infovis-wiki.net/wiki/Data-Ink_Ratio ；lie factor — https://infovis-wiki.net/wiki/Lie_Factor
- Small multiples — https://en.wikipedia.org/wiki/Small_multiple
- Few *Information Dashboard Design* 书评 — https://www.uxmatters.com/mt/archives/2007/04/book-review-information-dashboard-design.php
- Qu & Hullman 2018 跨视图一致性 — https://idl.uw.edu/papers/consistency
- Chartjunk 争议 — https://arxiv.org/pdf/2009.02634
- 饼图之战 — https://www.perceptualedge.com/articles/visual_business_intelligence/save_the_pies_for_dessert.pdf
- Heer & Robertson 2007 动态转场 — https://idl.cs.washington.edu/files/2007-AnimatedTransitions-InfoVis.pdf
- W3C CSS Box Model Level 3 — https://www.w3.org/TR/css-box-3/
- W3C SVG 2 Painting（stroke line caps）— https://www.w3.org/TR/SVG2/painting.html#LineCaps
