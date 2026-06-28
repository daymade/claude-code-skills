# GLM API 配置指南

 transcript-fixer 通过智谱 GLM 的 **Anthropic 兼容端点**调用 AI 纠错能力。本节是 API 配置的唯一权威来源（SSOT）。

## 配置优先级

1. **配置文件**（推荐）：`~/.transcript-fixer/config.json`
2. **环境变量**（显式覆盖）：`GLM_API_KEY`、`ANTHROPIC_API_KEY`、`ANTHROPIC_BASE_URL`、`TRANSCRIPT_FIXER_CONFIG_DIR`
3. **代码默认值**

环境变量仅用于临时覆盖或 CI/容器场景，不要把密钥写进 shell profile。

## 推荐配置方式

### 1. 初始化配置目录

```bash
uv run scripts/fix_transcription.py --init
```

这会自动创建 `~/.transcript-fixer/` 目录并设置 `0o700` 权限。

### 2. 写入配置文件

编辑 `~/.transcript-fixer/config.json`：

```json
{
  "api": {
    "api_key": "your-glm-api-key",
    "base_url": null,
    "timeout": 60.0,
    "max_retries": 3
  }
}
```

配置文件的完整模板见 `references/installation_setup.md`。

### 3. 验证

```bash
uv run scripts/fix_transcription.py --validate
```

## 环境变量覆盖（可选）

```bash
# 临时覆盖 API 密钥
export GLM_API_KEY="your-glm-api-key"

# 或使用 Anthropic 兼容密钥名
export ANTHROPIC_API_KEY="your-glm-api-key"

# 自定义端点（高级）
export ANTHROPIC_BASE_URL="https://open.bigmodel.cn/api/anthropic"

# 自定义配置目录
export TRANSCRIPT_FIXER_CONFIG_DIR="/path/to/config"
```

## 支持的模型

代码默认值：

| 模型名称 | 说明 | 用途 |
|---------|------|------|
| GLM-5.2 | 主力模型 | 默认使用，精度最高 |
| GLM-5-turbo | 快速模型 | 主模型失败时回落，速度更快 |

模型名称通过 `ai_processor.py` / `ai_processor_async.py` 的构造函数传入；修改配置文件中不会自动改变模型，需要改代码或调用处。

## API 认证

GLM Anthropic 兼容端点使用 `x-api-key` 头，而不是 `Authorization: Bearer`：

```python
headers = {
    "anthropic-version": "2023-06-01",
    "x-api-key": api_key,
    "content-type": "application/json"
}
```

**关键点：**
- 使用 `x-api-key` 头
- 不要使用 `Authorization: Bearer`

## API 调用示例

```python
import httpx

def call_glm_api(prompt: str, api_key: str) -> str:
    url = "https://open.bigmodel.cn/api/anthropic/v1/messages"
    headers = {
        "anthropic-version": "2023-06-01",
        "x-api-key": api_key,
        "content-type": "application/json"
    }

    data = {
        "model": "GLM-5.2",
        "max_tokens": 8000,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}]
    }

    with httpx.Client(timeout=60.0, http2=False) as client:
        response = client.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()["content"][0]["text"]
```

生产代码应使用 `scripts/core/ai_utils.py` 中的 `build_correction_prompt()` 和 `parse_anthropic_response()`，而不是手写解析。

## 获取 API 密钥

1. 访问 https://open.bigmodel.cn/
2. 注册/登录账号
3. 进入 API 管理页面
4. 创建新的 API 密钥
5. 复制密钥到 `~/.transcript-fixer/config.json` 的 `api.api_key` 字段

## 费用

参考智谱 AI 官方定价：
- GLM-5.2：按 token 计费
- GLM-5-turbo：更便宜的选择

## 故障排查

### 401/403 错误
- 检查 API 密钥是否正确
- 确认使用 `x-api-key` 头，而不是 `Authorization: Bearer`
- 确认密钥未过期且余额充足

### 超时错误
- 增加 `timeout` 参数
- 考虑使用 GLM-5-turbo 快速模型

### 配置未生效
- 确认配置文件路径：`~/.transcript-fixer/config.json`
- 确认 JSON 格式有效
- 运行 `--validate` 查看加载的配置目录

## 安全提示

- 不要把 `api_key` 提交到 Git
- 配置文件权限由脚本自动设为 `0o600`
- 不要在 shell profile 或 `.bashrc` 中持久化 `GLM_API_KEY`
