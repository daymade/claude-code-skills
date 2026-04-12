/**
 * Entity Extraction Agent
 * Extract entities and relationships from articles using LLM
 */

import { kimiClient } from '../lib/kimi-client.js';
import { db, Article } from '../lib/db.js';
import { Neo4jClient, Entity, Relationship } from '../lib/neo4j-client.js';

export interface ExtractedData {
  entities: Entity[];
  relationships: Relationship[];
}

export class EntityExtractionAgent {
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
   * Extract entities from an article
   */
  async extractFromArticle(article: Article): Promise<ExtractedData> {
    const prompt = `Analyze this article and extract entities and relationships.

Title: ${article.title}
Author: ${article.author}
Content: ${article.content.substring(0, 2000)}...

Extract the following:
1. Topics (main themes/subjects)
2. Keywords (important terms)
3. People mentioned
4. Organizations mentioned
5. Locations mentioned

Return JSON format:
{
  "entities": [
    {"type": "Topic", "name": "topic name", "id": "topic-id"},
    {"type": "Keyword", "name": "keyword", "id": "keyword-id"},
    {"type": "Person", "name": "person name", "id": "person-id"},
    {"type": "Organization", "name": "org name", "id": "org-id"},
    {"type": "Location", "name": "location", "id": "location-id"}
  ],
  "relationships": [
    {"source": "article-id", "target": "topic-id", "type": "BELONGS_TO"},
    {"source": "article-id", "target": "person-id", "type": "MENTIONS"}
  ]
}

Guidelines:
- Use kebab-case for IDs (e.g., "artificial-intelligence", "zhang-san")
- Extract 3-5 main topics
- Extract 5-10 relevant keywords
- Only include people/orgs/locations explicitly mentioned
- Create BELONGS_TO relationship between article and topics
- Create MENTIONS relationship between article and people/orgs/locations`;

    const response = await kimiClient.sendMessage(
      [{ role: 'user', content: prompt }],
      { temperature: 0.2 }
    );

    try {
      const parsed = JSON.parse(response.content);

      // Add author entity
      if (article.author) {
        parsed.entities.push({
          type: 'Author',
          name: article.author,
          id: this.slugify(article.author),
        });

        // Create WROTE relationship
        parsed.relationships.push({
          source: this.slugify(article.author),
          target: article.id,
          type: 'WROTE',
        });
      }

      // Add article as entity
      parsed.entities.push({
        type: 'Topic',
        name: article.title,
        id: article.id,
        properties: {
          publishTime: article.publishTime,
          readCount: article.readCount,
          url: article.url,
        },
      });

      return parsed;
    } catch (error) {
      console.error('Failed to parse extraction result:', error);
      return { entities: [], relationships: [] };
    }
  }

  /**
   * Process multiple articles and build graph
   */
  async processArticles(articleIds?: string[]): Promise<{
    processed: number;
    entities: number;
    relationships: number;
  }> {
    await db.connect();

    try {
      let articles: Article[];

      if (articleIds && articleIds.length > 0) {
        articles = [];
        for (const id of articleIds) {
          const article = await db.getArticleById(id);
          if (article) articles.push(article);
        }
      } else {
        // Get unprocessed articles (last 50)
        articles = await db.getRecentArticles(50);
      }

      let totalEntities = 0;
      let totalRelationships = 0;

      for (const article of articles) {
        console.log(`Processing: ${article.title}`);

        const extracted = await this.extractFromArticle(article);

        // Save entities
        for (const entity of extracted.entities) {
          await this.neo4j.mergeEntity(entity);
          totalEntities++;
        }

        // Save relationships
        for (const rel of extracted.relationships) {
          await this.neo4j.mergeRelationship(rel);
          totalRelationships++;
        }

        // Small delay to avoid rate limiting
        await new Promise((r) => setTimeout(r, 100));
      }

      return {
        processed: articles.length,
        entities: totalEntities,
        relationships: totalRelationships,
      };
    } finally {
      await db.close();
    }
  }

  /**
   * Extract co-occurrence relationships between topics
   */
  async extractCoOccurrences(): Promise<number> {
    // Find articles with multiple topics and create CO_OCCURS_WITH relationships
    const result = await this.neo4j.query(`
      MATCH (a:Article)-[:BELONGS_TO]->(t1:Topic)
      MATCH (a)-[:BELONGS_TO]->(t2:Topic)
      WHERE t1.id < t2.id
      WITH t1, t2, count(a) as weight
      WHERE weight > 1
      MERGE (t1)-[r:CO_OCCURS_WITH]->(t2)
      SET r.weight = weight
      RETURN count(r) as created
    `);

    return result[0]?.created || 0;
  }

  /**
   * Find similar articles based on shared entities
   */
  async findSimilarArticles(articleId: string, limit: number = 5): Promise<
    Array<{
      article: any;
      commonEntities: number;
      sharedTopics: string[];
    }>
  > {
    const result = await this.neo4j.query(
      `
      MATCH (a:Topic {id: $id})<-[:BELONGS_TO]-(shared:Topic)<-[:BELONGS_TO]-(similar:Topic)
      WHERE similar.id <> $id
      WITH similar, count(DISTINCT shared) as commonEntities, collect(DISTINCT shared.name) as sharedTopics
      ORDER BY commonEntities DESC
      LIMIT $limit
      RETURN similar, commonEntities, sharedTopics
    `,
      { id: articleId, limit }
    );

    return result.map((r) => ({
      article: r.similar.properties,
      commonEntities: r.commonEntities.toNumber(),
      sharedTopics: r.sharedTopics,
    }));
  }

  private slugify(text: string): string {
    return text
      .toLowerCase()
      .replace(/[^\w\s-]/g, '')
      .replace(/\s+/g, '-')
      .substring(0, 50);
  }
}

export const entityExtractionAgent = new EntityExtractionAgent();
