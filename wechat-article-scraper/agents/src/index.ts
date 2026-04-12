/**
 * WeChat Article Scraper - Agent SDK
 * Semantic search, Q&A, and recommendation system using Claude Agent SDK
 */

export { SearchAgent, searchAgent } from './agents/search-agent.js';
export { QAAgent, qaAgent } from './agents/qa-agent.js';
export { RecommendationAgent, recommendationAgent } from './agents/recommendation-agent.js';
export { KimiClient, kimiClient } from './lib/kimi-client.js';
export { ArticleDatabase, db } from './lib/db.js';
export { config } from './config.js';

export type {
  SearchQuery,
  SearchResponse,
} from './agents/search-agent.js';

export type {
  Question,
  Answer,
} from './agents/qa-agent.js';

export type {
  RecommendationRequest,
  Recommendation,
} from './agents/recommendation-agent.js';

export type {
  Article,
  SearchResult,
} from './lib/db.js';
