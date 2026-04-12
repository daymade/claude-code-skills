/**
 * Edge TTS React Hook
 * 使用 Microsoft Edge 在线 TTS 服务（免费，高质量）
 *
 * 特点:
 * - 无需 API Key
 * - 支持 100+ 声音
 * - 支持语速、音调调节
 * - 本地缓存
 * - 分段播放（支持长文）
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import {
  synthesizeSpeech,
  getVoices,
  splitTextIntoSegments,
  DEFAULT_VOICES,
  RATE_OPTIONS,
  EdgeTTSVoice,
} from '@/lib/edge-tts-client';

export interface EdgeTTSState {
  isPlaying: boolean;
  isLoading: boolean;
  currentSegment: number;
  totalSegments: number;
  progress: number; // 0-100
  error: string | null;
  voices: EdgeTTSVoice[];
  availableVoices: {
    chinese: EdgeTTSVoice[];
    english: EdgeTTSVoice[];
    other: EdgeTTSVoice[];
  };
}

export interface UseEdgeTTSOptions {
  text: string;
  voice?: string;
  rate?: string;
  autoPlay?: boolean;
}

export function useEdgeTTS(options: UseEdgeTTSOptions) {
  const { text, voice = 'zh-CN-XiaoxiaoNeural', rate = '+0%' } = options;

  const [state, setState] = useState<EdgeTTSState>({
    isPlaying: false,
    isLoading: false,
    currentSegment: 0,
    totalSegments: 0,
    progress: 0,
    error: null,
    voices: [],
    availableVoices: { chinese: [], english: [], other: [] },
  });

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const segmentsRef = useRef<string[]>([]);
  const audioUrlsRef = useRef<string[]>([]);
  const abortControllerRef = useRef<AbortController | null>(null);

  // 分割文本
  useEffect(() => {
    segmentsRef.current = splitTextIntoSegments(text, 3000);
    setState(prev => ({
      ...prev,
      totalSegments: segmentsRef.current.length,
      currentSegment: 0,
      progress: 0,
    }));
  }, [text]);

  // 加载声音列表
  useEffect(() => {
    getVoices()
      .then(voices => {
        setState(prev => ({ ...prev, availableVoices: voices }));
      })
      .catch(err => {
        console.warn('Failed to load voices:', err);
      });
  }, []);

  // 清理函数
  useEffect(() => {
    return () => {
      // 清理音频 URL
      audioUrlsRef.current.forEach(url => URL.revokeObjectURL(url));
      audioUrlsRef.current = [];
      abortControllerRef.current?.abort();
    };
  }, []);

  const updateState = useCallback((updates: Partial<EdgeTTSState>) => {
    setState(prev => ({ ...prev, ...updates }));
  }, []);

  const playSegment = useCallback(async (segmentIndex: number) => {
    if (segmentIndex >= segmentsRef.current.length) {
      // 播放完成
      updateState({
        isPlaying: false,
        currentSegment: 0,
        progress: 100,
      });
      return;
    }

    const segmentText = segmentsRef.current[segmentIndex];

    try {
      updateState({ isLoading: true, error: null });

      // 检查是否已缓存
      let audioUrl = audioUrlsRef.current[segmentIndex];

      if (!audioUrl) {
        // 生成 TTS
        const blob = await synthesizeSpeech({
          text: segmentText,
          voice,
          rate,
          cacheKey: `${voice}-${segmentIndex}-${segmentText.slice(0, 50)}`,
        });

        audioUrl = URL.createObjectURL(blob);
        audioUrlsRef.current[segmentIndex] = audioUrl;
      }

      // 播放音频
      if (audioRef.current) {
        audioRef.current.pause();
      }

      audioRef.current = new Audio(audioUrl);

      audioRef.current.onended = () => {
        playSegment(segmentIndex + 1);
      };

      audioRef.current.onerror = () => {
        updateState({
          error: 'Failed to play audio',
          isPlaying: false,
          isLoading: false,
        });
      };

      await audioRef.current.play();

      updateState({
        isPlaying: true,
        isLoading: false,
        currentSegment: segmentIndex,
        progress: ((segmentIndex + 1) / segmentsRef.current.length) * 100,
      });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'TTS failed';
      updateState({
        error: errorMessage,
        isPlaying: false,
        isLoading: false,
      });
    }
  }, [voice, rate, updateState]);

  const play = useCallback(() => {
    if (state.isPlaying) return;
    playSegment(state.currentSegment);
  }, [state.isPlaying, state.currentSegment, playSegment]);

  const pause = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
    }
    updateState({ isPlaying: false });
  }, [updateState]);

  const resume = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.play();
      updateState({ isPlaying: true });
    } else {
      play();
    }
  }, [play, updateState]);

  const stop = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    updateState({
      isPlaying: false,
      currentSegment: 0,
      progress: 0,
    });
  }, [updateState]);

  const seekTo = useCallback((segmentIndex: number) => {
    stop();
    playSegment(segmentIndex);
  }, [stop, playSegment]);

  const next = useCallback(() => {
    if (state.currentSegment < segmentsRef.current.length - 1) {
      seekTo(state.currentSegment + 1);
    }
  }, [state.currentSegment, seekTo]);

  const previous = useCallback(() => {
    if (state.currentSegment > 0) {
      seekTo(state.currentSegment - 1);
    }
  }, [state.currentSegment, seekTo]);

  const setRate = useCallback((newRate: string) => {
    // 需要重新生成缓存
    audioUrlsRef.current.forEach(url => URL.revokeObjectURL(url));
    audioUrlsRef.current = [];

    if (state.isPlaying) {
      // 重新开始当前段落
      playSegment(state.currentSegment);
    }
  }, [state.isPlaying, state.currentSegment, playSegment]);

  const setVoice = useCallback((newVoice: string) => {
    // 需要重新生成缓存
    audioUrlsRef.current.forEach(url => URL.revokeObjectURL(url));
    audioUrlsRef.current = [];

    if (state.isPlaying) {
      playSegment(state.currentSegment);
    }
  }, [state.isPlaying, state.currentSegment, playSegment]);

  const clearError = useCallback(() => {
    updateState({ error: null });
  }, [updateState]);

  return {
    // 状态
    ...state,

    // 控制方法
    play,
    pause,
    resume,
    stop,
    seekTo,
    next,
    previous,
    setRate,
    setVoice,
    clearError,

    // 配置
    defaultVoices: DEFAULT_VOICES,
    rateOptions: RATE_OPTIONS,

    // 分段信息
    currentText: segmentsRef.current[state.currentSegment] || '',
    segments: segmentsRef.current,
  };
}

export default useEdgeTTS;
