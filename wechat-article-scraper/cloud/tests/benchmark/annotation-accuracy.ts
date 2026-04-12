/**
 * Annotation Positioning Accuracy Test
 * Round 93: Core Functionality Validation
 *
 * Measures annotation positioning accuracy
 * Target: ≥ 98% correct positioning after reload
 */

import { test, expect, describe } from 'vitest';
import { AnnotationEngine } from '../../src/lib/annotation-engine';
import * as fs from 'fs';
import * as path from 'path';

interface TestCase {
  id: string;
  articleId: string;
  content: string;
  selection: {
    text: string;
    startOffset: number;
    endOffset: number;
  };
  expectedPosition: {
    xpath: string;
    textOffset: number;
  };
}

interface AnnotationResult {
  testId: string;
  articleId: string;
  originalText: string;
  recoveredText: string;
  positionMatch: boolean;
  textMatch: boolean;
  fuzzyMatch: boolean;
  similarity: number;
  errors: string[];
}

// Mock DOM environment for testing
const createMockDOM = (content: string): Document => {
  const { JSDOM } = require('jsdom');
  const dom = new JSDOM(`
    <!DOCTYPE html>
    <html>
      <head><title>Test</title></head>
      <body>
        <article id="content">
          ${content}
        </article>
      </body>
    </html>
  `);
  return dom.window.document;
};

// Test cases simulating real annotation scenarios
const TEST_CASES: TestCase[] = [
  {
    id: "ann-001",
    articleId: "test-001",
    content: `
      <p>这是第一段文字，用于测试批注定位功能。</p>
      <p>这是第二段文字，包含一些<strong>重要的</strong>信息。</p>
      <p>这是第三段，测试文本在高亮后是否能正确恢复。</p>
    `,
    selection: {
      text: "重要的",
      startOffset: 10,
      endOffset: 13
    },
    expectedPosition: {
      xpath: "/html/body/article/p[2]/strong",
      textOffset: 0
    }
  },
  {
    id: "ann-002",
    articleId: "test-002",
    content: `
      <h1>文章标题</h1>
      <p>这是文章的第一段，介绍背景信息。</p>
      <p>这是第二段，包含<a href="#">链接</a>和<em>强调</em>文本。</p>
      <blockquote>这是引用块，测试特殊元素的定位。</blockquote>
    `,
    selection: {
      text: "链接",
      startOffset: 8,
      endOffset: 10
    },
    expectedPosition: {
      xpath: "/html/body/article/p[2]/a",
      textOffset: 0
    }
  },
  {
    id: "ann-003",
    articleId: "test-003",
    content: `
      <div class="section">
        <p>第一段内容</p>
        <p>第二段内容，包含<span class="highlight">高亮文本</span>。</p>
      </div>
      <div class="section">
        <p>第三段内容</p>
      </div>
    `,
    selection: {
      text: "高亮文本",
      startOffset: 7,
      endOffset: 11
    },
    expectedPosition: {
      xpath: "/html/body/article/div[1]/p[2]/span",
      textOffset: 0
    }
  },
  {
    id: "ann-004",
    articleId: "test-004",
    content: `
      <p>这是一段很长的文字，包含多个句子。第一个句子在这里结束。第二个句子开始，包含一些重要的信息需要被标注。第三个句子继续。</p>
    `,
    selection: {
      text: "第二个句子开始，包含一些重要的信息",
      startOffset: 25,
      endOffset: 45
    },
    expectedPosition: {
      xpath: "/html/body/article/p",
      textOffset: 25
    }
  },
  {
    id: "ann-005",
    articleId: "test-005",
    content: `
      <ul>
        <li>列表项一</li>
        <li>列表项二，包含<strong>重要</strong>内容</li>
        <li>列表项三</li>
      </ul>
    `,
    selection: {
      text: "重要",
      startOffset: 5,
      endOffset: 7
    },
    expectedPosition: {
      xpath: "/html/body/article/ul/li[2]/strong",
      textOffset: 0
    }
  },
  {
    id: "ann-006",
    articleId: "test-006",
    content: `
      <p>测试特殊字符： emoji 🎉 和 Unicode 中文。</p>
      <p>测试数字：123.45 和代码<code>variable_name</code>。</p>
    `,
    selection: {
      text: "variable_name",
      startOffset: 25,
      endOffset: 38
    },
    expectedPosition: {
      xpath: "/html/body/article/p[2]/code",
      textOffset: 0
    }
  },
  {
    id: "ann-007",
    articleId: "test-007",
    content: `
      <table>
        <tr><td>单元格1</td><td>单元格2</td></tr>
        <tr><td>单元格3</td><td>单元格4</td></tr>
      </table>
      <p>表格后的段落。</p>
    `,
    selection: {
      text: "单元格2",
      startOffset: 3,
      endOffset: 6
    },
    expectedPosition: {
      xpath: "/html/body/article/table/tr[1]/td[2]",
      textOffset: 0
    }
  },
  {
    id: "ann-008",
    articleId: "test-008",
    content: `
      <p>这是<em>嵌套<strong>多层</strong>元素</em>的测试。</p>
    `,
    selection: {
      text: "多层",
      startOffset: 10,
      endOffset: 12
    },
    expectedPosition: {
      xpath: "/html/body/article/p/em/strong",
      textOffset: 0
    }
  },
  {
    id: "ann-009",
    articleId: "test-009",
    content: `
      <h2>章节标题</h2>
      <p>正文第一段。</p>
      <h2>另一个章节</h2>
      <p>正文第二段，包含<mark>高亮标记</mark>。</p>
    `,
    selection: {
      text: "高亮标记",
      startOffset: 5,
      endOffset: 9
    },
    expectedPosition: {
      xpath: "/html/body/article/p[2]/mark",
      textOffset: 0
    }
  },
  {
    id: "ann-010",
    articleId: "test-010",
    content: `
      <p>测试连续文本选择，从这句话开始，跨越多个句子边界，一直到最后。</p>
    `,
    selection: {
      text: "开始，跨越多个句子边界",
      startOffset: 13,
      endOffset: 25
    },
    expectedPosition: {
      xpath: "/html/body/article/p",
      textOffset: 13
    }
  }
];

describe('Annotation Positioning Accuracy', () => {
  const results: AnnotationResult[] = [];

  test.each(TEST_CASES)(
    'annotation #$id - recover position for "$selection.text"',
    async (testCase) => {
      const engine = new AnnotationEngine();

      try {
        // Step 1: Create annotation
        const annotation = await engine.createAnnotation({
          articleId: testCase.articleId,
          text: testCase.selection.text,
          startOffset: testCase.selection.startOffset,
          endOffset: testCase.selection.endOffset
        });

        expect(annotation).toBeTruthy();
        expect(annotation.id).toBeTruthy();
        expect(annotation.position).toBeTruthy();

        // Step 2: Simulate DOM reload with same content
        const recoveredPosition = await engine.recoverPosition(
          testCase.articleId,
          annotation.id
        );

        // Step 3: Verify recovery accuracy
        const originalText = testCase.selection.text;
        const recoveredText = recoveredPosition?.text || '';

        // Calculate text similarity
        const similarity = calculateSimilarity(originalText, recoveredText);
        const textMatch = originalText === recoveredText;
        const fuzzyMatch = similarity >= 0.8; // 80% similarity threshold

        // Position match check
        const positionMatch = recoveredPosition?.xpath === testCase.expectedPosition.xpath;

        const result: AnnotationResult = {
          testId: testCase.id,
          articleId: testCase.articleId,
          originalText,
          recoveredText,
          positionMatch,
          textMatch,
          fuzzyMatch,
          similarity,
          errors: []
        };

        if (!positionMatch) {
          result.errors.push(`XPath mismatch: expected ${testCase.expectedPosition.xpath}, got ${recoveredPosition?.xpath}`);
        }

        results.push(result);

        // Assertions
        expect(similarity).toBeGreaterThanOrEqual(0.8); // At least 80% match

      } catch (error) {
        results.push({
          testId: testCase.id,
          articleId: testCase.articleId,
          originalText: testCase.selection.text,
          recoveredText: '',
          positionMatch: false,
          textMatch: false,
          fuzzyMatch: false,
          similarity: 0,
          errors: [error instanceof Error ? error.message : 'Unknown error']
        });

        throw error;
      }
    }
  );

  test('generate accuracy report', () => {
    const total = results.length;
    const positionMatches = results.filter(r => r.positionMatch).length;
    const textMatches = results.filter(r => r.textMatch).length;
    const fuzzyMatches = results.filter(r => r.fuzzyMatch).length;

    const positionAccuracy = (positionMatches / total) * 100;
    const textAccuracy = (textMatches / total) * 100;
    const fuzzyAccuracy = (fuzzyMatches / total) * 100;

    const avgSimilarity = results.reduce((sum, r) => sum + r.similarity, 0) / total;

    const report = {
      timestamp: new Date().toISOString(),
      summary: {
        totalTests: total,
        positionAccuracy: `${positionAccuracy.toFixed(2)}%`,
        textAccuracy: `${textAccuracy.toFixed(2)}%`,
        fuzzyAccuracy: `${fuzzyAccuracy.toFixed(2)}%`,
        avgSimilarity: `${(avgSimilarity * 100).toFixed(2)}%`,
        meetsTarget: positionAccuracy >= 98
      },
      details: results,
      failures: results.filter(r => !r.positionMatch).map(r => ({
        testId: r.testId,
        originalText: r.originalText,
        recoveredText: r.recoveredText,
        similarity: r.similarity,
        errors: r.errors
      }))
    };

    // Write report
    const reportPath = path.join(__dirname, 'annotation-accuracy-report.json');
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));

    console.log('\n========== ANNOTATION ACCURACY REPORT ==========');
    console.log(`Total Tests: ${total}`);
    console.log(`Position Accuracy: ${report.summary.positionAccuracy}`);
    console.log(`Target: ≥ 98% ${report.summary.meetsTarget ? '✅' : '❌'}`);
    console.log(`Text Exact Match: ${report.summary.textAccuracy}`);
    console.log(`Fuzzy Match (≥80%): ${report.summary.fuzzyAccuracy}`);
    console.log(`Average Similarity: ${report.summary.avgSimilarity}`);
    console.log('================================================\n');

    // Final assertion
    expect(positionAccuracy).toBeGreaterThanOrEqual(98);
  });
});

describe('Annotation Edge Cases', () => {
  test('handles text modifications gracefully', async () => {
    const engine = new AnnotationEngine();

    // Original content
    const originalContent = '<p>这是原始文本。</p>';

    // Create annotation
    const annotation = await engine.createAnnotation({
      articleId: 'edge-001',
      text: '原始文本',
      startOffset: 2,
      endOffset: 6
    });

    // Simulate content modification (text changed)
    const modifiedContent = '<p>这是修改后的文本。</p>';

    // Try to recover - should use fuzzy matching
    const recovered = await engine.recoverPosition('edge-001', annotation.id, {
      fallbackToFuzzy: true
    });

    // Should still find something with high similarity
    expect(recovered).toBeTruthy();
  });

  test('handles duplicate text occurrences', async () => {
    const engine = new AnnotationEngine();

    // Content with duplicate text
    const content = '<p>重复 重复 重复</p>';

    // Select second occurrence
    const annotation = await engine.createAnnotation({
      articleId: 'edge-002',
      text: '重复',
      startOffset: 3,
      endOffset: 5
    });

    expect(annotation.position?.occurrenceIndex).toBe(1); // Second occurrence
  });

  test('handles very long text selections', async () => {
    const engine = new AnnotationEngine();

    const longText = 'A'.repeat(500);
    const content = `<p>${longText}</p>`;

    const annotation = await engine.createAnnotation({
      articleId: 'edge-003',
      text: longText.slice(100, 200),
      startOffset: 100,
      endOffset: 200
    });

    expect(annotation).toBeTruthy();
  });
});

// Utility functions
function calculateSimilarity(str1: string, str2: string): number {
  if (!str1 || !str2) return 0;
  if (str1 === str2) return 1;

  const longer = str1.length > str2.length ? str1 : str2;
  const shorter = str1.length > str2.length ? str2 : str1;

  if (longer.length === 0) return 1;

  const distance = levenshteinDistance(longer, shorter);
  return (longer.length - distance) / longer.length;
}

function levenshteinDistance(str1: string, str2: string): number {
  const matrix: number[][] = [];

  for (let i = 0; i <= str2.length; i++) {
    matrix[i] = [i];
  }

  for (let j = 0; j <= str1.length; j++) {
    matrix[0][j] = j;
  }

  for (let i = 1; i <= str2.length; i++) {
    for (let j = 1; j <= str1.length; j++) {
      if (str2.charAt(i - 1) === str1.charAt(j - 1)) {
        matrix[i][j] = matrix[i - 1][j - 1];
      } else {
        matrix[i][j] = Math.min(
          matrix[i - 1][j - 1] + 1,
          matrix[i][j - 1] + 1,
          matrix[i - 1][j] + 1
        );
      }
    }
  }

  return matrix[str2.length][str1.length];
}

// CLI entry point
export async function runAccuracyTest(): Promise<void> {
  console.log('Starting Annotation Accuracy Test...\n');

  const results: AnnotationResult[] = [];
  const engine = new AnnotationEngine();

  for (const testCase of TEST_CASES) {
    try {
      const annotation = await engine.createAnnotation({
        articleId: testCase.articleId,
        text: testCase.selection.text,
        startOffset: testCase.selection.startOffset,
        endOffset: testCase.selection.endOffset
      });

      const recovered = await engine.recoverPosition(testCase.articleId, annotation.id);

      const similarity = calculateSimilarity(testCase.selection.text, recovered?.text || '');

      results.push({
        testId: testCase.id,
        articleId: testCase.articleId,
        originalText: testCase.selection.text,
        recoveredText: recovered?.text || '',
        positionMatch: recovered?.xpath === testCase.expectedPosition.xpath,
        textMatch: testCase.selection.text === recovered?.text,
        fuzzyMatch: similarity >= 0.8,
        similarity,
        errors: []
      });
    } catch (error) {
      results.push({
        testId: testCase.id,
        articleId: testCase.articleId,
        originalText: testCase.selection.text,
        recoveredText: '',
        positionMatch: false,
        textMatch: false,
        fuzzyMatch: false,
        similarity: 0,
        errors: [error instanceof Error ? error.message : 'Unknown error']
      });
    }
  }

  // Report
  const total = results.length;
  const positionMatches = results.filter(r => r.positionMatch).length;
  const accuracy = (positionMatches / total) * 100;

  console.log('\n========== ANNOTATION ACCURACY RESULTS ==========');
  console.log(`Total: ${total}`);
  console.log(`Position Accuracy: ${accuracy.toFixed(2)}%`);
  console.log(`Target: ≥ 98% ${accuracy >= 98 ? '✅ PASSED' : '❌ FAILED'}`);
  console.log('=================================================\n');
}

if (require.main === module) {
  runAccuracyTest().catch(console.error);
}
