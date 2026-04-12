'use client';

import { useState, useCallback } from 'react';
import { useEdgeTTS } from '@/hooks/useEdgeTTS';

interface EdgeTTSPlayerProps {
  text: string;
  className?: string;
}

export function EdgeTTSPlayer({ text, className = '' }: EdgeTTSPlayerProps) {
  const {
    isPlaying,
    isLoading,
    currentSegment,
    totalSegments,
    progress,
    error,
    availableVoices,
    play,
    pause,
    resume,
    stop,
    next,
    previous,
    setRate,
    setVoice,
    clearError,
    defaultVoices,
    rateOptions,
    currentText,
  } = useEdgeTTS({ text, voice: 'zh-CN-XiaoxiaoNeural', rate: '+0%' });

  const [selectedVoice, setSelectedVoice] = useState('zh-CN-XiaoxiaoNeural');
  const [selectedRate, setSelectedRate] = useState('+0%');
  const [showVoiceMenu, setShowVoiceMenu] = useState(false);
  const [showRateMenu, setShowRateMenu] = useState(false);

  const handlePlayPause = useCallback(() => {
    if (isPlaying) {
      pause();
    } else {
      resume();
    }
  }, [isPlaying, pause, resume]);

  const handleVoiceChange = useCallback((voice: string) => {
    setSelectedVoice(voice);
    setVoice(voice);
    setShowVoiceMenu(false);
  }, [setVoice]);

  const handleRateChange = useCallback((rate: string) => {
    setSelectedRate(rate);
    setRate(rate);
    setShowRateMenu(false);
  }, [setRate]);

  // 获取当前声音名称
  const currentVoiceName = defaultVoices[selectedVoice as keyof typeof defaultVoices]?.name || '晓晓';
  const currentRateLabel = rateOptions.find(r => r.value === selectedRate)?.label || '1.0x 正常';

  return (
    <div className={`bg-white border border-gray-200 rounded-2xl p-4 shadow-sm ${className}`}>
      {/* Error Message */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-sm text-red-600">{error}</p>
          <button
            onClick={clearError}
            className="text-xs text-red-500 underline mt-1"
          >
            清除错误
          </button>
        </div>
      )}

      {/* Progress Bar */}
      <div className="mb-4">
        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-blue-500 transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-gray-500 mt-1">
          <span>段落 {currentSegment + 1} / {totalSegments}</span>
          <span>{Math.round(progress)}%</span>
        </div>
      </div>

      {/* Main Controls */}
      <div className="flex items-center justify-center gap-4 mb-4">
        <button
          onClick={previous}
          disabled={currentSegment === 0 || isLoading}
          className="p-3 text-gray-600 hover:bg-gray-100 rounded-full disabled:opacity-30 transition-colors"
          aria-label="上一段"
        >
          <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
            <path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/>
          </svg>
        </button>

        <button
          onClick={handlePlayPause}
          disabled={isLoading || totalSegments === 0}
          className="p-4 bg-blue-600 text-white rounded-full hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-lg"
          aria-label={isPlaying ? '暂停' : '播放'}
        >
          {isLoading ? (
            <svg className="w-8 h-8 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"/>
            </svg>
          ) : isPlaying ? (
            <svg className="w-8 h-8" fill="currentColor" viewBox="0 0 24 24">
              <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>
            </svg>
          ) : (
            <svg className="w-8 h-8" fill="currentColor" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z"/>
            </svg>
          )}
        </button>

        <button
          onClick={next}
          disabled={currentSegment >= totalSegments - 1 || isLoading}
          className="p-3 text-gray-600 hover:bg-gray-100 rounded-full disabled:opacity-30 transition-colors"
          aria-label="下一段"
        >
          <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
            <path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/>
          </svg>
        </button>
      </div>

      {/* Secondary Controls */}
      <div className="flex items-center justify-between">
        <button
          onClick={stop}
          disabled={!isPlaying}
          className="p-2 text-gray-500 hover:bg-gray-100 rounded-lg disabled:opacity-30 transition-colors"
          aria-label="停止"
        >
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
            <path d="M6 6h12v12H6z"/>
          </svg>
        </button>

        <div className="flex items-center gap-2">
          {/* Voice Selector */}
          <div className="relative">
            <button
              onClick={() => setShowVoiceMenu(!showVoiceMenu)}
              className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors flex items-center gap-1"
            >
              <span>{currentVoiceName}</span>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {showVoiceMenu && (
              <div className="absolute bottom-full left-0 mb-2 bg-white border border-gray-200 rounded-xl shadow-lg py-2 z-10 min-w-[200px] max-h-[300px] overflow-y-auto">
                {/* Chinese Voices */}
                {availableVoices.chinese.length > 0 && (
                  <>
                    <div className="px-4 py-1 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                      中文
                    </div>
                    {availableVoices.chinese.slice(0, 5).map((voice) => (
                      <button
                        key={voice.id}
                        onClick={() => handleVoiceChange(voice.id)}
                        className={`w-full px-4 py-2 text-sm text-left hover:bg-gray-50 transition-colors ${
                          voice.id === selectedVoice ? 'text-blue-600 bg-blue-50' : 'text-gray-700'
                        }`}
                      >
                        <div className="font-medium">{voice.name}</div>
                        <div className="text-xs text-gray-500">{voice.gender}</div>
                      </button>
                    ))}
                  </>
                )}

                {/* English Voices */}
                {availableVoices.english.length > 0 && (
                  <>
                    <div className="px-4 py-1 text-xs font-semibold text-gray-500 uppercase tracking-wider mt-2">
                      English
                    </div>
                    {availableVoices.english.slice(0, 3).map((voice) => (
                      <button
                        key={voice.id}
                        onClick={() => handleVoiceChange(voice.id)}
                        className={`w-full px-4 py-2 text-sm text-left hover:bg-gray-50 transition-colors ${
                          voice.id === selectedVoice ? 'text-blue-600 bg-blue-50' : 'text-gray-700'
                        }`}
                      >
                        <div className="font-medium">{voice.name}</div>
                        <div className="text-xs text-gray-500">{voice.gender}</div>
                      </button>
                    ))}
                  </>
                )}

                {/* Default Voices Fallback */}
                {availableVoices.chinese.length === 0 && Object.entries(defaultVoices).slice(0, 6).map(([id, info]) => (
                  <button
                    key={id}
                    onClick={() => handleVoiceChange(id)}
                    className={`w-full px-4 py-2 text-sm text-left hover:bg-gray-50 transition-colors ${
                      id === selectedVoice ? 'text-blue-600 bg-blue-50' : 'text-gray-700'
                    }`}
                  >
                    <div className="font-medium">{info.name}</div>
                    <div className="text-xs text-gray-500">{info.locale}</div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Rate Selector */}
          <div className="relative">
            <button
              onClick={() => setShowRateMenu(!showRateMenu)}
              className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
            >
              {currentRateLabel}
            </button>

            {showRateMenu && (
              <div className="absolute bottom-full right-0 mb-2 bg-white border border-gray-200 rounded-xl shadow-lg py-2 z-10 min-w-[120px]">
                {rateOptions.map((option) => (
                  <button
                    key={option.value}
                    onClick={() => handleRateChange(option.value)}
                    className={`w-full px-4 py-2 text-sm text-left hover:bg-gray-50 transition-colors ${
                      option.value === selectedRate ? 'text-blue-600 bg-blue-50' : 'text-gray-700'
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Status */}
        <div className="text-xs text-gray-500">
          {isLoading ? (
            <span className="text-blue-500">生成中...</span>
          ) : isPlaying ? (
            <span className="text-green-500">🔊 朗读中</span>
          ) : (
            <span>就绪</span>
          )}
        </div>
      </div>

      {/* Current Segment Preview */}
      {currentText && (
        <div className="mt-4 p-3 bg-gray-50 rounded-xl">
          <p className="text-sm text-gray-700 line-clamp-3">
            {currentText}
          </p>
        </div>
      )}

      {/* Edge TTS Badge */}
      <div className="mt-3 flex items-center justify-center">
        <span className="text-xs text-gray-400 bg-gray-100 px-2 py-1 rounded">
          Powered by Microsoft Edge TTS
        </span>
      </div>
    </div>
  );
}

export default EdgeTTSPlayer;
