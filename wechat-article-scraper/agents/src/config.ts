/**
 * Agent SDK Configuration
 * Anthropic format with Kimi API
 */

export const config = {
  // Kimi API Configuration (Anthropic format)
  apiKey: process.env.KIMI_API_KEY || 'sk-kimi-CoLJX0b0xFa0EsWmOVkfHcduUNFDuqAhoeXnxddpcNZXiGBCCfzbdefM7c9RVvBf',
  baseURL: process.env.KIMI_BASE_URL || 'https://api.kimi.com/coding/',
  model: process.env.KIMI_MODEL || 'kimi-for-coding',

  // Agent Configuration
  maxTokens: 4096,
  temperature: 0.3, // Lower for search accuracy

  // Search Configuration
  search: {
    maxResults: 10,
    similarityThreshold: 0.7,
    enableReranking: true,
  },

  // Database (SQLite for article storage)
  dbPath: process.env.DB_PATH || '../data/articles.db',
};

export type Config = typeof config;
