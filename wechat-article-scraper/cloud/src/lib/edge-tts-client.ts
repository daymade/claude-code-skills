/**
 * Edge TTS Client
 * 调用本地 edge-tts Python 服务
 * 使用 Microsoft Edge 在线 TTS（免费，无需 API Key）
 */

export interface EdgeTTSOptions {
  text: string;
  voice?: string;
  rate?: string;      // e.g., "-50%", "+10%"
  volume?: string;    // e.g., "-50%", "+0%"
  pitch?: string;     // e.g., "-50Hz", "+10Hz"
  cacheKey?: string;  // 缓存键，用于重复内容
}

export interface EdgeTTSVoice {
  id: string;
  name: string;
  locale: string;
  gender: string;
  suggested: boolean;
}

export interface EdgeTTSError extends Error {
  statusCode?: number;
}

const TTS_SERVER_URL = process.env.EDGE_TTS_URL || 'http://127.0.0.1:8020';

/**
 * 文本转语音
 */
export async function synthesizeSpeech(options: EdgeTTSOptions): Promise<Blob> {
  const response = await fetch(`${TTS_SERVER_URL}/tts`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      text: options.text,
      voice: options.voice || 'zh-CN-XiaoxiaoNeural',
      rate: options.rate || '+0%',
      volume: options.volume || '+0%',
      pitch: options.pitch || '+0Hz',
      cache_key: options.cacheKey,
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    const err = new Error(error.error || `TTS failed: ${response.status}`) as EdgeTTSError;
    err.statusCode = response.status;
    throw err;
  }

  return response.blob();
}

/**
 * 获取可用声音列表
 */
export async function getVoices(): Promise<{
  chinese: EdgeTTSVoice[];
  english: EdgeTTSVoice[];
  other: EdgeTTSVoice[];
}> {
  const response = await fetch(`${TTS_SERVER_URL}/voices`);

  if (!response.ok) {
    throw new Error(`Failed to get voices: ${response.status}`);
  }

  const data = await response.json();
  return data.voices;
}

/**
 * 健康检查
 */
export async function healthCheck(): Promise<{ status: string; service: string }> {
  const response = await fetch(`${TTS_SERVER_URL}/health`);

  if (!response.ok) {
    throw new Error(`TTS server unhealthy: ${response.status}`);
  }

  return response.json();
}

/**
 * 推荐的默认声音
 */
export const DEFAULT_VOICES = {
  // 中文女声
  'zh-CN-XiaoxiaoNeural': {
    name: '晓晓',
    locale: 'zh-CN',
    gender: 'Female',
    description: '活泼、热情',
  },
  // 中文男声
  'zh-CN-YunyangNeural': {
    name: '云扬',
    locale: 'zh-CN',
    gender: 'Male',
    description: '专业、可靠',
  },
  // 中文男声（新闻风格）
  'zh-CN-YunxiNeural': {
    name: '云希',
    locale: 'zh-CN',
    gender: 'Male',
    description: '活泼、阳光',
  },
  // 中文女声（温柔）
  'zh-CN-XiaoyiNeural': {
    name: '晓伊',
    locale: 'zh-CN',
    gender: 'Female',
    description: '温柔、亲切',
  },
  // 台湾女声
  'zh-TW-HsiaoChenNeural': {
    name: '曉臻',
    locale: 'zh-TW',
    gender: 'Female',
    description: '台湾女声',
  },
  // 香港女声
  'zh-HK-HiuMaanNeural': {
    name: '曉曼',
    locale: 'zh-HK',
    gender: 'Female',
    description: '粤语女声',
  },
  // 英文女声
  'en-US-JennyNeural': {
    name: 'Jenny',
    locale: 'en-US',
    gender: 'Female',
    description: '美式英语',
  },
  // 英文男声
  'en-US-GuyNeural': {
    name: 'Guy',
    locale: 'en-US',
    gender: 'Male',
    description: '美式英语',
  },
  // 日文女声
  'ja-JP-NanamiNeural': {
    name: '七海',
    locale: 'ja-JP',
    gender: 'Female',
    description: '日语女声',
  },
  // 韩文女声
  'ko-KR-SunHiNeural': {
    name: '선희',
    locale: 'ko-KR',
    gender: 'Female',
    description: '韩语女声',
  },
};

/**
 * 语速选项
 */
export const RATE_OPTIONS = [
  { value: '-50%', label: '0.5x 慢速' },
  { value: '-25%', label: '0.75x 较慢' },
  { value: '+0%', label: '1.0x 正常' },
  { value: '+25%', label: '1.25x 较快' },
  { value: '+50%', label: '1.5x 快速' },
  { value: '+100%', label: '2.0x 倍速' },
];

/**
 * 创建音频 URL（用于播放）
 */
export function createAudioUrl(blob: Blob): string {
  return URL.createObjectURL(blob);
}

/**
 * 分段文本（用于长文朗读）
 */
export function splitTextIntoSegments(text: string, maxLength: number = 5000): string[] {
  const segments: string[] = [];
  const sentences = text.match(/[^.!?。！？]+[.!?。！？]+/g) || [text];

  let currentSegment = '';
  for (const sentence of sentences) {
    if ((currentSegment + sentence).length > maxLength) {
      if (currentSegment) {
        segments.push(currentSegment.trim());
      }
      currentSegment = sentence;
    } else {
      currentSegment += sentence;
    }
  }

  if (currentSegment) {
    segments.push(currentSegment.trim());
  }

  return segments;
}
