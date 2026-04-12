/**
 * Theme Engine Unit Tests
 * Tests theme system, typography config, and CSS variable generation
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  THEMES,
  FONT_FAMILIES,
  FONT_SIZE_CONFIG,
  LINE_HEIGHT_CONFIG,
  CONTENT_WIDTH_CONFIG,
  DEFAULT_READER_SETTINGS,
  generateCSSVariables,
  saveReaderSettings,
  loadReaderSettings,
  isDarkTheme,
  getThemeIcon,
  getFontLabel,
  type ThemeId,
  type ReaderSettings,
} from '../../../src/lib/theme-engine';

describe('Theme Engine', () => {
  describe('THEMES', () => {
    it('should have all required themes', () => {
      expect(THEMES).toHaveProperty('light');
      expect(THEMES).toHaveProperty('sepia');
      expect(THEMES).toHaveProperty('dark');
      expect(THEMES).toHaveProperty('oled');
      expect(THEMES).toHaveProperty('paper');
    });

    it('should have valid theme structure', () => {
      Object.entries(THEMES).forEach(([id, theme]) => {
        expect(theme.id).toBe(id);
        expect(theme.name).toBeDefined();
        expect(theme.description).toBeDefined();
        expect(theme.colors).toBeDefined();
        expect(theme.reader).toBeDefined();

        // Check color structure
        expect(theme.colors.background).toBeDefined();
        expect(theme.colors.text).toBeDefined();
        expect(theme.colors.link).toBeDefined();
        expect(theme.colors.highlight).toBeDefined();

        // Check reader colors
        expect(theme.reader.background).toBeDefined();
        expect(theme.reader.text).toBeDefined();
        expect(theme.reader.highlightYellow).toBeDefined();
        expect(theme.reader.highlightGreen).toBeDefined();
        expect(theme.reader.highlightBlue).toBeDefined();
      });
    });

    it('should have distinct colors for light and dark themes', () => {
      const lightBg = THEMES.light.reader.background;
      const darkBg = THEMES.dark.reader.background;
      const oledBg = THEMES.oled.reader.background;

      expect(lightBg).not.toBe(darkBg);
      expect(darkBg).not.toBe(oledBg);
      expect(oledBg).toBe('#000000'); // OLED should be pure black
    });
  });

  describe('FONT_FAMILIES', () => {
    it('should have all font family types', () => {
      expect(FONT_FAMILIES).toHaveProperty('system');
      expect(FONT_FAMILIES).toHaveProperty('serif');
      expect(FONT_FAMILIES).toHaveProperty('sans');
      expect(FONT_FAMILIES).toHaveProperty('mono');
      expect(FONT_FAMILIES).toHaveProperty('custom');
    });

    it('should have valid font family structure', () => {
      Object.entries(FONT_FAMILIES).forEach(([key, font]) => {
        expect(font.name).toBeDefined();
        expect(font.description).toBeDefined();
        expect(font.stack).toBeDefined();
        expect(font.stack.length).toBeGreaterThan(0);
      });
    });

    it('should include Chinese fonts in serif and sans', () => {
      expect(FONT_FAMILIES.serif.stack).toContain('"Noto Serif SC"');
      expect(FONT_FAMILIES.sans.stack).toContain('"Noto Sans SC"');
    });
  });

  describe('FONT_SIZE_CONFIG', () => {
    it('should have all font sizes', () => {
      expect(FONT_SIZE_CONFIG).toHaveProperty('sm');
      expect(FONT_SIZE_CONFIG).toHaveProperty('base');
      expect(FONT_SIZE_CONFIG).toHaveProperty('lg');
      expect(FONT_SIZE_CONFIG).toHaveProperty('xl');
      expect(FONT_SIZE_CONFIG).toHaveProperty('2xl');
    });

    it('should have increasing font sizes', () => {
      const sizes = ['sm', 'base', 'lg', 'xl', '2xl'] as const;
      const sizeValues = sizes.map((s) =>
        parseFloat(FONT_SIZE_CONFIG[s].size)
      );

      for (let i = 1; i < sizeValues.length; i++) {
        expect(sizeValues[i]).toBeGreaterThan(sizeValues[i - 1]);
      }
    });
  });

  describe('DEFAULT_READER_SETTINGS', () => {
    it('should have valid default settings', () => {
      expect(DEFAULT_READER_SETTINGS.theme).toBeDefined();
      expect(DEFAULT_READER_SETTINGS.typography).toBeDefined();
      expect(DEFAULT_READER_SETTINGS.preferences).toBeDefined();
    });

    it('should have valid typography defaults', () => {
      expect(DEFAULT_READER_SETTINGS.typography.fontFamily).toBeDefined();
      expect(DEFAULT_READER_SETTINGS.typography.fontSize).toBeDefined();
      expect(DEFAULT_READER_SETTINGS.typography.lineHeight).toBeDefined();
    });
  });

  describe('generateCSSVariables', () => {
    it('should generate CSS variables for theme and typography', () => {
      const cssVars = generateCSSVariables(
        THEMES.light,
        DEFAULT_READER_SETTINGS.typography
      );

      expect(cssVars['--theme-bg']).toBe(THEMES.light.reader.background);
      expect(cssVars['--theme-text']).toBe(THEMES.light.reader.text);
      expect(cssVars['--font-family']).toBeDefined();
      expect(cssVars['--font-size']).toBeDefined();
      expect(cssVars['--line-height']).toBeDefined();
    });

    it('should generate highlight colors', () => {
      const cssVars = generateCSSVariables(
        THEMES.sepia,
        DEFAULT_READER_SETTINGS.typography
      );

      expect(cssVars['--highlight-yellow']).toBe(
        THEMES.sepia.reader.highlightYellow
      );
      expect(cssVars['--highlight-green']).toBe(
        THEMES.sepia.reader.highlightGreen
      );
    });

    it('should handle different typography configs', () => {
      const customTypography = {
        ...DEFAULT_READER_SETTINGS.typography,
        fontSize: 'xl' as const,
        lineHeight: 'loose' as const,
      };

      const cssVars = generateCSSVariables(THEMES.light, customTypography);

      expect(cssVars['--font-size']).toBe(FONT_SIZE_CONFIG.xl.size);
      expect(cssVars['--line-height']).toBe(LINE_HEIGHT_CONFIG.loose.value);
    });
  });

  describe('isDarkTheme', () => {
    it('should return true for dark themes', () => {
      expect(isDarkTheme('dark')).toBe(true);
      expect(isDarkTheme('oled')).toBe(true);
    });

    it('should return false for light themes', () => {
      expect(isDarkTheme('light')).toBe(false);
      expect(isDarkTheme('sepia')).toBe(false);
      expect(isDarkTheme('paper')).toBe(false);
    });
  });

  describe('getThemeIcon', () => {
    it('should return emoji icons for all themes', () => {
      expect(getThemeIcon('light')).toBe('☀️');
      expect(getThemeIcon('sepia')).toBe('📜');
      expect(getThemeIcon('paper')).toBe('📄');
      expect(getThemeIcon('dark')).toBe('🌙');
      expect(getThemeIcon('oled')).toBe('🌑');
    });
  });

  describe('getFontLabel', () => {
    it('should return font family names', () => {
      expect(getFontLabel('system')).toBe('系统默认');
      expect(getFontLabel('serif')).toBe('衬线体');
      expect(getFontLabel('sans')).toBe('无衬线');
    });
  });
});

describe('Reader Settings Storage', () => {
  let localStorageMock: Storage;

  beforeEach(() => {
    localStorageMock = {
      getItem: vi.fn(),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
      length: 0,
      key: vi.fn(),
    };
    Object.defineProperty(window, 'localStorage', {
      value: localStorageMock,
      writable: true,
    });
  });

  describe('saveReaderSettings', () => {
    it('should save settings to localStorage', () => {
      const settings: ReaderSettings = {
        theme: 'sepia',
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

      saveReaderSettings(settings);

      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        'reader-settings-v1',
        JSON.stringify(settings)
      );
    });
  });

  describe('loadReaderSettings', () => {
    it('should load saved settings', () => {
      const savedSettings: ReaderSettings = {
        theme: 'dark',
        typography: {
          fontFamily: 'sans',
          fontSize: 'xl',
          lineHeight: 'loose',
          letterSpacing: 'wide',
          paragraphSpacing: 'spacious',
          contentWidth: 'wide',
          justifyText: true,
          hyphenation: false,
        },
        preferences: {
          autoHideToolbar: false,
          showReadingProgress: true,
          showEstimatedTime: false,
          enablePagination: false,
          scrollSync: true,
        },
      };

      (localStorageMock.getItem as any).mockReturnValue(
        JSON.stringify(savedSettings)
      );

      const loaded = loadReaderSettings();

      expect(loaded.theme).toBe('dark');
      expect(loaded.typography.fontFamily).toBe('sans');
      expect(loaded.typography.fontSize).toBe('xl');
    });

    it('should return defaults when no settings saved', () => {
      (localStorageMock.getItem as any).mockReturnValue(null);

      const loaded = loadReaderSettings();

      expect(loaded).toEqual(DEFAULT_READER_SETTINGS);
    });

    it('should merge defaults with partial saved settings', () => {
      const partialSettings = {
        theme: 'paper',
        typography: {
          fontSize: '2xl',
        },
      };

      (localStorageMock.getItem as any).mockReturnValue(
        JSON.stringify(partialSettings)
      );

      const loaded = loadReaderSettings();

      expect(loaded.theme).toBe('paper');
      expect(loaded.typography.fontSize).toBe('2xl');
      expect(loaded.typography.fontFamily).toBe(
        DEFAULT_READER_SETTINGS.typography.fontFamily
      );
    });

    it('should handle invalid JSON gracefully', () => {
      (localStorageMock.getItem as any).mockReturnValue('invalid json');

      const loaded = loadReaderSettings();

      expect(loaded).toEqual(DEFAULT_READER_SETTINGS);
    });

    it('should handle server-side rendering', () => {
      Object.defineProperty(window, 'localStorage', {
        value: undefined,
        writable: true,
      });

      const loaded = loadReaderSettings();

      expect(loaded).toEqual(DEFAULT_READER_SETTINGS);
    });
  });
});