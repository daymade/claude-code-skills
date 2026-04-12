/**
 * WeChat Article Scraper Benchmark Test
 * Round 93: Core Functionality Validation
 *
 * Measures scrape success rate across all 6 strategies
 * Target: ≥ 95% success rate
 */

import { test, expect, describe } from 'vitest';
import { WechatArticleScraper, ContentStatus } from '../../src/lib/scraper';
import * as fs from 'fs';
import * as path from 'path';

interface TestArticle {
  id: string;
  url: string;
  title: string;
  category: string;
  complexity: 'simple' | 'medium' | 'complex';
  year: number;
  account_type: string;
  features: string[];
  expected_fields: string[];
}

interface TestDataset {
  metadata: {
    name: string;
    total_articles: number;
  };
  articles: TestArticle[];
  statistics: {
    by_complexity: Record<string, number>;
    by_category: Record<string, number>;
  };
}

interface BenchmarkResult {
  articleId: string;
  url: string;
  success: boolean;
  strategy: string;
  duration: number;
  fields: string[];
  missingFields: string[];
  errors: string[];
  contentStatus?: ContentStatus;
}

// Load test dataset
const datasetPath = path.join(__dirname, 'test-dataset-100.json');
const dataset: TestDataset = JSON.parse(fs.readFileSync(datasetPath, 'utf-8'));

// Use a subset for CI/testing (15 articles)
const TEST_SUBSET = dataset.articles.slice(0, 15);

describe('Scrape Success Rate Benchmark', () => {
  const results: BenchmarkResult[] = [];

  test.each(TEST_SUBSET)(
    'scrape article #$id - $title ($complexity)',
    async (article) => {
      const scraper = new WechatArticleScraper();
      const startTime = Date.now();

      try {
        const result = await scraper.scrape(article.url, {
          strategy: 'adaptive',
          priority: 'high',
          extractComments: true,
          extractImages: true,
          timeout: 30000
        });

        const duration = Date.now() - startTime;

        // Check expected fields
        const extractedFields: string[] = [];
        if (result.title) extractedFields.push('title');
        if (result.author) extractedFields.push('author');
        if (result.publishTime) extractedFields.push('publish_time');
        if (result.content && result.content.length > 100) extractedFields.push('content');
        if (result.images && result.images.length > 0) extractedFields.push('images');
        if (result.stats?.readCount) extractedFields.push('read_count');
        if (result.stats?.likeCount) extractedFields.push('like_count');

        const missingFields = article.expected_fields.filter(
          f => !extractedFields.includes(f)
        );

        const benchmarkResult: BenchmarkResult = {
          articleId: article.id,
          url: article.url,
          success: missingFields.length <= 1, // Allow 1 missing field
          strategy: result.strategy || 'unknown',
          duration,
          fields: extractedFields,
          missingFields,
          errors: result.errors || [],
          contentStatus: result.status
        };

        results.push(benchmarkResult);

        // Assertions
        expect(benchmarkResult.success).toBe(true);
        expect(duration).toBeLessThan(30000); // 30s timeout

        // Critical fields must be present
        expect(result.title).toBeTruthy();
        expect(result.content).toBeTruthy();
        expect(result.content?.length).toBeGreaterThan(100);

      } catch (error) {
        const duration = Date.now() - startTime;
        results.push({
          articleId: article.id,
          url: article.url,
          success: false,
          strategy: 'failed',
          duration,
          fields: [],
          missingFields: article.expected_fields,
          errors: [error instanceof Error ? error.message : 'Unknown error']
        });

        throw error;
      }
    },
    30000 // 30 second timeout per test
  );

  test('generate benchmark report', () => {
    const total = results.length;
    const successful = results.filter(r => r.success).length;
    const successRate = (successful / total) * 100;
    const avgDuration = results.reduce((sum, r) => sum + r.duration, 0) / total;

    // Strategy distribution
    const strategyCounts: Record<string, number> = {};
    results.forEach(r => {
      strategyCounts[r.strategy] = (strategyCounts[r.strategy] || 0) + 1;
    });

    // Complexity breakdown
    const complexityResults: Record<string, { total: number; success: number }> = {};
    TEST_SUBSET.forEach((article, i) => {
      if (!complexityResults[article.complexity]) {
        complexityResults[article.complexity] = { total: 0, success: 0 };
      }
      complexityResults[article.complexity].total++;
      if (results[i]?.success) {
        complexityResults[article.complexity].success++;
      }
    });

    const report = {
      timestamp: new Date().toISOString(),
      summary: {
        totalArticles: total,
        successful,
        failed: total - successful,
        successRate: `${successRate.toFixed(2)}%`,
        avgDuration: `${avgDuration.toFixed(0)}ms`,
        meetsTarget: successRate >= 95
      },
      strategyDistribution: strategyCounts,
      byComplexity: Object.entries(complexityResults).map(([level, data]) => ({
        level,
        total: data.total,
        success: data.success,
        rate: `${((data.success / data.total) * 100).toFixed(2)}%`
      })),
      failures: results.filter(r => !r.success).map(r => ({
        id: r.articleId,
        strategy: r.strategy,
        errors: r.errors,
        missingFields: r.missingFields
      }))
    };

    // Write report
    const reportPath = path.join(__dirname, 'scrape-benchmark-report.json');
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));

    console.log('\n========== SCRAPE BENCHMARK REPORT ==========');
    console.log(`Success Rate: ${report.summary.successRate}`);
    console.log(`Target: ≥ 95% ${report.summary.meetsTarget ? '✅' : '❌'}`);
    console.log(`Average Duration: ${report.summary.avgDuration}`);
    console.log(`\nStrategy Distribution:`, strategyCounts);
    console.log('\nBy Complexity:');
    report.byComplexity.forEach(c => {
      console.log(`  ${c.level}: ${c.rate} (${c.success}/${c.total})`);
    });
    console.log('=============================================\n');

    // Final assertion
    expect(successRate).toBeGreaterThanOrEqual(95);
  });
});

describe('Strategy Routing Benchmark', () => {
  const testUrl = 'https://mp.weixin.qq.com/s?__biz=MzA5NjEyMDUyMA==&mid=2655711234&idx=1&sn=abc123';

  test('fast strategy completes quickly', async () => {
    const scraper = new WechatArticleScraper();
    const start = Date.now();

    const result = await scraper.scrape(testUrl, { strategy: 'fast' });
    const duration = Date.now() - start;

    expect(duration).toBeLessThan(5000); // Fast should complete in < 5s
    expect(result.strategy).toBe('fast');
  });

  test('adaptive strategy falls back correctly', async () => {
    const scraper = new WechatArticleScraper();

    // This URL might fail fast, should fallback to stable
    const result = await scraper.scrape(testUrl, { strategy: 'adaptive' });

    expect(['fast', 'stable', 'reliable', 'jina_ai']).toContain(result.strategy);
    expect(result.content).toBeTruthy();
  });

  test('jina_ai fallback always works', async () => {
    const scraper = new WechatArticleScraper();

    const result = await scraper.scrape(testUrl, { strategy: 'jina_ai' });

    expect(result.strategy).toBe('jina_ai');
    expect(result.content).toBeTruthy();
  });
});

// Standalone benchmark runner
export async function runBenchmark(): Promise<void> {
  console.log('Starting WeChat Scraper Benchmark...\n');

  const results: BenchmarkResult[] = [];
  const scraper = new WechatArticleScraper();

  for (const article of dataset.articles) {
    const startTime = Date.now();

    try {
      const result = await scraper.scrape(article.url, {
        strategy: 'adaptive',
        timeout: 30000
      });

      results.push({
        articleId: article.id,
        url: article.url,
        success: result.status === ContentStatus.SUCCESS,
        strategy: result.strategy || 'unknown',
        duration: Date.now() - startTime,
        fields: Object.keys(result).filter(k => result[k as keyof typeof result]),
        missingFields: [],
        errors: result.errors || [],
        contentStatus: result.status
      });
    } catch (error) {
      results.push({
        articleId: article.id,
        url: article.url,
        success: false,
        strategy: 'failed',
        duration: Date.now() - startTime,
        fields: [],
        missingFields: article.expected_fields,
        errors: [error instanceof Error ? error.message : 'Unknown error']
      });
    }

    // Progress indicator
    if (results.length % 10 === 0) {
      console.log(`Progress: ${results.length}/100`);
    }
  }

  // Generate report
  const total = results.length;
  const successful = results.filter(r => r.success).length;
  const successRate = (successful / total) * 100;

  console.log('\n========== FINAL BENCHMARK RESULTS ==========');
  console.log(`Total Articles: ${total}`);
  console.log(`Successful: ${successful}`);
  console.log(`Success Rate: ${successRate.toFixed(2)}%`);
  console.log(`Target: ≥ 95% ${successRate >= 95 ? '✅ PASSED' : '❌ FAILED'}`);
  console.log('=============================================\n');
}

// CLI entry point
if (require.main === module) {
  runBenchmark().catch(console.error);
}
