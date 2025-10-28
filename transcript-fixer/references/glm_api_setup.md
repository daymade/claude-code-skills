# GLM API 配置指南

## API配置

### 设置环境变量

在运行脚本前,设置GLM API密钥环境变量:

```bash
# Linux/macOS
export GLM_API_KEY="your-api-key-here"

# Windows (PowerShell)
$env:GLM_API_KEY="your-api-key-here"

# Windows (CMD)
set GLM_API_KEY=your-api-key-here
```

**永久设置** (推荐):

```bash
# Linux/macOS: 添加到 ~/.bashrc 或 ~/.zshrc
echo 'export GLM_API_KEY="your-api-key-here"' >> ~/.bashrc
source ~/.bashrc

# Windows: 在系统环境变量中设置
```

### 脚本配置

脚本会自动从环境变量读取API密钥:

```python
# 脚本会检查环境变量
if "GLM_API_KEY" not in os.environ:
    raise ValueError("请设置 GLM_API_KEY 环境变量")

os.environ["ANTHROPIC_BASE_URL"] = "https://open.bigmodel.cn/api/anthropic"
os.environ["ANTHROPIC_API_KEY"] = os.environ["GLM_API_KEY"]

# 模型配置
GLM_MODEL = "GLM-4.6"  # 主力模型
GLM_MODEL_FAST = "GLM-4.5-Air"  # 快速模型(备用)
```

## 支持的模型

| 模型名称 | 说明 | 用途 |
|---------|------|------|
| GLM-4.6 | 最强模型 | 默认使用,精度最高 |
| GLM-4.5-Air | 快速模型 | 备用,速度更快 |

**注意**: 模型名称大小写不敏感。

## API认证

智谱GLM使用Anthropic兼容API:

```python
headers = {
    "anthropic-version": "2023-06-01",
    "Authorization": f"Bearer {api_key}",
    "content-type": "application/json"
}
```

**关键点:**
- 使用 `Authorization: Bearer` 头
- 不要使用 `x-api-key` 头

## API调用示例

```python
def call_glm_api(prompt: str) -> str:
    url = "https://open.bigmodel.cn/api/anthropic/v1/messages"
    headers = {
        "anthropic-version": "2023-06-01",
        "Authorization": f"Bearer {os.environ.get('ANTHROPIC_API_KEY')}",
        "content-type": "application/json"
    }

    data = {
        "model": "GLM-4.6",
        "max_tokens": 8000,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}]
    }

    response = httpx.post(url, headers=headers, json=data, timeout=60.0)
    return response.json()["content"][0]["text"]
```

## 获取API密钥

1. 访问 https://open.bigmodel.cn/
2. 注册/登录账号
3. 进入API管理页面
4. 创建新的API密钥
5. 复制密钥到配置中

## 费用

参考智谱AI官方定价:
- GLM-4.6: 按token计费
- GLM-4.5-Air: 更便宜的选择

## 故障排查

### 401错误
- 检查API密钥是否正确
- 确认使用 `Authorization: Bearer` 头

### 超时错误
- 增加timeout参数
- 考虑使用GLM-4.5-Air快速模型
