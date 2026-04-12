/**
 * Smart Search Agent
 * Uses LLM to understand search intent and retrieve relevant articles
 */

import { kimiClient } from '../lib/kimi-client.js';
import { db, Article, SearchResult } from '../lib/db.js';

export interface SearchQuery {
  query: string;
  filters?: {
    author?: string;
    startDate?: string;
    endDate?: string;
    minReadCount?: number;
  };
  limit?: number;
}

export interface SearchResponse {
  results: Array<{
    article: Article;
    relevanceScore: number;
    explanation: string;
  }>;
  summary: string;
  relatedKeywords: string[];
  totalFound: number;
}

const SEARCH_TOOLS = [
  {
    name: 'search_articles',
    description: 'Search articles by keywords in title, content, or author',
    input_schema: {
      type: 'object' as const,
      properties: {
        query: { type: 'string', description: 'Search keywords' },
        author: { type: 'string', description: 'Filter by author name (optional)' },
        limit: { type: 'number', description: 'Maximum results (default: 10)' },
      },
      required: ['query'],
    },
  },
  {
    name: 'get_author_articles',
    description: 'Get all articles from a specific author',
    input_schema: {
      type: 'object' as const,
      properties: {
        author: { type: 'string', description: 'Author name' },
        limit: { type: 'number', description: 'Maximum results' },
      },
      required: ['author'],
    },
  },
  {
    name: 'get_article_stats',
    description: 'Get database statistics',
    input_schema: {
      type: 'object' as const,
      properties: {},
      required: [],
    },
  },
];

export class SearchAgent {
  private systemPrompt = `You are an intelligent search assistant for WeChat article database.
Your task is to understand user search intent and retrieve the most relevant articles.

Guidelines:
1. Analyze the user's query to understand what they're looking for
2. Use the available tools to search the database
3. Provide relevant results with explanations of why they match
4. Suggest related keywords or authors if applicable
5. Summarize the findings in a helpful way

When searching:
- Extract key concepts from the query
- Consider synonyms and related terms
- Prioritize recent and high-engagement content
- Provide context for why each result is relevant`;

  async search(request: SearchQuery): Promise<SearchResponse> {
    await db.connect();

    try {
      // Step 1: Use LLM to analyze query and determine search strategy
      const analysis = await this.analyzeQuery(request.query);

      // Step 2: Execute search based on analysis
      const rawResults = await this.executeSearch(analysis, request);

      // Step 3: Use LLM to rank and explain results
      const enrichedResults = await this.enrichResults(request.query, rawResults);

      return enrichedResults;
    } finally {
      await db.close();
    }
  }

  private async analyzeQuery(query: string): Promise<{
    searchTerms: string[];
    intent: 'factual' | 'opinion' | 'trend' | 'author_focused' | 'broad';
    suggestedFilters?: {
      author?: string;
      dateRange?: 'recent' | 'all';
    };
  }> {
    const response = await kimiClient.sendMessage(
      [
        {
          role: 'user',
          content: `Analyze this search query and extract search strategy:

Query: "${query}"

Return a JSON object with:
- searchTerms: array of keywords to search
- intent: one of [factual, opinion, trend, author_focused, broad]
- suggestedFilters: optional author or dateRange hints`,
        },
      ],
      {
        system: this.systemPrompt,
        temperature: 0.2,
      }
    );

    try {
      const parsed = JSON.parse(response.content);
      return {
        searchTerms: parsed.searchTerms || [query],
        intent: parsed.intent || 'broad',
        suggestedFilters: parsed.suggestedFilters,
      };
    } catch {
      // Fallback to simple query
      return {
        searchTerms: [query],
        intent: 'broad',
      };
    }
  }

  private async executeSearch(
    analysis: { searchTerms: string[]; intent: string; suggestedFilters?: any },
    request: SearchQuery
  ): Promise<SearchResult[]> {
    // Combine all search terms
    const combinedQuery = analysis.searchTerms.join(' ');

    // Execute search with filters
    const results = await db.searchArticles(combinedQuery, {
      limit: request.limit || 10,
      author: request.filters?.author || analysis.suggestedFilters?.author,
      startDate: request.filters?.startDate,
      endDate: request.filters?.endDate,
      minReadCount: request.filters?.minReadCount,
    });

    return results;
  }

  private async enrichResults(
    originalQuery: string,
    results: SearchResult[]
  ): Promise<SearchResponse> {
    if (results.length === 0) {
      return {
        results: [],
        summary: 'No articles found matching your query.',
        relatedKeywords: [],
        totalFound: 0,
      };
    }

    // Prepare results for LLM analysis
    const resultsForAnalysis = results.map((r) => ({
      id: r.article.id,
      title: r.article.title,
      author: r.article.author,
      publishTime: r.article.publishTime,
      readCount: r.article.readCount,
      excerpt: r.article.content.substring(0, 200) + '...',
    }));

    const response = await kimiClient.sendMessage(
      [
        {
          role: 'user',
          content: `Analyze these search results for query: "${originalQuery}"

Results:
${JSON.stringify(resultsForAnalysis, null, 2)}

Provide:
1. A brief summary of findings
2. Why each result is relevant (in order)
3. 3-5 related keywords that might help refine the search

Return JSON format:
{
  "summary": "string",
  "explanations": ["explanation for result 1", "explanation for result 2", ...],
  "relatedKeywords": ["keyword1", "keyword2", ...]
}`,
        },
      ],
      {
        system: this.systemPrompt,
        temperature: 0.3,
      }
    );

    let enrichment: {
      summary: string;
      explanations: string[];
      relatedKeywords: string[];
    };

    try {
      enrichment = JSON.parse(response.content);
    } catch {
      enrichment = {
        summary: `Found ${results.length} articles matching your query.`,
        explanations: results.map(() => 'Relevant match'),
        relatedKeywords: [],
      };
    }

    return {
      results: results.map((r, i) => ({
        article: r.article,
        relevanceScore: r.relevanceScore,
        explanation: enrichment.explanations[i] || 'Relevant match',
      })),
      summary: enrichment.summary,
      relatedKeywords: enrichment.relatedKeywords,
      totalFound: results.length,
    };
  }

  /**
   * Natural language search with conversation context
   */
  async conversationalSearch(
    query: string,
    conversationHistory: Array<{ role: 'user' | 'assistant'; content: string }> = []
  ): Promise<{
    response: string;
    results: SearchResult[];
  }> {
    await db.connect();

    try {
      // Get database stats for context
      const stats = await db.getStatistics();

      const systemPrompt = `${this.systemPrompt}

Database Context:
- Total articles: ${stats.totalArticles}
- Total authors: ${stats.totalAuthors}
- Date range: ${stats.dateRange.earliest} to ${stats.dateRange.latest}

You have access to these tools:
- search_articles: Search by keywords
- get_author_articles: Get articles by specific author
- get_article_stats: Get database statistics`;

      const messages = [
        ...conversationHistory,
        { role: 'user' as const, content: query },
      ];

      const response = await kimiClient.sendMessage(messages, {
        system: systemPrompt,
        tools: SEARCH_TOOLS,
        temperature: 0.3,
      });

      // Execute tool calls if any
      let results: SearchResult[] = [];
      if (response.toolCalls && response.toolCalls.length > 0) {
        for (const call of response.toolCalls) {
          switch (call.name) {
            case 'search_articles':
              results = await db.searchArticles(call.input.query, {
                limit: call.input.limit || 10,
                author: call.input.author,
              });
              break;
            case 'get_author_articles':
              const articles = await db.getArticlesByAuthor(
                call.input.author,
                call.input.limit || 10
              );
              results = articles.map((a) => ({
                article: a,
                relevanceScore: 100,
                matchedKeywords: [call.input.author],
              }));
              break;
          }
        }
      }

      return {
        response: response.content,
        results,
      };
    } finally {
      await db.close();
    }
  }
}

export const searchAgent = new SearchAgent();
