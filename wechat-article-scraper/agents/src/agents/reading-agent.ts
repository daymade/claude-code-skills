/**
 * Reading Agent - 阅读洞察提取Agent
 *
 * 使用 Claude Agent SDK (JS/TS) + Kimi API
 * 参考世界级框架: Readwise / Matter / Glasp 的阅读工作流
 *
 * BASE URL: https://api.kimi.com/coding/
 * Model: kimi-for-coding
 */

import Anthropic from '@anthropic-ai/sdk';
import { Agent } from '../core/agent';
import { Tool } from '../core/types';

const anthropic = new Anthropic({
  apiKey: process.env.KIMI_API_KEY,
  baseURL: 'https://api.kimi.com/coding/',
});

interface ReadingSession {
  articleId: string;
  articleTitle: string;
  articleContent: string;
  annotations: Array<{
    quote: string;
    comment?: string;
    tags: string[];
  }>;
  timeSpent: number; // seconds
  progress: number; // 0-100
}

interface Insight {
  keyTakeaways: string[];
  memorableQuotes: string[];
  actionItems: string[];
  connections: string[];
  summary: string;
}

export class ReadingAgent extends Agent {
  name = 'ReadingAgent';
  description = '从阅读内容和标注中提取洞察、生成笔记、推荐相关阅读';

  tools: Tool[] = [
    {
      name: 'extract_insights',
      description: '从阅读内容和标注中提取关键洞察',
      parameters: {
        type: 'object',
        properties: {
          session: {
            type: 'object',
            description: '阅读会话数据',
          },
          focus: {
            type: 'string',
            enum: ['general', 'research', 'business', 'personal'],
            description: '洞察提取的焦点',
          },
        },
        required: ['session'],
      },
      execute: async (params) => {
        return this.extractInsights(params.session as ReadingSession, params.focus as string);
      },
    },
    {
      name: 'generate_reading_notes',
      description: '生成结构化的阅读笔记',
      parameters: {
        type: 'object',
        properties: {
          session: {
            type: 'object',
            description: '阅读会话数据',
          },
          format: {
            type: 'string',
            enum: ['markdown', 'notion', 'obsidian', 'zettelkasten'],
            description: '笔记格式',
          },
        },
        required: ['session'],
      },
      execute: async (params) => {
        return this.generateReadingNotes(
          params.session as ReadingSession,
          params.format as string
        );
      },
    },
    {
      name: 'find_related_articles',
      description: '基于阅读内容推荐相关文章',
      parameters: {
        type: 'object',
        properties: {
          articleId: {
            type: 'string',
            description: '当前文章ID',
          },
          articleContent: {
            type: 'string',
            description: '文章内容',
          },
          limit: {
            type: 'number',
            description: '推荐数量',
            default: 5,
          },
        },
        required: ['articleId', 'articleContent'],
      },
      execute: async (params) => {
        return this.findRelatedArticles(
          params.articleId as string,
          params.articleContent as string,
          params.limit as number
        );
      },
    },
    {
      name: 'generate_daily_review',
      description: '生成每日阅读回顾',
      parameters: {
        type: 'object',
        properties: {
          sessions: {
            type: 'array',
            description: '今日所有阅读会话',
          },
        },
        required: ['sessions'],
      },
      execute: async (params) => {
        return this.generateDailyReview(params.sessions as ReadingSession[]);
      },
    },
  ];

  async extractInsights(session: ReadingSession, focus: string = 'general'): Promise<Insight> {
    const systemPrompt = `你是一个专业的阅读洞察提取助手。你的任务是从用户的阅读内容和标注中提取有价值的洞察。

请分析:
1. 关键要点 - 文章的核心观点
2. 金句摘录 - 值得记住的句子(优先使用用户的标注)
3. 行动项 - 可以实践的建议
4. 关联思考 - 与其他知识的连接

焦点: ${focus}
${focus === 'research' ? '重点关注研究方法、数据来源、论证逻辑' : ''}
${focus === 'business' ? '重点关注商业模式、市场洞察、运营策略' : ''}
${focus === 'personal' ? '重点关注个人成长、生活建议、思维启发' : ''}

输出格式为JSON。`;

    const userContent = `
文章标题: ${session.articleTitle}

文章内容(前3000字):
${session.articleContent.substring(0, 3000)}

用户标注:
${session.annotations.map((a, i) => `
标注${i + 1}:
- 原文: "${a.quote}"
- 批注: ${a.comment || '无'}
- 标签: ${a.tags.join(', ') || '无'}
`).join('\n')}

阅读时间: ${Math.round(session.timeSpent / 60)}分钟
阅读进度: ${session.progress}%
`;

    const response = await anthropic.messages.create({
      model: 'kimi-for-coding',
      max_tokens: 2000,
      system: systemPrompt,
      messages: [{ role: 'user', content: userContent }],
    });

    const content = response.content[0].type === 'text' ? response.content[0].text : '';

    try {
      // Extract JSON from response
      const jsonMatch = content.match(/```json\n?([\s\S]*?)\n?```/) || content.match(/({[\s\S]*})/);
      const jsonStr = jsonMatch ? jsonMatch[1] : content;
      return JSON.parse(jsonStr) as Insight;
    } catch (e) {
      // Fallback: parse manually
      return this.parseInsightFromText(content);
    }
  }

  async generateReadingNotes(
    session: ReadingSession,
    format: string = 'markdown'
  ): Promise<string> {
    const formatInstructions: Record<string, string> = {
      markdown: '标准Markdown格式，使用标题、列表、引用',
      notion: 'Notion兼容格式，使用toggle列表和数据库格式',
      obsidian: 'Obsidian兼容格式，使用wiki链接和标签',
      zettelkasten: 'Zettelkasten卡片格式，包含元数据和连接',
    };

    const systemPrompt = `你是一个专业的笔记生成助手。根据用户的阅读内容和标注，生成高质量的阅读笔记。

格式要求: ${formatInstructions[format] || formatInstructions.markdown}

笔记结构:
1. 元数据(标题、作者、阅读日期)
2. 核心观点摘要
3. 详细笔记(基于用户标注展开)
4. 思考与反思
5. 行动项
6. 相关链接和标签

保持简洁、结构化、易于回顾。`;

    const userContent = `
文章标题: ${session.articleTitle}

文章内容摘要:
${session.articleContent.substring(0, 2000)}

用户标注:
${session.annotations.map((a, i) => `
[标注${i + 1}] ${a.comment || a.quote}
`).join('\n')}

阅读时长: ${Math.round(session.timeSpent / 60)}分钟
`;

    const response = await anthropic.messages.create({
      model: 'kimi-for-coding',
      max_tokens: 3000,
      system: systemPrompt,
      messages: [{ role: 'user', content: userContent }],
    });

    return response.content[0].type === 'text' ? response.content[0].text : '';
  }

  async findRelatedArticles(
    articleId: string,
    articleContent: string,
    limit: number = 5
  ): Promise<Array<{ id: string; title: string; relevance: number; reason: string }>> {
    // This would query the database for related articles
    // For now, returning a mock implementation
    const systemPrompt = `基于给定的文章内容，提取关键主题和标签，用于推荐相关文章。

输出JSON格式:
{
  "themes": ["主题1", "主题2"],
  "keywords": ["关键词1", "关键词2"],
  "complexity": "basic|intermediate|advanced"
}`;

    const response = await anthropic.messages.create({
      model: 'kimi-for-coding',
      max_tokens: 500,
      system: systemPrompt,
      messages: [
        {
          role: 'user',
          content: `分析这篇文章的主题和关键词:\n\n${articleContent.substring(0, 1500)}`,
        },
      ],
    });

    const content = response.content[0].type === 'text' ? response.content[0].text : '';

    // In real implementation, use these themes to query the database
    // Return mock data for now
    return [
      {
        id: 'related-1',
        title: '相关文章示例 1',
        relevance: 0.92,
        reason: '主题高度相关',
      },
      {
        id: 'related-2',
        title: '相关文章示例 2',
        relevance: 0.85,
        reason: '同一作者',
      },
    ].slice(0, limit);
  }

  async generateDailyReview(sessions: ReadingSession[]): Promise<{
    summary: string;
    keyInsights: string[];
    quotes: string[];
    connections: string[];
  }> {
    const totalTime = sessions.reduce((sum, s) => sum + s.timeSpent, 0);
    const totalAnnotations = sessions.reduce((sum, s) => sum + s.annotations.length, 0);

    const systemPrompt = `生成今日阅读回顾。总结一天的阅读收获，突出关键洞察，并建立文章间的连接。

要求:
- 简洁但富有洞察
- 突出跨文章的共同主题
- 提供明日阅读建议
- 使用中文输出`;

    const userContent = `
今日阅读统计:
- 阅读文章: ${sessions.length}篇
- 总阅读时间: ${Math.round(totalTime / 60)}分钟
- 总标注数: ${totalAnnotations}条

阅读内容:
${sessions
  .map(
    (s) => `
《${s.articleTitle}》
- 阅读进度: ${s.progress}%
- 标注: ${s.annotations.length}条
- 金句: ${s.annotations
      .filter((a) => a.tags.includes('quote'))
      .map((a) => `"${a.quote.substring(0, 50)}..."`)
      .join('; ')}
`
  )
  .join('\n---\n')}
`;

    const response = await anthropic.messages.create({
      model: 'kimi-for-coding',
      max_tokens: 1500,
      system: systemPrompt,
      messages: [{ role: 'user', content: userContent }],
    });

    const content = response.content[0].type === 'text' ? response.content[0].text : '';

    // Parse structured data from response
    return {
      summary: content.split('\n')[0] || '今日阅读回顾',
      keyInsights: this.extractListItems(content, '关键洞察'),
      quotes: sessions.flatMap((s) =>
        s.annotations.filter((a) => a.quote.length > 10).map((a) => a.quote)
      ),
      connections: this.extractListItems(content, '连接'),
    };
  }

  private parseInsightFromText(text: string): Insight {
    const extractSection = (marker: string): string[] => {
      const regex = new RegExp(`${marker}[：:]([^]*?)(?=\n\d+\.|$)`, 'i');
      const match = text.match(regex);
      if (match) {
        return match[1]
          .split('\n')
          .map((l) => l.replace(/^[-•*\d.]+\s*/, '').trim())
          .filter((l) => l.length > 0);
      }
      return [];
    };

    return {
      keyTakeaways: extractSection('关键要点'),
      memorableQuotes: extractSection('金句'),
      actionItems: extractSection('行动'),
      connections: extractSection('关联'),
      summary: text.substring(0, 200),
    };
  }

  private extractListItems(text: string, section: string): string[] {
    const lines = text.split('\n');
    const items: string[] = [];
    let inSection = false;

    for (const line of lines) {
      if (line.includes(section)) {
        inSection = true;
        continue;
      }
      if (inSection) {
        if (line.match(/^\d+\./) || line.match(/^[-•]/)) {
          items.push(line.replace(/^\d+\.\s*/, '').replace(/^[-•]\s*/, ''));
        } else if (line.trim() === '' || line.match(/^\d+\./)) {
          inSection = false;
        }
      }
    }

    return items;
  }
}
