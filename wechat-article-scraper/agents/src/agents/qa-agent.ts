/**
 * Question-Answering Agent
 * RAG (Retrieval-Augmented Generation) for article knowledge base
 */

import { kimiClient } from '../lib/kimi-client.js';
import { db, Article } from '../lib/db.js';

export interface Question {
  question: string;
  context?: string;
  maxSources?: number;
}

export interface Answer {
  answer: string;
  sources: Array<{
    article: Article;
    relevantText: string;
    relevanceScore: number;
  }>;
  confidence: 'high' | 'medium' | 'low';
  followUpQuestions: string[];
}

export class QAAgent {
  private systemPrompt = `You are a knowledgeable assistant that answers questions based on WeChat article content.
You must only use the provided article content to answer questions.
If the answer cannot be found in the articles, say so clearly.

Guidelines:
1. Always cite your sources with article titles and authors
2. Synthesize information from multiple articles if needed
3. Be concise but thorough
4. If the question is about trends or opinions, analyze patterns across articles
5. Format your response clearly with headings and bullet points when appropriate

Confidence levels:
- high: Direct answer found in one or more articles
- medium: Partial answer found, some inference required
- low: Limited information, answer is mostly speculation`;

  async ask(question: Question): Promise<Answer> {
    await db.connect();

    try {
      // Step 1: Extract search keywords from question
      const searchKeywords = await this.extractKeywords(question.question);

      // Step 2: Retrieve relevant articles
      const relevantArticles = await this.retrieveArticles(
        searchKeywords,
        question.maxSources || 5
      );

      if (relevantArticles.length === 0) {
        return {
          answer: 'I could not find any relevant articles to answer this question.',
          sources: [],
          confidence: 'low',
          followUpQuestions: this.suggestRelatedQueries(question.question),
        };
      }

      // Step 3: Generate answer based on retrieved content
      const answer = await this.generateAnswer(question, relevantArticles);

      return answer;
    } finally {
      await db.close();
    }
  }

  private async extractKeywords(question: string): Promise<string[]> {
    const response = await kimiClient.sendMessage(
      [
        {
          role: 'user',
          content: `Extract 3-5 search keywords from this question:
"${question}"

Return only a JSON array of keywords, no other text.
Example: ["keyword1", "keyword2", "keyword3"]`,
        },
      ],
      {
        system: 'You extract relevant search keywords from questions.',
        temperature: 0.1,
        maxTokens: 100,
      }
    );

    try {
      const keywords = JSON.parse(response.content);
      if (Array.isArray(keywords)) {
        return keywords;
      }
    } catch {
      // Fallback: split by common words
    }

    // Simple fallback extraction
    return question
      .toLowerCase()
      .replace(/[?.,!]/g, '')
      .split(/\s+/)
      .filter((w) => w.length > 2)
      .slice(0, 5);
  }

  private async retrieveArticles(
    keywords: string[],
    maxResults: number
  ): Promise<
    Array<{
      article: Article;
      relevantParagraphs: string[];
      score: number;
    }>
  > {
    const allResults: Array<{
      article: Article;
      relevantParagraphs: string[];
      score: number;
    }> = [];

    // Search with each keyword and combine results
    for (const keyword of keywords) {
      const results = await db.searchArticles(keyword, { limit: maxResults });

      for (const result of results) {
        const existing = allResults.find(
          (r) => r.article.id === result.article.id
        );

        if (existing) {
          existing.score += result.relevanceScore;
        } else {
          // Extract relevant paragraphs
          const paragraphs = this.extractRelevantParagraphs(
            result.article.content,
            keywords
          );

          allResults.push({
            article: result.article,
            relevantParagraphs: paragraphs,
            score: result.relevanceScore,
          });
        }
      }
    }

    // Sort by score and return top results
    return allResults
      .sort((a, b) => b.score - a.score)
      .slice(0, maxResults);
  }

  private extractRelevantParagraphs(
    content: string,
    keywords: string[]
  ): string[] {
    const paragraphs = content.split(/\n\n+/);
    const relevant: string[] = [];

    for (const paragraph of paragraphs) {
      const paragraphLower = paragraph.toLowerCase();
      const matchCount = keywords.filter((k) =>
        paragraphLower.includes(k.toLowerCase())
      ).length;

      if (matchCount > 0) {
        relevant.push(paragraph.trim());
      }
    }

    // Return top 3 most relevant paragraphs
    return relevant.slice(0, 3);
  }

  private async generateAnswer(
    question: Question,
    articles: Array<{
      article: Article;
      relevantParagraphs: string[];
      score: number;
    }>
  ): Promise<Answer> {
    // Prepare context from articles
    const context = articles
      .map(
        (a, i) => `Source ${i + 1}:
Title: ${a.article.title}
Author: ${a.article.author}
Publish Date: ${a.article.publishTime}
Relevant Content:
${a.relevantParagraphs.join('\n\n')}`
      )
      .join('\n\n---\n\n');

    const response = await kimiClient.sendMessage(
      [
        {
          role: 'user',
          content: `Based on the following articles, answer this question:

Question: ${question.question}

${context}

Provide your answer in this JSON format:
{
  "answer": "Your detailed answer here, with citations to sources",
  "confidence": "high|medium|low",
  "followUpQuestions": ["Question 1?", "Question 2?", "Question 3?"]
}

Guidelines:
- Cite sources using [Source X] format
- Confidence should reflect how directly the answer is supported
- Suggest 3 follow-up questions that would deepen understanding`,
        },
      ],
      {
        system: this.systemPrompt,
        temperature: 0.2,
        maxTokens: 2000,
      }
    );

    try {
      const parsed = JSON.parse(response.content);

      return {
        answer: parsed.answer,
        sources: articles.map((a) => ({
          article: a.article,
          relevantText: a.relevantParagraphs.join('\n\n'),
          relevanceScore: a.score,
        })),
        confidence: parsed.confidence || 'medium',
        followUpQuestions: parsed.followUpQuestions || [],
      };
    } catch {
      // Fallback if JSON parsing fails
      return {
        answer: response.content,
        sources: articles.map((a) => ({
          article: a.article,
          relevantText: a.relevantParagraphs.join('\n\n'),
          relevanceScore: a.score,
        })),
        confidence: 'medium',
        followUpQuestions: this.suggestRelatedQueries(question.question),
      };
    }
  }

  private suggestRelatedQueries(originalQuestion: string): string[] {
    // Template follow-up questions based on question type
    const templates = [
      `What are the latest developments regarding ${originalQuestion}?`,
      `Which authors have written the most about ${originalQuestion}?`,
      `What are the different perspectives on ${originalQuestion}?`,
    ];

    return templates;
  }

  /**
   * Summarize multiple articles on a topic
   */
  async summarizeTopic(
    topic: string,
    maxArticles: number = 5
  ): Promise<{
    summary: string;
    keyPoints: string[];
    articles: Article[];
  }> {
    await db.connect();

    try {
      const articles = await db.searchArticles(topic, { limit: maxArticles });

      if (articles.length === 0) {
        return {
          summary: `No articles found about "${topic}".`,
          keyPoints: [],
          articles: [],
        };
      }

      const content = articles
        .map(
          (r, i) => `Article ${i + 1}: ${r.article.title} by ${r.article.author}
${r.article.content.substring(0, 500)}...`
        )
        .join('\n\n---\n\n');

      const response = await kimiClient.sendMessage(
        [
          {
            role: 'user',
            content: `Summarize these articles about "${topic}":

${content}

Return JSON format:
{
  "summary": "Comprehensive summary paragraph",
  "keyPoints": ["Point 1", "Point 2", "Point 3", "Point 4", "Point 5"]
}`,
          },
        ],
        {
          system: 'You synthesize information from multiple articles into clear summaries.',
          temperature: 0.3,
        }
      );

      try {
        const parsed = JSON.parse(response.content);
        return {
          summary: parsed.summary,
          keyPoints: parsed.keyPoints || [],
          articles: articles.map((r) => r.article),
        };
      } catch {
        return {
          summary: response.content,
          keyPoints: [],
          articles: articles.map((r) => r.article),
        };
      }
    } finally {
      await db.close();
    }
  }
}

export const qaAgent = new QAAgent();
