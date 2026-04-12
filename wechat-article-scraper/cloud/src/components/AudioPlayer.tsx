'use client';

import { useState, useEffect, useCallback } from 'react';
import { useTTS } from '@/lib/tts-engine';

interface AudioPlayerProps {
  articleId: string;
  content: string;
  className?: string;
}

const SPEED_OPTIONS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3];

export function AudioPlayer({ articleId, content, className = '' }: AudioPlayerProps) {
  const { state, play, pause, resume, stop, seekTo, setRate } = useTTS(articleId, content);
  const [showSpeedMenu, setShowSpeedMenu] = useState(false);
  const [selectedSpeed, setSelectedSpeed] = useState(1);

  const handlePlayPause = useCallback(() => {
    if (state.isPlaying) {
      pause();
    } else {
      resume();
    }
  }, [state.isPlaying, pause, resume]);

  const handleSpeedChange = (speed: number) => {
    setSelectedSpeed(speed);
    setRate(speed);
    setShowSpeedMenu(false);
  };

  const progress = state.segments.length > 0
    ? (state.currentSegment / state.segments.length) * 100
    : 0;

  return (
    <div className={`bg-white border border-gray-200 rounded-2xl p-4 shadow-sm ${className}`}>
      {/* Progress Bar */}
      <div className="mb-4">
        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-blue-500 transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-gray-500 mt-1">
          <span>段落 {state.currentSegment + 1} / {state.segments.length}</span>
          <span>{Math.round(progress)}%</span>
        </div>
      </div>

      {/* Main Controls */}
      <div className="flex items-center justify-center gap-4 mb-4">
        <button
          onClick={() => seekTo(Math.max(0, state.currentSegment - 1))}
          disabled={state.currentSegment === 0 || state.isLoading}
          className="p-3 text-gray-600 hover:bg-gray-100 rounded-full disabled:opacity-30 transition-colors"
          aria-label="上一段"
        >
          <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
            <path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/>
          </svg>
        </button>

        <button
          onClick={handlePlayPause}
          disabled={state.isLoading || state.segments.length === 0}
          className="p-4 bg-blue-600 text-white rounded-full hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-lg"
          aria-label={state.isPlaying ? '暂停' : '播放'}
        >
          {state.isLoading ? (
            <svg className="w-8 h-8 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"/>
            </svg>
          ) : state.isPlaying ? (
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
          onClick={() => seekTo(Math.min(state.segments.length - 1, state.currentSegment + 1))}
          disabled={state.currentSegment >= state.segments.length - 1 || state.isLoading}
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
          onClick={() => stop()}
          disabled={!state.isPlaying}
          className="p-2 text-gray-500 hover:bg-gray-100 rounded-lg disabled:opacity-30 transition-colors"
          aria-label="停止"
        >
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
            <path d="M6 6h12v12H6z"/>
          </svg>
        </button>

        {/* Speed Control */}
        <div className="relative">
          <button
            onClick={() => setShowSpeedMenu(!showSpeedMenu)}
            className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
          >
            {selectedSpeed}x
          </button>

          {showSpeedMenu && (
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 bg-white border border-gray-200 rounded-xl shadow-lg py-2 z-10">
              {SPEED_OPTIONS.map((speed) => (
                <button
                  key={speed}
                  onClick={() => handleSpeedChange(speed)}
                  className={`w-full px-4 py-2 text-sm text-left hover:bg-gray-50 transition-colors ${
                    speed === selectedSpeed ? 'text-blue-600 bg-blue-50' : 'text-gray-700'
                  }`}
                >
                  {speed}x
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Voice Info */}
        <div className="text-xs text-gray-500">
          {state.error ? (
            <span className="text-red-500">{state.error}</span>
          ) : (
            <span>🔊 朗读中</span>
          )}
        </div>
      </div>

      {/* Current Segment Preview */}
      {state.segments[state.currentSegment] && (
        <div className="mt-4 p-3 bg-gray-50 rounded-xl">
          <p className="text-sm text-gray-700 line-clamp-3">
            {state.segments[state.currentSegment].text}
          </p>
        </div>
      )}
    </div>
  );
}
