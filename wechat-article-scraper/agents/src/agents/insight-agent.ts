/**
 * Insight Analysis Agent
 * Generate intelligent insights and reports from knowledge graph
 */

import { kimiClient } from '../lib/kimi-client.js';
import { Neo4jClient } from '../lib/neo4j-client.js';
import { db } from '../lib/db.js';

export interface TrendReport {
  topic: string;
  summary: string;
  trend: 'rising' | 'stable' | 'declining';
  keyArticles: Array<{
    title: string;
    author: string;
    insight: string;
  }>;
  relatedTopics: string[];
  prediction: string;
}

export interface AuthorReport {
  author: string;
  summary: string;
  expertise: string[];
  writingStyle: string;
  audience: string;
  recommendedCollaborations: string[];
  contentGaps: string[];
}

export interface IndustryReport {
  industry: string;
  overview: string;
  keyPlayers: Array<{
    name: string;
    role: string;
    influence: string;
  }>;
  hotTopics: Array<{
    topic: string;
    trend: string;
    articles: number;
  }>;
  opportunities: string[];
  risks: string[];
}

export class InsightAgent {
  private neo4j: Neo4jClient;

  constructor(neo4jClient?: Neo4jClient) {
    this.neo4j = neo4jClient || new Neo4jClient();
  }

  async connect(): Promise<void> {
    await this.neo4j.connect();
  }

  async close(): Promise<void> {
    await this.neo4j.close();
  }

  /**
   * Generate trend analysis for a topic
   */
  async generateTrendReport(topic: string): Promise<TrendReport> {
    const evolution = await this.neo4j.getTopicEvolution(topic);

    if (!evolution.topic) {
      throw new Error(`Topic not found: ${topic}`);
    }

    // Get key articles
    const articles = await db.connect().then(() =>
      db.searchArticles(topic, { limit: 5 })
    );
    await db.close();

    const prompt = `Analyze this topic trend and generate an insight report.

Topic: ${topic}

Timeline Data:
${JSON.stringify(evolution.timeline.slice(-6), null, 2)}

Related Topics: ${evolution.relatedTopics.map(t => t.name).join(', ')}

Key Articles:
${articles.map((a, i) => `${i+1}. "${a.article.title}" by ${a.article.author} (${a.article.readCount} reads)`).join('\n')}

Generate a JSON report with:
{
  "summary": "Brief overview of the trend (2-3 sentences)",
  "trend": "rising|stable|declining",
  "keyArticles": [
    {"title": "...", "author": "...", "insight": "Why this article matters"}
  ],
  "relatedTopics": ["topic1", "topic2"],
  "prediction": "Future prediction based on the trend"
}

Guidelines:
- trend should be based on article volume and engagement over time
- keyArticles should explain WHY each is significant
- prediction should be data-informed, not generic`;

    const response = await kimiClient.sendMessage(
      [{ role: 'user', content: prompt }],
      { temperature: 0.4 }
    );

    try {
      const parsed = JSON.parse(response.content);
      return {
        topic,
        ...parsed,
      };
    } catch (error) {
      // Fallback
      return {
        topic,
        summary: `Analysis of ${topic} based on ${evolution.timeline.length} months of data.`,
        trend: 'stable',
        keyArticles: articles.map(a => ({
          title: a.article.title,
          author: a.article.author || 'Unknown',
          insight: 'Key article on this topic',
        })),
        relatedTopics: evolution.relatedTopics.map(t => t.name),
        prediction: 'Trend expected to continue based on current momentum.',
      };
    }
  }

  /**
   * Generate author profile and recommendations
   */
  async generateAuthorReport(authorName: string): Promise<AuthorReport> {
    const network = await this.neo4j.getAuthorNetwork(authorName);

    if (!network.author) {
      throw new Error(`Author not found: ${authorName}`);
    }

    const prompt = `Analyze this author and generate a profile report.

Author: ${authorName}

Articles (${network.articles.length} total):
${network.articles.slice(0, 5).map(a => `- "${a.title}" (${a.readCount} reads)`).join('\n')}

Top Topics:
${network.topics.map(t => `- ${t.name} (${t.frequency} articles)`).join('\n')}

Related Authors:
${network.relatedAuthors.map(a => `- ${a.name} (${a.commonTopics} common topics)`).join('\n')}

Generate a JSON report:
{
  "summary": "Author profile overview (2-3 sentences)",
  "expertise": ["area1", "area2", "area3"],
  "writingStyle": "Description of writing style",
  "audience": "Target audience description",
  "recommendedCollaborations": ["author1", "author2"],
  "contentGaps": ["topic1", "topic2"]
}

Guidelines:
- expertise: infer from topics and content
- writingStyle: analyze titles and engagement patterns
- recommendedCollaborations: choose from related authors with complementary expertise
- contentGaps: identify popular topics they haven't covered`;

    const response = await kimiClient.sendMessage(
      [{ role: 'user', content: prompt }],
      { temperature: 0.4 }
    );

    try {
      const parsed = JSON.parse(response.content);
      return {
        author: authorName,
        ...parsed,
      };
    } catch (error) {
      return {
        author: authorName,
        summary: `${authorName} has written ${network.articles.length} articles.`,
        expertise: network.topics.slice(0, 3).map(t => t.name),
        writingStyle: 'Professional content creator',
        audience: 'General professional audience',
        recommendedCollaborations: network.relatedAuthors.slice(0, 2).map(a => a.name),
        contentGaps: ['Emerging technologies', 'Industry trends'],
      };
    }
  }

  /**
   * Generate industry landscape report
   */
  async generateIndustryReport(industry: string): Promise<IndustryReport> {
    // Get articles related to this industry
    await db.connect();
    const articles = await db.searchArticles(industry, { limit: 20 });
    await db.close();

    // Get content clusters
    const clusters = await this.neo4j.getContentClusters();
    const relevantCluster = clusters.find(c =>
      c.centralTopic.toLowerCase().includes(industry.toLowerCase()) ||
      c.topics.some(t => t.toLowerCase().includes(industry.toLowerCase()))
    );

    const prompt = `Generate an industry landscape report.

Industry: ${industry}

Articles Analyzed: ${articles.length}

Key Topics: ${relevantCluster?.topics.join(', ') || 'Various'}

Sample Articles:
${articles.slice(0, 5).map(a => `- "${a.article.title}" by ${a.article.author}`).join('\n')}

Generate a JSON report:
{
  "overview": "Industry overview (3-4 sentences)",
  "keyPlayers": [
    {"name": "Author/Org", "role": "Influencer/Expert/Leader", "influence": "Description"}
  ],
  "hotTopics": [
    {"topic": "...", "trend": "rising/stable/declining", "articles": 10}
  ],
  "opportunities": ["opportunity1", "opportunity2"],
  "risks": ["risk1", "risk2"]
}

Guidelines:
- keyPlayers: identify from frequent authors and mentioned organizations
- hotTopics: identify trending subjects with volume
- opportunities: content/business opportunities based on gaps
- risks: potential challenges or declining areas`;

    const response = await kimiClient.sendMessage(
      [{ role: 'user', content: prompt }],
      { temperature: 0.4 }
    );

    try {
      const parsed = JSON.parse(response.content);
      return {
        industry,
        ...parsed,
      };
    } catch (error) {
      // Extract authors for key players
      const authorCounts = new Map();
      for (const a of articles) {
        const name = a.article.author || 'Unknown';
        authorCounts.set(name, (authorCounts.get(name) || 0) + 1);
      }
      const topAuthors = Array.from(authorCounts.entries())
        .sort((a, b) => b[1] - a[1])
        .slice(0, 3);

      return {
        industry,
        overview: `Analysis of ${industry} based on ${articles.length} articles.`,
        keyPlayers: topAuthors.map(([name, count]) => ({
          name,
          role: 'Content Creator',
          influence: `${count} articles on this topic`,
        })),
        hotTopics: relevantCluster?.topics.slice(0, 3).map(t => ({
          topic: t,
          trend: 'stable',
          articles: relevantCluster.size,
        })) || [],
        opportunities: ['Increase coverage on emerging subtopics'],
        risks: ['Content saturation in popular areas'],
      };
    }
  }

  /**
   * Generate comparative analysis between two topics/authors
   */
  async generateComparison(
    type: 'topic' | 'author',
    entity1: string,
    entity2: string
  ): Promise<{
    summary: string;
    similarities: string[];
    differences: string[];
    recommendations: string;
  }> {
    let context1, context2;

    if (type === 'topic') {
      context1 = await this.neo4j.getTopicEvolution(entity1);
      context2 = await this.neo4j.getTopicEvolution(entity2);
    } else {
      context1 = await this.neo4j.getAuthorNetwork(entity1);
      context2 = await this.neo4j.getAuthorNetwork(entity2);
    }

    const prompt = `Compare these two ${type}s and generate insights.

${type === 'topic' ? 'Topic' : 'Author'} 1: ${entity1}
${JSON.stringify(context1, null, 2)}

${type === 'topic' ? 'Topic' : 'Author'} 2: ${entity2}
${JSON.stringify(context2, null, 2)}

Generate a JSON comparison:
{
  "summary": "Overall comparison (2-3 sentences)",
  "similarities": ["similarity1", "similarity2"],
  "differences": ["difference1", "difference2"],
  "recommendations": "Strategic recommendations"
}`;

    const response = await kimiClient.sendMessage(
      [{ role: 'user', content: prompt }],
      { temperature: 0.4 }
    );

    try {
      return JSON.parse(response.content);
    } catch (error) {
      return {
        summary: `Comparison between ${entity1} and ${entity2}.`,
        similarities: ['Both are active in content creation'],
        differences: ['Different focus areas'],
        recommendations: 'Consider cross-pollination of ideas.',
      };
    }
  }
}

export const insightAgent = new InsightAgent();
