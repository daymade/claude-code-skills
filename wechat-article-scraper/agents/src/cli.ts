#!/usr/bin/env node
/**
 * Agent CLI - Command line interface for intelligent article search
 */

import { Command } from 'commander';
import { searchAgent } from './agents/search-agent.js';
import { qaAgent } from './agents/qa-agent.js';
import { recommendationAgent } from './agents/recommendation-agent.js';

const program = new Command();

program
  .name('w-agent')
  .description('WeChat Article Agent - Semantic search with LLM')
  .version('1.0.0');

// Search command
program
  .command('search')
  .description('Semantic search articles')
  .argument('<query>', 'Search query')
  .option('-a, --author <author>', 'Filter by author')
  .option('-l, --limit <n>', 'Max results', '10')
  .action(async (query, options) => {
    console.log(`🔍 Searching: "${query}"\n`);

    try {
      const results = await searchAgent.search({
        query,
        filters: {
          author: options.author,
        },
        limit: parseInt(options.limit),
      });

      console.log(`📊 ${results.summary}\n`);

      results.results.forEach((r, i) => {
        console.log(`${i + 1}. ${r.article.title}`);
        console.log(`   👤 ${r.article.author} | 📅 ${r.article.publishTime}`);
        console.log(`   📖 ${r.article.readCount?.toLocaleString() || 0} reads`);
        console.log(`   💡 ${r.explanation}`);
        console.log(`   🔗 ${r.article.url}\n`);
      });

      if (results.relatedKeywords.length > 0) {
        console.log(`💡 Related: ${results.relatedKeywords.join(', ')}\n`);
      }
    } catch (error) {
      console.error('❌ Error:', error);
      process.exit(1);
    }
  });

// Ask command
program
  .command('ask')
  .description('Ask questions about articles')
  .argument('<question>', 'Your question')
  .option('-s, --sources <n>', 'Number of source articles', '5')
  .action(async (question, options) => {
    console.log(`❓ Question: "${question}"\n`);

    try {
      const answer = await qaAgent.ask({
        question,
        maxSources: parseInt(options.sources),
      });

      console.log(`✅ Answer (${answer.confidence} confidence):\n`);
      console.log(answer.answer);
      console.log(`\n📚 Sources:`);
      answer.sources.forEach((s, i) => {
        console.log(`  ${i + 1}. "${s.article.title}" - ${s.article.author}`);
      });

      if (answer.followUpQuestions.length > 0) {
        console.log(`\n💭 Follow-up questions:`);
        answer.followUpQuestions.forEach((q) => console.log(`   • ${q}`));
      }
    } catch (error) {
      console.error('❌ Error:', error);
      process.exit(1);
    }
  });

// Recommend command
program
  .command('recommend')
  .description('Get article recommendations')
  .option('-a, --article <id>', 'Based on article ID')
  .option('-t, --topic <topic>', 'Based on topic')
  .option('-A, --author <author>', 'Based on author')
  .option('-l, --limit <n>', 'Number of recommendations', '5')
  .action(async (options) => {
    console.log(`🎯 Generating recommendations...\n`);

    try {
      const recommendations = await recommendationAgent.getRecommendations({
        basedOn: {
          articleId: options.article,
          topic: options.topic,
          author: options.author,
        },
        limit: parseInt(options.limit),
      });

      recommendations.forEach((r, i) => {
        const icon = {
          similar_content: '📄',
          same_author: '✍️',
          trending: '🔥',
          discovery: '💡',
        }[r.category];

        console.log(`${i + 1}. ${icon} ${r.article.title}`);
        console.log(`   👤 ${r.article.author} | 📅 ${r.article.publishTime}`);
        console.log(`   📖 ${r.article.readCount?.toLocaleString() || 0} reads`);
        console.log(`   💭 ${r.reason}`);
        console.log(`   🔗 ${r.article.url}\n`);
      });
    } catch (error) {
      console.error('❌ Error:', error);
      process.exit(1);
    }
  });

program.parse();
