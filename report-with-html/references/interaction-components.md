# 交互组件货架

报告页需要某种交互形式时，**先来这里取货架组件原样嵌入，禁止每次现手搓**。原话（2026-07-20，货架建立的由来）："我希望这个交互形式都是沉淀下来的，可以复用的，有复利的一些组件。它代表了我们一致的 Agent 和我交互的我的喜好和风格。"

手搓的问题不是费 token，是**漂移**：每次重写的 lightbox 键位、关闭行为、计数样式都会有微差，要重新适应一遍——交互一致性本身就是产品质量。货架组件是校准过的契约，像 approved-examples 之于版式。

## 使用规则

1. **原样嵌入**：组件文件 `BEGIN…END` 之间整块拷进页面（通常在 `</body>` 前），交付后仍保持报告页单文件形态；每个组件所需 token / DOM 前置条件以它文件头的契约为准，不能把“单文件内嵌”误读成“零前置依赖”。**行为与键位禁改**（那是已校准的契约）；皮（颜色/尺寸）可按 register 微调。

   按组件文件头满足 DOM 前置条件。**拷完在真实浏览器激活主交互，记录实际打开的内容和定位**；组件存在、id 唯一或标签平衡不能代替这次激活检查。
2. **先查货架再动手**：需要的交互货架没有时，先看下方候选配方。没有适用配方时，按 [交互克制](design-principles.md#13-交互克制默认无脚本交互必须增加理解或可操作性) 判断该不该有交互，再实现。
3. **收录闸**（同 approved-examples 纪律）：只收**用过并认可**的交互（明确点头或无纠正地持续使用）。收录时写清：契约（触发/键位/关闭/边界）、来源页、认可日期。未认可的交互再炫也不进。

## 货架

下表只列已认可交互。候选配方单列在后，不能借用下表的认可状态。

| 组件 | 解决什么 | 契约要点 | 文件/片段 | 来源与认可 |
|---|---|---|---|---|
| **lightbox-gallery** 图片蒙层画廊 | 页内图片查验：放大、同组浏览、对比 | `img.zoom` 统一进入正常 Tab 顺序，可用 Enter/Space 打开原生 dialog；← → 循环切换；ESC / 背景 / 可见关闭钮关闭；关闭后焦点回触发图；长说明在窄屏内换行；`data-gallery` 分组；单图组隐藏箭头 | `assets/components/lightbox-gallery.html` | 素材拍摄手册排版决策页 · 2026-07-20 |
| **hash-expand** 折叠组锚点直达 | 折叠区可被 `URL#锚点` 直接引用 | 每个折叠组带 `id`；hash 命中即自动展开并滚到位；`hashchange` 同样生效 | 下方片段（行内即用） |  |
| **sticky-nav** 长页锚点导航 | 长报告页分节跳转 | 语义 `<nav>`＋可见焦点；`position:sticky`；hash 命中项 `aria-current="location"`；坏编码/死目标报错但不阻断有效链接；待拍板项金色高亮；导航自身窄屏横向滚动；不做滚动动画 | `assets/components/sticky-nav.html` | 多张认可页通用 |
| **citation-drawer** 嵌入源文档 + 条款抽屉 | 引用密集审阅页「每句话可核到原文」 | 唯一 `#s9` 内 tabs/panes 严格一一对应且不污染外部同名 class；引用是原生 button；modal 焦点受约束并可恢复；抽屉副本 remap 全部 id/IDREF 并清掉页面残留高亮；**子条引用优先定位子条锚点、退到母节时状态栏如实说明**；**外部法条/外部文件的编号标 `.nocite` 后 linkify 跳过**；长标题不撑宽窄屏；文档 tabs 支持方向键/Home/End；定位用 rect 差值 | `assets/components/citation-drawer.html`（BEGIN…END 整块嵌）+ `assets/regen-docs-template.py` 生成内容 DOM |  |
| **交互计算器** | 参数敏感的估值/分配（交互即论证） | 滑块 + preset + 实时联动数字流 + 高亮结果 + 解释句 | 暂无抽出组件 |  |

## 候选配方 · 尚未获通用认可

句末数字引用需要 hover/focus 轻量来源预览、点击原地查完整原件时，进入
[来源预览配方](citation-source-preview.md)。

### hash-expand canonical 片段

```html
<script>
(() => {
  const openHash = () => {
    if (!location.hash) return;
    let el;
    try {
      el = document.querySelector(location.hash);
    } catch (e) {
      /* 查询式 hash（#g=群名）不是合法 ID 选择器，querySelector 直接抛 SyntaxError。
         这类 hash 归页面自己的路由管，本片段让开——但留一行 warn，否则「深链不展开」
         看起来会像页面压根没有折叠逻辑。实测：'#g=abc' → SyntaxError。 */
      console.warn('[hash-expand] 跳过非 ID 形式的 hash：', location.hash);
      return;
    }
    if (!el) return;
    el.classList.add('open');            /* 折叠组的展开态 class，按页面命名调整 */
    el.scrollIntoView({ block: 'start' });
  };
  window.addEventListener('hashchange', openHash);
  openHash();
})();
</script>
```

## 与其他纪律的关系

- 上游交互准入与引用方式进入 [交互克制](design-principles.md#13-交互克制默认无脚本交互必须增加理解或可操作性)；本文件维护组件取用与收录。
- 工具页（浏览器/工作台）的重型交互组件（side+main、badge 状态流转、filter chips、导出回流）见 `approved-examples.md` 工具页组件表；成熟后同样按收录闸抽进本货架。
