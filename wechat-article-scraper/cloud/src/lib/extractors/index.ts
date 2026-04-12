/**
 * 内容提取器统一入口
 * 提供多策略内容提取，优先使用 ftr-site-config 规则库
 */

import { SiteConfigExtractor } from './site-config-adapter';
import type { ExtractedContent } from './site-config-adapter';

export interface ExtractOptions {
  url: string;
  html: string;
  preferSiteConfig?: boolean; // 是否优先使用站点规则
  fallbackToReadability?: boolean; // 是否允许回退到 Readability
}

/**
 * 统一提取内容的主函数
 * 策略：ftr-site-config 规则 → Readability → 通用提取
 */
export async function extractContent(options: ExtractOptions): Promise<ExtractedContent> {
  const { url, html, preferSiteConfig = true, fallbackToReadability = true } = options;

  if (!html || html.length < 100) {
    return {
      title: '',
      content: '',
      extractor: 'failure',
    };
  }

  // 策略1: 使用 ftr-site-config 规则库
  if (preferSiteConfig) {
    const siteConfigExtractor = new SiteConfigExtractor();
    const result = await siteConfigExtractor.extract(html, url);

    // 如果提取成功或不允许回退，直接返回
    if (result.extractor !== 'failure' || !fallbackToReadability) {
      return result;
    }

    // 如果 site-config 失败但 readability 成功了，会返回 readability 结果
    return result;
  }

  // 策略2: 直接使用 Readability
  if (fallbackToReadability) {
    const siteConfigExtractor = new SiteConfigExtractor();
    return siteConfigExtractor.extract(html, url);
  }

  return {
    title: '',
    content: '',
    extractor: 'failure',
  };
}

// 重新导出
export { SiteConfigExtractor } from './site-config-adapter';
export type { ExtractedContent, SiteConfigRule } from './site-config-adapter';
export { hasSiteRule, preloadCommonRules } from './site-config-adapter';
