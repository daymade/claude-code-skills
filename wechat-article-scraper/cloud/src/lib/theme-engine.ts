/**
 * Theme Engine - 沉浸式阅读主题系统
 *
 * 特性:
 * - 精心设计的预设主题 (Light/Sepia/Dark/OLED)
 * - 灵活的字体系统 (系统字体 + 第三方字体)
 * - 精细排版控制 (行高/段距/页边距/字间距)
 * - 用户偏好持久化
 * - CSS 变量动态切换
 *
 * 对标: Matter Reader / Omnivore / Apple Books
 */

export type ThemeId = 'light' | 'sepia' | 'dark' | 'oled' | 'paper';
export type FontFamily = 'system' | 'serif' | 'sans' | 'mono' | 'custom';
export type FontSize = 'sm' | 'base' | 'lg' | 'xl' | '2xl';
export type LineHeight = 'compact' | 'normal' | 'relaxed' | 'loose';
export type ContentWidth = 'narrow' | 'medium' | 'wide' | 'full';

export interface ThemeConfig {
  id: ThemeId;
  name: string;
  description: string;
  // 颜色系统
  colors: {
    background: string;
    surface: string;
    text: string;
    textMuted: string;
    link: string;
    highlight: string;
    border: string;
    selection: string;
  };
  // 阅读器特定颜色
  reader: {
    background: string;
    text: string;
    quoteBorder: string;
    quoteBackground: string;
    codeBackground: string;
    highlightYellow: string;
    highlightGreen: string;
    highlightBlue: string;
    highlightPink: string;
    highlightPurple: string;
  };
}

export interface TypographyConfig {
  fontFamily: FontFamily;
  customFont?: string; // 自定义字体名称
  fontSize: FontSize;
  lineHeight: LineHeight;
  letterSpacing: 'tight' | 'normal' | 'wide';
  paragraphSpacing: 'compact' | 'normal' | 'spacious';
  contentWidth: ContentWidth;
  justifyText: boolean;
  hyphenation: boolean;
}

export interface ReaderSettings {
  theme: ThemeId;
  typography: TypographyConfig;
  // 阅读行为
  preferences: {
    autoHideToolbar: boolean;
    showReadingProgress: boolean;
    showEstimatedTime: boolean;
    enablePagination: boolean;
    scrollSync: boolean;
  };
}

// ============================================
// 预设主题配置
// ============================================

export const THEMES: Record<ThemeId, ThemeConfig> = {
  light: {
    id: 'light',
    name: '白天',
    description: '清晰的白色背景，适合日间阅读',
    colors: {
      background: '#ffffff',
      surface: '#f8fafc',
      text: '#1e293b',
      textMuted: '#64748b',
      link: '#3b82f6',
      highlight: '#dbeafe',
      border: '#e2e8f0',
      selection: '#bfdbfe',
    },
    reader: {
      background: '#ffffff',
      text: '#1e293b',
      quoteBorder: '#3b82f6',
      quoteBackground: '#f1f5f9',
      codeBackground: '#f8fafc',
      highlightYellow: '#fef3c7',
      highlightGreen: '#d1fae5',
      highlightBlue: '#dbeafe',
      highlightPink: '#fce7f3',
      highlightPurple: '#f3e8ff',
    },
  },

  sepia: {
    id: 'sepia',
    name: '护眼',
    description: '温暖的米黄色，长时间阅读更舒适',
    colors: {
      background: '#f4ecd8',
      surface: '#f5efe0',
      text: '#433422',
      textMuted: '#8b7355',
      link: '#b45309',
      highlight: '#fde68a',
      border: '#e7dcc8',
      selection: '#fcd34d',
    },
    reader: {
      background: '#f4ecd8',
      text: '#433422',
      quoteBorder: '#b45309',
      quoteBackground: '#f5efe0',
      codeBackground: '#faf6ed',
      highlightYellow: '#fcd34d',
      highlightGreen: '#bbf7d0',
      highlightBlue: '#bfdbfe',
      highlightPink: '#fbcfe8',
      highlightPurple: '#e9d5ff',
    },
  },

  paper: {
    id: 'paper',
    name: '纸张',
    description: '模拟纸张纹理，最接近实体书体验',
    colors: {
      background: '#faf9f6',
      surface: '#ffffff',
      text: '#2d2d2d',
      textMuted: '#666666',
      link: '#2563eb',
      highlight: '#fef08a',
      border: '#e5e5e5',
      selection: '#93c5fd',
    },
    reader: {
      background: '#faf9f6',
      text: '#2d2d2d',
      quoteBorder: '#525252',
      quoteBackground: '#f5f5f4',
      codeBackground: '#fafaf9',
      highlightYellow: '#fef9c3',
      highlightGreen: '#dcfce7',
      highlightBlue: '#dbeafe',
      highlightPink: '#fce7f3',
      highlightPurple: '#f3e8ff',
    },
  },

  dark: {
    id: 'dark',
    name: '夜间',
    description: '深色模式，适合夜间阅读',
    colors: {
      background: '#0f172a',
      surface: '#1e293b',
      text: '#e2e8f0',
      textMuted: '#94a3b8',
      link: '#60a5fa',
      highlight: '#1e40af',
      border: '#334155',
      selection: '#3b82f6',
    },
    reader: {
      background: '#0f172a',
      text: '#e2e8f0',
      quoteBorder: '#60a5fa',
      quoteBackground: '#1e293b',
      codeBackground: '#1e293b',
      highlightYellow: '#713f12',
      highlightGreen: '#14532d',
      highlightBlue: '#1e3a8a',
      highlightPink: '#831843',
      highlightPurple: '#581c87',
    },
  },

  oled: {
    id: 'oled',
    name: 'OLED',
    description: '纯黑背景，为OLED屏幕优化，极致省电',
    colors: {
      background: '#000000',
      surface: '#0a0a0a',
      text: '#e5e5e5',
      textMuted: '#737373',
      link: '#60a5fa',
      highlight: '#171717',
      border: '#262626',
      selection: '#404040',
    },
    reader: {
      background: '#000000',
      text: '#e5e5e5',
      quoteBorder: '#525252',
      quoteBackground: '#0a0a0a',
      codeBackground: '#0a0a0a',
      highlightYellow: '#3f3f00',
      highlightGreen: '#002200',
      highlightBlue: '#000033',
      highlightPink: '#330022',
      highlightPurple: '#220033',
    },
  },
};

// ============================================
// 字体配置
// ============================================

export const FONT_FAMILIES: Record<FontFamily, { name: string; description: string; stack: string }> = {
  system: {
    name: '系统默认',
    description: '使用系统默认字体',
    stack: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  },
  serif: {
    name: '衬线体',
    description: '传统印刷风格，适合长文阅读',
    stack: '"Noto Serif SC", "Source Han Serif SC", "PingFang SC", "Microsoft YaHei", serif',
  },
  sans: {
    name: '无衬线',
    description: '现代简洁，屏幕显示清晰',
    stack: '"Noto Sans SC", "Source Han Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif',
  },
  mono: {
    name: '等宽',
    description: '代码风格，技术文章适用',
    stack: '"JetBrains Mono", "Fira Code", "SF Mono", Monaco, "Cascadia Code", monospace',
  },
  custom: {
    name: '自定义',
    description: '使用自定义字体',
    stack: 'inherit',
  },
};

export const FONT_SIZE_CONFIG: Record<FontSize, { label: string; size: string; lineHeight: string }> = {
  sm: { label: '小', size: '0.875rem', lineHeight: '1.6' },
  base: { label: '中', size: '1rem', lineHeight: '1.7' },
  lg: { label: '大', size: '1.125rem', lineHeight: '1.8' },
  xl: { label: '特大', size: '1.25rem', lineHeight: '1.9' },
  '2xl': { label: '超大', size: '1.5rem', lineHeight: '2' },
};

export const LINE_HEIGHT_CONFIG: Record<LineHeight, { label: string; value: string }> = {
  compact: { label: '紧凑', value: '1.5' },
  normal: { label: '标准', value: '1.7' },
  relaxed: { label: '宽松', value: '1.9' },
  loose: { label: '极宽', value: '2.2' },
};

export const CONTENT_WIDTH_CONFIG: Record<ContentWidth, { label: string; maxWidth: string }> = {
  narrow: { label: '窄', maxWidth: '60ch' },
  medium: { label: '适中', maxWidth: '70ch' },
  wide: { label: '宽', maxWidth: '80ch' },
  full: { label: '全宽', maxWidth: '100%' },
};

// ============================================
// 默认设置
// ============================================

export const DEFAULT_READER_SETTINGS: ReaderSettings = {
  theme: 'light',
  typography: {
    fontFamily: 'serif',
    fontSize: 'lg',
    lineHeight: 'relaxed',
    letterSpacing: 'normal',
    paragraphSpacing: 'normal',
    contentWidth: 'medium',
    justifyText: true,
    hyphenation: false,
  },
  preferences: {
    autoHideToolbar: true,
    showReadingProgress: true,
    showEstimatedTime: true,
    enablePagination: false,
    scrollSync: true,
  },
};

// ============================================
// CSS 变量生成
// ============================================

export function generateCSSVariables(
  theme: ThemeConfig,
  typography: TypographyConfig
): Record<string, string> {
  return {
    // 主题颜色
    '--theme-bg': theme.reader.background,
    '--theme-text': theme.reader.text,
    '--theme-link': theme.colors.link,
    '--theme-muted': theme.colors.textMuted,
    '--theme-border': theme.colors.border,
    '--theme-surface': theme.colors.surface,
    '--theme-selection': theme.colors.selection,

    // 阅读器高亮颜色
    '--highlight-yellow': theme.reader.highlightYellow,
    '--highlight-green': theme.reader.highlightGreen,
    '--highlight-blue': theme.reader.highlightBlue,
    '--highlight-pink': theme.reader.highlightPink,
    '--highlight-purple': theme.reader.highlightPurple,

    // 引用和代码
    '--quote-border': theme.reader.quoteBorder,
    '--quote-bg': theme.reader.quoteBackground,
    '--code-bg': theme.reader.codeBackground,

    // 字体
    '--font-family': FONT_FAMILIES[typography.fontFamily].stack,
    '--font-size': FONT_SIZE_CONFIG[typography.fontSize].size,
    '--line-height': LINE_HEIGHT_CONFIG[typography.lineHeight].value,
    '--content-width': CONTENT_WIDTH_CONFIG[typography.contentWidth].maxWidth,

    // 间距
    '--letter-spacing':
      typography.letterSpacing === 'tight'
        ? '-0.01em'
        : typography.letterSpacing === 'wide'
          ? '0.01em'
          : '0',
    '--paragraph-spacing':
      typography.paragraphSpacing === 'compact'
        ? '1em'
        : typography.paragraphSpacing === 'spacious'
          ? '2.5em'
          : '1.75em',
  };
}

// ============================================
// 存储管理
// ============================================

const STORAGE_KEY = 'reader-settings-v1';

export function saveReaderSettings(settings: ReaderSettings): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

export function loadReaderSettings(): ReaderSettings {
  if (typeof window === 'undefined') return DEFAULT_READER_SETTINGS;

  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return DEFAULT_READER_SETTINGS;

    const parsed = JSON.parse(stored) as ReaderSettings;

    // 合并默认值，处理新增字段
    return {
      ...DEFAULT_READER_SETTINGS,
      ...parsed,
      typography: {
        ...DEFAULT_READER_SETTINGS.typography,
        ...parsed.typography,
      },
      preferences: {
        ...DEFAULT_READER_SETTINGS.preferences,
        ...parsed.preferences,
      },
    };
  } catch {
    return DEFAULT_READER_SETTINGS;
  }
}

// ============================================
// 辅助函数
// ============================================

export function isDarkTheme(themeId: ThemeId): boolean {
  return themeId === 'dark' || themeId === 'oled';
}

export function getThemeIcon(themeId: ThemeId): string {
  const icons: Record<ThemeId, string> = {
    light: '☀️',
    sepia: '📜',
    paper: '📄',
    dark: '🌙',
    oled: '🌑',
  };
  return icons[themeId];
}

export function getFontLabel(fontFamily: FontFamily): string {
  return FONT_FAMILIES[fontFamily].name;
}

export function getFontSizeLabel(size: FontSize): string {
  return FONT_SIZE_CONFIG[size].label;
}

export function getLineHeightLabel(lineHeight: LineHeight): string {
  return LINE_HEIGHT_CONFIG[lineHeight].label;
}