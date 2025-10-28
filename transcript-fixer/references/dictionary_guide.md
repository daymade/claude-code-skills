# 纠错词典配置指南

## 词典结构

纠错词典位于 `fix_transcription.py` 中,包含两部分:

### 1. 上下文规则 (CONTEXT_RULES)

用于需要结合上下文判断的替换:

```python
CONTEXT_RULES = [
    {
        "pattern": r"正则表达式",
        "replacement": "替换文本",
        "description": "规则说明"
    }
]
```

**示例:**
```python
{
    "pattern": r"近距离的去看",
    "replacement": "近距离地去看",
    "description": "修正'的'为'地'"
}
```

### 2. 通用词典 (CORRECTIONS_DICT)

用于直接字符串替换:

```python
CORRECTIONS_DICT = {
    "错误词汇": "正确词汇",
}
```

**示例:**
```python
{
    "巨升智能": "具身智能",
    "奇迹创坛": "奇绩创坛",
    "矩阵公司": "初创公司",
}
```

## 添加自定义规则

### 步骤1: 识别错误模式

从修复报告中识别重复出现的错误。

### 步骤2: 选择规则类型

- **简单替换** → 使用 CORRECTIONS_DICT
- **需要上下文** → 使用 CONTEXT_RULES

### 步骤3: 添加到词典

编辑 `scripts/fix_transcription.py`:

```python
CORRECTIONS_DICT = {
    # 现有规则...
    "你的错误": "正确词汇",  # 添加新规则
}
```

### 步骤4: 测试

运行修复脚本测试新规则。

## 常见错误类型

### 同音字错误
```python
"股价": "框架",
"三观": "三关",
```

### 专业术语
```python
"巨升智能": "具身智能",
"近距离": "具身",  # 某些上下文中
```

### 公司名称
```python
"奇迹创坛": "奇绩创坛",
```

## 优先级

1. 先应用 CONTEXT_RULES (精确匹配)
2. 再应用 CORRECTIONS_DICT (全局替换)
