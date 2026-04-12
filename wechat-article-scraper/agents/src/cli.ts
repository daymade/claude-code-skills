#!/usr/bin/env node
/**
 * Agent CLI - Command line interface for intelligent article search
 */

import { Command } from 'commander';
import { searchAgent } from './agents/search-agent.js';
import { qaAgent } from './agents/qa-agent.js';
import { recommendationAgent } from './agents/recommendation-agent.js';
import { entityExtractionAgent } from './agents/entity-extraction-agent.js';
import { insightAgent } from './agents/insight-agent.js';

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

// Knowledge Graph command
program
  .command('graph')
  .description('Knowledge graph operations')
  .argument('<action>', 'Action: extract, network, topics, clusters')
  .option('-a, --article <id>', 'Article ID for extraction')
  .option('-A, --author <author>', 'Author name for network')
  .option('-t, --topic <topic>', 'Topic for evolution analysis')
  .action(async (action, options) => {
    try {
      if (action === 'extract') {
        console.log('🔍 Extracting entities from articles...\n');
        await entityExtractionAgent.connect();
        const result = await entityExtractionAgent.processArticles(
          options.article ? [options.article] : undefined
        );
        console.log(`✅ Processed ${result.processed} articles`);
        console.log(`   Entities: ${result.entities}`);
        console.log(`   Relationships: ${result.relationships}`);

        // Extract co-occurrences
        console.log('\n🔗 Extracting topic co-occurrences...');
        const coOccurrences = await entityExtractionAgent.extractCoOccurrences();
        console.log(`   Created ${coOccurrences} co-occurrence relationships`);
        await entityExtractionAgent.close();
      }
      else if (action === 'network') {
        if (!options.author) {
          console.error('❌ Please provide --author for network analysis');
          process.exit(1);
        }
        console.log(`🕸️  Analyzing network for: ${options.author}\n`);
        const { neo4jClient } = await import('./lib/neo4j-client.js');
        await neo4jClient.connect();
        const network = await neo4jClient.getAuthorNetwork(options.author);
        await neo4jClient.close();

        console.log(`📊 Author: ${network.author?.name || options.author}`);
        console.log(`📝 Articles: ${network.articles.length}`);
        console.log(`\n🏷️  Top Topics:`);
        network.topics.forEach(t => {
          console.log(`   • ${t.name} (${t.frequency} articles)`);
        });
        console.log(`\n👥 Related Authors:`);
        network.relatedAuthors.forEach(a => {
          console.log(`   • ${a.name} (${a.commonTopics} common topics)`);
        });
      }
      else if (action === 'topics') {
        if (!options.topic) {
          console.error('❌ Please provide --topic for evolution analysis');
          process.exit(1);
        }
        console.log(`📈 Analyzing evolution of: ${options.topic}\n`);
        const { neo4jClient } = await import('./lib/neo4j-client.js');
        await neo4jClient.connect();
        const evolution = await neo4jClient.getTopicEvolution(options.topic);
        await neo4jClient.close();

        if (!evolution.topic) {
          console.log('❌ Topic not found');
          return;
        }

        console.log(`📊 Timeline:`);
        evolution.timeline.forEach(t => {
          console.log(`   ${t.month}: ${t.articleCount} articles, ${t.avgReadCount} avg reads`);
        });
        console.log(`\n🔗 Related Topics: ${evolution.relatedTopics.map(t => t.name).join(', ')}`);
      }
      else if (action === 'clusters') {
        console.log('🔬 Finding content clusters...\n');
        const { neo4jClient } = await import('./lib/neo4j-client.js');
        await neo4jClient.connect();
        const clusters = await neo4jClient.getContentClusters();
        await neo4jClient.close();

        clusters.forEach(c => {
          console.log(`📦 Cluster ${c.clusterId}: ${c.centralTopic}`);
          console.log(`   Size: ${c.size} topics`);
          console.log(`   Topics: ${c.topics.slice(0, 5).join(', ')}`);
          console.log();
        });
      }
      else {
        console.error('❌ Unknown action. Use: extract, network, topics, clusters');
        process.exit(1);
      }
    } catch (error) {
      console.error('❌ Error:', error);
      process.exit(1);
    }
  });

// Insight report command
program
  .command('insight')
  .description('Generate insight reports')
  .argument('<type>', 'Report type: trend, author, industry, compare')
  .option('-t, --target <target>', 'Target (topic/author/industry name)')
  .option('-t2, --target2 <target2>', 'Second target for comparison')
  .action(async (type, options) => {
    try {
      await insightAgent.connect();

      if (type === 'trend') {
        if (!options.target) {
          console.error('❌ Please provide --target topic name');
          process.exit(1);
        }
        console.log(`📈 Generating trend report for: ${options.target}\n`);
        const report = await insightAgent.generateTrendReport(options.target);

        console.log(`📊 ${report.topic}`);
        console.log(`📈 Trend: ${report.trend}`);
        console.log(`\n📝 Summary: ${report.summary}`);
        console.log(`\n📚 Key Articles:`);
        report.keyArticles.forEach((a, i) => {
          console.log(`   ${i + 1}. "${a.title}" by ${a.author}`);
          console.log(`      💡 ${a.insight}`);
        });
        console.log(`\n🔮 Prediction: ${report.prediction}`);
      }
      else if (type === 'author') {
        if (!options.target) {
          console.error('❌ Please provide --target author name');
          process.exit(1);
        }
        console.log(`👤 Generating author report for: ${options.target}\n`);
        const report = await insightAgent.generateAuthorReport(options.target);

        console.log(`👤 ${report.author}`);
        console.log(`📝 ${report.summary}`);
        console.log(`\n🎯 Expertise: ${report.expertise.join(', ')}`);
        console.log(`✍️  Style: ${report.writingStyle}`);
        console.log(`👥 Audience: ${report.audience}`);
        console.log(`\n🤝 Recommended Collaborations: ${report.recommendedCollaborations.join(', ')}`);
        console.log(`⚠️  Content Gaps: ${report.contentGaps.join(', ')}`);
      }
      else if (type === 'industry') {
        if (!options.target) {
          console.error('❌ Please provide --target industry name');
          process.exit(1);
        }
        console.log(`🏭 Generating industry report for: ${options.target}\n`);
        const report = await insightAgent.generateIndustryReport(options.target);

        console.log(`🏭 ${report.industry}`);
        console.log(`📝 ${report.overview}`);
        console.log(`\n⭐ Key Players:`);
        report.keyPlayers.forEach(p => {
          console.log(`   • ${p.name} (${p.role}): ${p.influence}`);
        });
        console.log(`\n🔥 Hot Topics:`);
        report.hotTopics.forEach(t => {
          console.log(`   • ${t.topic}: ${t.trend} (${t.articles} articles)`);
        });
        console.log(`\n✅ Opportunities: ${report.opportunities.join(', ')}`);
        console.log(`⚠️  Risks: ${report.risks.join(', ')}`);
      }
      else if (type === 'compare') {
        if (!options.target || !options.target2) {
          console.error('❌ Please provide both --target and --target2 for comparison');
          process.exit(1);
        }
        console.log(`⚖️  Comparing: ${options.target} vs ${options.target2}\n`);
        const entityType = options.target.includes('@') ? 'author' : 'topic';
        const comparison = await insightAgent.generateComparison(
          entityType,
          options.target,
          options.target2
        );

        console.log(`📝 ${comparison.summary}`);
        console.log(`\n✅ Similarities:`);
        comparison.similarities.forEach(s => console.log(`   • ${s}`));
        console.log(`\n❌ Differences:`);
        comparison.differences.forEach(d => console.log(`   • ${d}`));
        console.log(`\n💡 Recommendations: ${comparison.recommendations}`);
      }
      else {
        console.error('❌ Unknown report type. Use: trend, author, industry, compare');
        process.exit(1);
      }

      await insightAgent.close();
    } catch (error) {
      console.error('❌ Error:', error);
      process.exit(1);
    }
  });

program.parse();
