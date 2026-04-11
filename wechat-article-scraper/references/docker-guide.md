# Docker 部署指南

## 快速开始

### 1. 构建镜像

```bash
cd wechat-article-scraper
docker build -t wechat-article-scraper:latest .
```

### 2. 单篇文章抓取

```bash
# 抓取单篇文章
docker run --rm \
  -v $(pwd)/output:/app/output \
  -v $(pwd)/cache:/app/cache \
  wechat-article-scraper:latest \
  "https://mp.weixin.qq.com/s/xxxxx" \
  -o /app/output \
  -s adaptive
```

### 3. 批量抓取

```bash
# 创建 URL 列表文件
cat > urls.txt << 'EOF'
https://mp.weixin.qq.com/s/article1
https://mp.weixin.qq.com/s/article2
https://mp.weixin.qq.com/s/article3
EOF

# 运行批量抓取
docker run --rm \
  -v $(pwd)/output:/app/output \
  -v $(pwd)/cache:/app/cache \
  -v $(pwd)/urls.txt:/app/urls.txt:ro \
  wechat-article-scraper:latest \
  --batch /app/urls.txt \
  -o /app/output \
  --delay 5
```

## 使用 Docker Compose

### 基本用法

```bash
# 显示帮助
docker-compose run --rm scraper

# 抓取单篇文章
docker-compose run --rm scraper \
  "https://mp.weixin.qq.com/s/xxxxx" \
  -o /app/output

# 批量抓取
docker-compose run --rm scraper \
  --batch /app/urls.txt \
  -o /app/output \
  --delay 5
```

### 定时抓取（Scheduler）

```bash
# 启动定时抓取服务（每小时运行一次）
docker-compose --profile scheduler up -d scheduler

# 查看日志
docker-compose logs -f scheduler

# 停止服务
docker-compose --profile scheduler down
```

## 高级配置

### 使用代理

```bash
# 通过环境变量设置代理
docker run --rm \
  -e HTTP_PROXY=http://proxy:1082 \
  -e HTTPS_PROXY=http://proxy:1082 \
  -v $(pwd)/output:/app/output \
  wechat-article-scraper:latest \
  "https://mp.weixin.qq.com/s/xxxxx" \
  --proxy http://proxy:1082
```

### 持久化缓存

缓存数据默认存储在 `/app/cache`，建议挂载卷以持久化：

```bash
-v $(pwd)/cache:/app/cache
```

### 自定义缓存过期时间

```bash
-e WECHAT_CACHE_TTL=7  # 7天
```

## 故障排查

### 检查容器状态

```bash
docker ps -a | grep wechat-scraper
```

### 查看日志

```bash
docker logs wechat-scraper
```

### 进入容器调试

```bash
docker run --rm -it \
  -v $(pwd)/output:/app/output \
  wechat-article-scraper:latest \
  bash

# 在容器内运行测试
python3 scripts/test_runner.py --offline
```

### 健康检查

容器内置健康检查，可以通过以下命令查看：

```bash
docker inspect --format='{{.State.Health.Status}}' wechat-scraper
```

## 性能优化

### 限制资源使用

```bash
docker run --rm \
  --memory=2g \
  --cpus=2 \
  -v $(pwd)/output:/app/output \
  wechat-article-scraper:latest \
  --batch /app/urls.txt
```

### 并行批量抓取

使用 GNU Parallel 并行运行多个容器：

```bash
# 将 URLs 分成多个文件
split -l 10 urls.txt urls_chunk_

# 并行处理
ls urls_chunk_* | parallel \
  'docker run --rm \
    -v $(pwd)/output:/app/output \
    -v $(pwd)/cache:/app/cache \
    -v {}:/app/urls.txt:ro \
    wechat-article-scraper:latest \
    --batch /app/urls.txt -o /app/output'
```

## 安全注意事项

1. **不要**将敏感信息（Cookie、Token）硬编码在 Dockerfile 中
2. 使用只读挂载（`:ro`）保护 URL 列表文件
3. 定期清理输出目录和缓存
4. 在公共环境中使用时，注意代理配置安全

## 更新镜像

```bash
# 拉取最新代码
git pull

# 重建镜像
docker build --no-cache -t wechat-article-scraper:latest .

# 清理旧镜像
docker image prune -f
```
