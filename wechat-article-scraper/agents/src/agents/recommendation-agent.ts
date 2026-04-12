/**
 * Recommendation Agent
 * Intelligent content recommendation based on reading patterns and content similarity
 */

import { kimiClient } from '../lib/kimi-client.js';
import { db, Article } from '../lib/db.js';

export interface RecommendationRequest {
  basedOn?: {
    articleId?: string;
    author?: string;
    topic?: string;
  };
  readingHistory?: string[]; // Article IDs
  limit?: number;
  diversify?: boolean;
}

export interface Recommendation {
  article: Article;
  reason: string;
  similarityScore: number;
  category: 'similar_content' | 'same_author' | 'trending' | 'discovery';
}

export class RecommendationAgent {
  private systemPrompt = `You are a content recommendation engine for WeChat articles.
Your goal is to help users discover relevant content they'll find valuable.

Recommendation principles:
1. Content similarity: Same topics, themes, or writing style
2. Author consistency: More from authors the user has enjoyed
3. Trending: Popular content they might have missed
4. Discovery: Related but different perspectives

Explain WHY each recommendation is relevant.`;

  async getRecommendations(
    request: RecommendationRequest
  ): Promise<Recommendation[]> {
    await db.connect();

    try {
      const candidates: Array<{
        article: Article;
        score: number;
        category: Recommendation['category'];
      }> = [];

      // Strategy 1: Similar content
      if (request.basedOn?.articleId) {
        const similar = await this.findSimilarContent(
          request.basedOn.articleId,
          request.limit || 5
        );
        candidates.push(
          ...similar.map((s) => ({ ...s, category: 'similar_content' as const }))
        );
      }

      // Strategy 2: Same author
      if (request.basedOn?.author) {
        const authorArticles = await this.findAuthorContent(
          request.basedOn.author,
          request.readingHistory || [],
          request.limit || 5
        );
        candidates.push(
          ...authorArticles.map((a) => ({ ...a, category: 'same_author' as const }))
        );
      }

      // Strategy 3: Topic-based
      if (request.basedOn?.topic) {
        const topicArticles = await this.findTopicContent(
          request.basedOn.topic,
          request.limit || 5
        );
        candidates.push(
          ...topicArticles.map((t) => ({ ...t, category: 'similar_content' as const }))
        );
      }

      // Strategy 4: Based on reading history
      if (request.readingHistory && request.readingHistory.length > 0) {
        const historyRecommendations = await this.findBasedOnHistory(
          request.readingHistory,
          request.limit || 5
        );
        candidates.push(
          ...historyRecommendations.map((h) => ({
            ...h,
            category: 'discovery' as const,
          }))
        );
      }

      // Strategy 5: Trending (fallback)
      if (candidates.length < (request.limit || 5)) {
        const trending = await this.findTrending(
          (request.limit || 5) - candidates.length
        );
        candidates.push(
          ...trending.map((t) => ({ ...t, category: 'trending' as const }))
        );
      }

      // Deduplicate and rank
      const unique = this.deduplicate(candidates);
      const ranked = this.rankRecommendations(unique, request);

      // Generate explanations
      const withExplanations = await this.generateExplanations(
        ranked.slice(0, request.limit || 5),
        request
      );

      return withExplanations;
    } finally {
      await db.close();
    }
  }

  private async findSimilarContent(
    articleId: string,
    limit: number
  ): Promise<Array<{ article: Article; score: number }>> {
    const article = await db.getArticleById(articleId);
    if (!article) return [];

    // Extract keywords from title and content
    const keywords = await this.extractKeywords(
      `${article.title} ${article.content.substring(0, 500)}`
    );

    const results: Array<{ article: Article; score: number }> = [];

    for (const keyword of keywords.slice(0, 3)) {
      const matches = await db.searchArticles(keyword, { limit: limit + 1 });

      for (const match of matches) {
        if (match.article.id !== articleId) {
          const existing = results.find(
            (r) => r.article.id === match.article.id
          );
          if (existing) {
            existing.score += match.relevanceScore;
          } else {
            results.push({
              article: match.article,
              score: match.relevanceScore,
            });
          }
        }
      }
    }

    return results.sort((a, b) => b.score - a.score).slice(0, limit);
  }

  private async findAuthorContent(
    author: string,
    excludeIds: string[],
    limit: number
  ): Promise<Array<{ article: Article; score: number }>> {
    const articles = await db.getArticlesByAuthor(author, limit + excludeIds.length);

    return articles
      .filter((a) => !excludeIds.includes(a.id))
      .slice(0, limit)
      .map((a) => ({ article: a, score: 80 })); // Base score for same author
  }

  private async findTopicContent(
    topic: string,
    limit: number
  ): Promise<Array<{ article: Article; score: number }>> {
    const results = await db.searchArticles(topic, { limit });
    return results.map((r) => ({
      article: r.article,
      score: r.relevanceScore,
    }));
  }

  private async findBasedOnHistory(
    historyIds: string[],
    limit: number
  ): Promise<Array<{ article: Article; score: number }>> {
    // Get keywords from reading history
    const allKeywords: string[] = [];

    for (const id of historyIds.slice(-5)) {
      const article = await db.getArticleById(id);
      if (article) {
        const keywords = await this.extractKeywords(
          `${article.title} ${article.content.substring(0, 300)}`
        );
        allKeywords.push(...keywords);
      }
    }

    // Find frequent keywords
    const keywordFreq = allKeywords.reduce((acc, k) => {
      acc[k] = (acc[k] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);

    const topKeywords = Object.entries(keywordFreq)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([k]) => k);

    const results: Array<{ article: Article; score: number }> = [];

    for (const keyword of topKeywords) {
      const matches = await db.searchArticles(keyword, {
        limit: limit + historyIds.length,
      });

      for (const match of matches) {
        if (!historyIds.includes(match.article.id)) {
          const existing = results.find(
            (r) => r.article.id === match.article.id
          );
          if (existing) {
            existing.score += match.relevanceScore;
          } else {
            results.push({
              article: match.article,
              score: match.relevanceScore,
            });
          }
        }
      }
    }

    return results.sort((a, b) => b.score - a.score).slice(0, limit);
  }

  private async findTrending(
    limit: number
  ): Promise<Array<{ article: Article; score: number }>> {
    const recent = await db.getRecentArticles(limit * 2);

    // Score by read count and recency
    return recent
      .map((a) => ({
        article: a,
        score: (a.readCount || 0) / 100, // Normalize read count
      }))
      .sort((a, b) => b.score - a.score)
      .slice(0, limit);
  }

  private async extractKeywords(text: string): Promise<string[]> {
    const response = await kimiClient.sendMessage(
      [
        {
          role: 'user',
          content: `Extract 5 key topics/keywords from this text:
${text.substring(0, 500)}

Return only a JSON array of keywords.`,
        },
      ],
      {
        temperature: 0.1,
        maxTokens: 100,
      }
    );

    try {
      return JSON.parse(response.content);
    } catch {
      return text
        .toLowerCase()
        .split(/\s+/)
        .filter((w) => w.length > 3)
        .slice(0, 5);
    }
  }

  private deduplicate(
    candidates: Array<{
      article: Article;
      score: number;
      category: Recommendation['category'];
    }>
  ): typeof candidates {
    const seen = new Set<string>();
    return candidates.filter((c) => {
      if (seen.has(c.article.id)) return false;
      seen.add(c.article.id);
      return true;
    });
  }

  private rankRecommendations(
    candidates: Array<{
      article: Article;
      score: number;
      category: Recommendation['category'];
    }>,
    request: RecommendationRequest
  ): typeof candidates {
    // Boost scores based on category priority
    const categoryPriority = {
      similar_content: 1.5,
      same_author: 1.3,
      trending: 1.0,
      discovery: 1.2,
    };

    return candidates
      .map((c) => ({
        ...c,
        score: c.score * (categoryPriority[c.category] || 1),
      }))
      .sort((a, b) => b.score - a.score);
  }

  private async generateExplanations(
    recommendations: Array<{
      article: Article;
      score: number;
      category: Recommendation['category'];
    }>,
    request: RecommendationRequest
  ): Promise<Recommendation[]> {
    const context = recommendations
      .map(
        (r, i) =>
          `${i + 1}. "${r.article.title}" by ${r.article.author} (${
            r.category
          }, score: ${r.score.toFixed(1)})`
      )
      .join('\n');

    const baseInfo = request.basedOn
      ? `Based on: ${
          request.basedOn.articleId
            ? 'article ID ' + request.basedOn.articleId
            : request.basedOn.author
            ? 'author ' + request.basedOn.author
            : 'topic ' + request.basedOn.topic
        }`
      : request.readingHistory
      ? `Reading history: ${request.readingHistory.length} articles`
      : 'Trending content';

    const response = await kimiClient.sendMessage(
      [
        {
          role: 'user',
          content: `Generate brief, personalized explanations for these recommendations:

${baseInfo}

Recommendations:
${context}

Return JSON format:
{
  "explanations": [
    "Why this article is recommended - personalize for each",
    ...
  ]
}

Keep each explanation to 1 sentence. Be specific about why it's relevant.`,
        },
      ],
      {
        system: this.systemPrompt,
        temperature: 0.4,
      }
    );

    let explanations: string[] = [];
    try {
      const parsed = JSON.parse(response.content);
      explanations = parsed.explanations || [];
    } catch {
      explanations = recommendations.map(() => 'Recommended based on your interests');
    }

    return recommendations.map((r, i) => ({
      article: r.article,
      reason: explanations[i] || 'Recommended for you',
      similarityScore: Math.min(100, r.score),
      category: r.category,
    }));
  }
}

export const recommendationAgent = new RecommendationAgent();
