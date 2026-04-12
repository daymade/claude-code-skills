#!/usr/bin/env python3
"""
Edge TTS Server
使用 Microsoft Edge 在线 TTS 服务（免费，无需 API Key）

Endpoints:
- POST /tts - 文本转语音
- GET /voices - 获取可用声音列表
- GET /health - 健康检查
"""

import asyncio
import json
import tempfile
import os
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import edge_tts

# 默认配置
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
DEFAULT_RATE = "+0%"
DEFAULT_VOLUME = "+0%"
DEFAULT_PITCH = "+0Hz"

# 缓存目录
CACHE_DIR = Path(tempfile.gettempdir()) / "edge-tts-cache"
CACHE_DIR.mkdir(exist_ok=True)


class EdgeTTSHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # 简化日志输出
        print(f"[{self.log_date_time_string()}] {format % args}")

    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        if path == "/health":
            self._send_json({"status": "ok", "service": "edge-tts"})
        elif path == "/voices":
            asyncio.run(self._handle_list_voices())
        else:
            self._send_error(404, "Not found")

    def do_POST(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        if path == "/tts":
            asyncio.run(self._handle_tts())
        else:
            self._send_error(404, "Not found")

    async def _handle_list_voices(self):
        """获取可用声音列表"""
        try:
            voices = await edge_tts.list_voices()
            # 筛选常用语言
            preferred_locales = [
                "zh-CN", "zh-HK", "zh-TW", "zh-SG",
                "en-US", "en-GB", "en-AU", "en-CA",
                "ja-JP", "ko-KR", "fr-FR", "de-DE",
            ]

            categorized = {
                "chinese": [],
                "english": [],
                "other": []
            }

            for voice in voices:
                locale = voice.get("Locale", "")
                voice_info = {
                    "id": voice.get("ShortName", ""),
                    "name": voice.get("FriendlyName", ""),
                    "locale": locale,
                    "gender": voice.get("Gender", ""),
                    "suggested": voice.get("Suggested", False),
                }

                if locale.startswith("zh"):
                    categorized["chinese"].append(voice_info)
                elif locale.startswith("en"):
                    categorized["english"].append(voice_info)
                else:
                    categorized["other"].append(voice_info)

            self._send_json({
                "voices": categorized,
                "total": len(voices),
                "count": {
                    "chinese": len(categorized["chinese"]),
                    "english": len(categorized["english"]),
                    "other": len(categorized["other"]),
                }
            })
        except Exception as e:
            self._send_error(500, str(e))

    async def _handle_tts(self):
        """处理 TTS 请求"""
        try:
            # 读取请求体
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)

            text = data.get('text', '')
            if not text:
                self._send_error(400, "Missing 'text' field")
                return

            # 参数
            voice = data.get('voice', DEFAULT_VOICE)
            rate = data.get('rate', DEFAULT_RATE)
            volume = data.get('volume', DEFAULT_VOLUME)
            pitch = data.get('pitch', DEFAULT_PITCH)
            cache_key = data.get('cache_key')

            # 生成缓存文件名
            if cache_key:
                cache_file = CACHE_DIR / f"{cache_key}.mp3"
            else:
                import hashlib
                text_hash = hashlib.md5(f"{text}:{voice}:{rate}:{pitch}".encode()).hexdigest()
                cache_file = CACHE_DIR / f"{text_hash}.mp3"

            # 检查缓存
            if cache_file.exists():
                print(f"[Cache HIT] {cache_file}")
                audio_data = cache_file.read_bytes()
            else:
                print(f"[Cache MISS] Generating TTS for {voice}")
                # 生成 TTS
                communicate = edge_tts.Communicate(
                    text=text,
                    voice=voice,
                    rate=rate,
                    volume=volume,
                    pitch=pitch,
                )

                # 收集音频数据
                audio_chunks = []
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_chunks.append(chunk["data"])

                audio_data = b"".join(audio_chunks)

                # 保存到缓存
                cache_file.write_bytes(audio_data)
                print(f"[Cache SAVED] {cache_file} ({len(audio_data)} bytes)")

            # 发送响应
            self.send_response(200)
            self.send_header('Content-Type', 'audio/mpeg')
            self.send_header('Content-Length', str(len(audio_data)))
            self.send_header('Cache-Control', 'public, max-age=86400')
            self.end_headers()
            self.wfile.write(audio_data)

        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON")
        except Exception as e:
            print(f"[ERROR] {e}")
            self._send_error(500, str(e))

    def _send_json(self, data):
        """发送 JSON 响应"""
        response = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(response)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(response)

    def _send_error(self, code, message):
        """发送错误响应"""
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode())

    def do_OPTIONS(self):
        """处理 CORS 预检请求"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()


def run_server(port=8020):
    """启动 TTS 服务器"""
    server = HTTPServer(('127.0.0.1', port), EdgeTTSHandler)
    print(f"Edge TTS Server running on http://127.0.0.1:{port}")
    print(f"Cache directory: {CACHE_DIR}")
    print(f"Available endpoints:")
    print(f"  GET  /health       - Health check")
    print(f"  GET  /voices       - List available voices")
    print(f"  POST /tts          - Text to speech")
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8020
    run_server(port)
