'use client';

import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ThemeId,
  FontFamily,
  FontSize,
  LineHeight,
  ContentWidth,
  ReaderSettings,
  THEMES,
  FONT_FAMILIES,
  FONT_SIZE_CONFIG,
  LINE_HEIGHT_CONFIG,
  CONTENT_WIDTH_CONFIG,
  DEFAULT_READER_SETTINGS,
  generateCSSVariables,
  saveReaderSettings,
  loadReaderSettings,
  getThemeIcon,
  isDarkTheme,
} from '@/lib/theme-engine';

interface ThemeSettingsProps {
  isOpen: boolean;
  onClose: () => void;
  onApply: (settings: ReaderSettings) => void;
  initialSettings?: ReaderSettings;
}

export function ThemeSettings({
  isOpen,
  onClose,
  onApply,
  initialSettings,
}: ThemeSettingsProps) {
  const [settings, setSettings] = useState<ReaderSettings>(
    initialSettings || loadReaderSettings()
  );
  const [activeTab, setActiveTab] = useState<'theme' | 'typography' | 'layout'>('theme');

  const handleThemeChange = useCallback((themeId: ThemeId) => {
    setSettings((prev) => ({ ...prev, theme: themeId }));
  }, []);

  const handleTypographyChange = useCallback(
    (key: keyof typeof settings.typography, value: any) => {
      setSettings((prev) => ({
        ...prev,
        typography: { ...prev.typography, [key]: value },
      }));
    },
    []
  );

  const handlePreferenceChange = useCallback(
    (key: keyof typeof settings.preferences, value: boolean) => {
      setSettings((prev) => ({
        ...prev,
        preferences: { ...prev.preferences, [key]: value },
      }));
    },
    []
  );

  const handleApply = useCallback(() => {
    saveReaderSettings(settings);
    onApply(settings);
    onClose();
  }, [settings, onApply, onClose]);

  const handleReset = useCallback(() => {
    setSettings(DEFAULT_READER_SETTINGS);
  }, []);

  // 预览样式
  const previewStyle = {
    ...generateCSSVariables(THEMES[settings.theme], settings.typography),
    backgroundColor: THEMES[settings.theme].reader.background,
    color: THEMES[settings.theme].reader.text,
    fontFamily: FONT_FAMILIES[settings.typography.fontFamily].stack,
    fontSize: FONT_SIZE_CONFIG[settings.typography.fontSize].size,
    lineHeight: LINE_HEIGHT_CONFIG[settings.typography.lineHeight].value,
    maxWidth: CONTENT_WIDTH_CONFIG[settings.typography.contentWidth].maxWidth,
    textAlign: settings.typography.justifyText ? 'justify' : 'left',
    letterSpacing:
      settings.typography.letterSpacing === 'tight'
        ? '-0.01em'
        : settings.typography.letterSpacing === 'wide'
          ? '0.01em'
          : '0',
  } as React.CSSProperties;

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50"
          />

          {/* Panel */}
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 25, stiffness: 200 }}
            className="fixed right-0 top-0 bottom-0 w-full max-w-lg bg-white shadow-2xl z-50 overflow-hidden flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b">
              <h2 className="text-lg font-semibold text-gray-900">阅读设置</h2>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleReset}
                  className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
                >
                  重置
                </button>
                <button
                  onClick={onClose}
                  className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Tabs */}
            <div className="flex border-b">
              {[
                { id: 'theme', label: '主题', icon: '🎨' },
                { id: 'typography', label: '字体', icon: '🔤' },
                { id: 'layout', label: '排版', icon: '📐' },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as any)}
                  className={`flex-1 flex items-center justify-center gap-2 py-3 text-sm font-medium transition-colors ${
                    activeTab === tab.id
                      ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50/50'
                      : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
                  }`}
                >
                  <span>{tab.icon}</span>
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4">
              {/* Theme Tab */}
              {activeTab === 'theme' && (
                <div className="space-y-4">
                  <div>
                    <h3 className="text-sm font-medium text-gray-700 mb-3">选择主题</h3>
                    <div className="grid grid-cols-2 gap-3">
                      {(Object.keys(THEMES) as ThemeId[]).map((themeId) => {
                        const theme = THEMES[themeId];
                        const isSelected = settings.theme === themeId;
                        return (
                          <button
                            key={themeId}
                            onClick={() => handleThemeChange(themeId)}
                            className={`p-4 rounded-xl border-2 text-left transition-all ${
                              isSelected
                                ? 'border-blue-500 bg-blue-50'
                                : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                            }`}
                            style={{
                              backgroundColor: isSelected ? undefined : theme.reader.background,
                            }}
                          >
                            <div className="flex items-center gap-2 mb-2">
                              <span className="text-2xl">{getThemeIcon(themeId)}</span>
                              <span
                                className="font-medium"
                                style={{ color: theme.reader.text }}
                              >
                                {theme.name}
                              </span>
                              {isSelected && (
                                <span className="ml-auto text-blue-500">
                                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                                    <path
                                      fillRule="evenodd"
                                      d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                                      clipRule="evenodd"
                                    />
                                  </svg>
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-gray-500">{theme.description}</p>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* Dark Mode Toggle Hint */}
                  {isDarkTheme(settings.theme) && (
                    <div className="p-3 bg-blue-50 rounded-lg">
                      <p className="text-sm text-blue-700">
                        💡 深色模式已开启。为保护视力，建议在光线较暗的环境中使用。
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Typography Tab */}
              {activeTab === 'typography' && (
                <div className="space-y-6">
                  {/* Font Family */}
                  <div>
                    <h3 className="text-sm font-medium text-gray-700 mb-3">字体</h3>
                    <div className="space-y-2">
                      {(Object.keys(FONT_FAMILIES) as FontFamily[]).map((font) => (
                        <button
                          key={font}
                          onClick={() => handleTypographyChange('fontFamily', font)}
                          className={`w-full flex items-center justify-between p-3 rounded-lg border transition-colors ${
                            settings.typography.fontFamily === font
                              ? 'border-blue-500 bg-blue-50 text-blue-700'
                              : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                          }`}
                        >
                          <div className="text-left">
                            <div className="font-medium">{FONT_FAMILIES[font].name}</div>
                            <div className="text-xs text-gray-500">
                              {FONT_FAMILIES[font].description}
                            </div>
                          </div>
                          {settings.typography.fontFamily === font && (
                            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                              <path
                                fillRule="evenodd"
                                d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                                clipRule="evenodd"
                              />
                            </svg>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Font Size */}
                  <div>
                    <h3 className="text-sm font-medium text-gray-700 mb-3">字号</h3>
                    <div className="flex gap-2">
                      {(Object.keys(FONT_SIZE_CONFIG) as FontSize[]).map((size) => (
                        <button
                          key={size}
                          onClick={() => handleTypographyChange('fontSize', size)}
                          className={`flex-1 py-2 px-3 rounded-lg border transition-colors ${
                            settings.typography.fontSize === size
                              ? 'border-blue-500 bg-blue-50 text-blue-700'
                              : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                          }`}
                        >
                          <span className="text-sm">{FONT_SIZE_CONFIG[size].label}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Line Height */}
                  <div>
                    <h3 className="text-sm font-medium text-gray-700 mb-3">行高</h3>
                    <div className="grid grid-cols-2 gap-2">
                      {(Object.keys(LINE_HEIGHT_CONFIG) as LineHeight[]).map((lh) => (
                        <button
                          key={lh}
                          onClick={() => handleTypographyChange('lineHeight', lh)}
                          className={`py-2 px-3 rounded-lg border transition-colors ${
                            settings.typography.lineHeight === lh
                              ? 'border-blue-500 bg-blue-50 text-blue-700'
                              : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                          }`}
                        >
                          <span className="text-sm">{LINE_HEIGHT_CONFIG[lh].label}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Letter Spacing */}
                  <div>
                    <h3 className="text-sm font-medium text-gray-700 mb-3">字间距</h3>
                    <div className="flex gap-2">
                      {(['tight', 'normal', 'wide'] as const).map((spacing) => (
                        <button
                          key={spacing}
                          onClick={() => handleTypographyChange('letterSpacing', spacing)}
                          className={`flex-1 py-2 px-3 rounded-lg border transition-colors ${
                            settings.typography.letterSpacing === spacing
                              ? 'border-blue-500 bg-blue-50 text-blue-700'
                              : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                          }`}
                        >
                          <span className="text-sm">
                            {spacing === 'tight' ? '紧凑' : spacing === 'wide' ? '宽松' : '标准'}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Layout Tab */}
              {activeTab === 'layout' && (
                <div className="space-y-6">
                  {/* Content Width */}
                  <div>
                    <h3 className="text-sm font-medium text-gray-700 mb-3">内容宽度</h3>
                    <div className="space-y-2">
                      {(Object.keys(CONTENT_WIDTH_CONFIG) as ContentWidth[]).map((width) => (
                        <button
                          key={width}
                          onClick={() => handleTypographyChange('contentWidth', width)}
                          className={`w-full flex items-center justify-between p-3 rounded-lg border transition-colors ${
                            settings.typography.contentWidth === width
                              ? 'border-blue-500 bg-blue-50 text-blue-700'
                              : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                          }`}
                        >
                          <span className="text-sm">
                            {CONTENT_WIDTH_CONFIG[width].label}
                          </span>
                          <span className="text-xs text-gray-400">
                            {CONTENT_WIDTH_CONFIG[width].maxWidth}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Paragraph Spacing */}
                  <div>
                    <h3 className="text-sm font-medium text-gray-700 mb-3">段落间距</h3>
                    <div className="flex gap-2">
                      {(['compact', 'normal', 'spacious'] as const).map((spacing) => (
                        <button
                          key={spacing}
                          onClick={() => handleTypographyChange('paragraphSpacing', spacing)}
                          className={`flex-1 py-2 px-3 rounded-lg border transition-colors ${
                            settings.typography.paragraphSpacing === spacing
                              ? 'border-blue-500 bg-blue-50 text-blue-700'
                              : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                          }`}
                        >
                          <span className="text-sm">
                            {spacing === 'compact' ? '紧凑' : spacing === 'spacious' ? '宽松' : '标准'}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Justify Text */}
                  <div>
                    <label className="flex items-center justify-between p-3 rounded-lg border border-gray-200 cursor-pointer hover:bg-gray-50">
                      <div>
                        <div className="font-medium text-sm">两端对齐</div>
                        <div className="text-xs text-gray-500">让段落边缘整齐</div>
                      </div>
                      <input
                        type="checkbox"
                        checked={settings.typography.justifyText}
                        onChange={(e) => handleTypographyChange('justifyText', e.target.checked)}
                        className="w-5 h-5 text-blue-600 rounded focus:ring-blue-500"
                      />
                    </label>
                  </div>

                  {/* Preferences */}
                  <div className="pt-4 border-t">
                    <h3 className="text-sm font-medium text-gray-700 mb-3">阅读偏好</h3>
                    <div className="space-y-3">
                      {[
                        { key: 'showReadingProgress', label: '显示阅读进度', desc: '在顶部显示进度条' },
                        { key: 'showEstimatedTime', label: '显示预估时间', desc: '显示剩余阅读时间' },
                        { key: 'autoHideToolbar', label: '自动隐藏工具栏', desc: '滚动时隐藏顶部工具栏' },
                      ].map((item) => (
                        <label
                          key={item.key}
                          className="flex items-center justify-between p-3 rounded-lg border border-gray-200 cursor-pointer hover:bg-gray-50"
                        >
                          <div>
                            <div className="font-medium text-sm">{item.label}</div>
                            <div className="text-xs text-gray-500">{item.desc}</div>
                          </div>
                          <input
                            type="checkbox"
                            checked={settings.preferences[item.key as keyof typeof settings.preferences]}
                            onChange={(e) =>
                              handlePreferenceChange(
                                item.key as keyof typeof settings.preferences,
                                e.target.checked
                              )
                            }
                            className="w-5 h-5 text-blue-600 rounded focus:ring-blue-500"
                          />
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Preview */}
            <div className="border-t p-4">
              <h3 className="text-sm font-medium text-gray-700 mb-2">预览</h3>
              <div
                className="p-4 rounded-lg border transition-all duration-300"
                style={previewStyle}
              >
                <p className="mb-2">
                  这是一个预览文本。你可以看到当前设置下的字体、字号和行高效果。
                </p>
                <p>
                  良好的排版让阅读更加舒适，减少视觉疲劳。调整设置找到最适合你的阅读体验。
                </p>
              </div>
            </div>

            {/* Footer */}
            <div className="p-4 border-t bg-gray-50">
              <button
                onClick={handleApply}
                className="w-full py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
              >
                应用设置
              </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

export default ThemeSettings;