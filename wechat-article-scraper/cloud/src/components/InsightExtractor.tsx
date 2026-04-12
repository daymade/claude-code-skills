'use client';

/**
 * Insight Extractor Component
 *
 * Core workflow: Annotations → AI Insights → Export to Workflow
 * This component "打穿" the reading-to-action pipeline.
 */

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useReadingAgent } from '@/hooks/useReadingAgent';
import { Annotation } from '@/lib/annotation-engine';
import { NotionClient } from '@/lib/notion-client';
import { ObsidianClient } from '@/lib/obsidian-client';

interface InsightExtractorProps {
  annotations: Annotation[];
  article: {
    id: string;
    title: string;
    author?: string;
    content?: string;
  };
  onExport?: (format: 'notion' | 'obsidian' | 'markdown') => void;
}

type ExportTarget = 'notion' | 'obsidian' | 'markdown' | null;

export function InsightExtractor({ annotations, article, onExport }: InsightExtractorProps) {
  const [showPanel, setShowPanel] = useState(false);
  const [exportTarget, setExportTarget] = useState<ExportTarget>(null);
  const [exportStatus, setExportStatus] = useState<'idle' | 'exporting' | 'success' | 'error'>('idle');
  const [selectedInsightIds, setSelectedInsightIds] = useState<Set<string>>(new Set());

  // Get API key from environment or settings
  const apiKey = process.env.NEXT_PUBLIC_KIMI_API_KEY || '';
  const {
    isProcessing,
    progress,
    insights,
    notes,
    actions,
    error,
    processAnnotations,
    reset,
  } = useReadingAgent(apiKey);

  const handleExtract = async () => {
    if (annotations.length === 0) return;
    await processAnnotations(annotations, {
      title: article.title,
      author: article.author,
      content: article.content,
    });
  };

  const handleExport = async (target: ExportTarget) => {
    if (!target || !notes) return;

    setExportTarget(target);
    setExportStatus('exporting');

    try {
      // Filter selected insights
      const selectedInsights = insights.filter((i) => selectedInsightIds.has(i.id));
      const insightsToExport = selectedInsights.length > 0 ? selectedInsights : insights;

      const exportData = {
        article: {
          id: article.id,
          title: article.title,
          author: article.author,
          content: article.content,
        },
        insights: insightsToExport,
        notes,
        actions,
      };

      switch (target) {
        case 'notion':
          await exportToNotion(exportData);
          break;
        case 'obsidian':
          await exportToObsidian(exportData);
          break;
        case 'markdown':
          downloadMarkdown(exportData);
          break;
      }

      setExportStatus('success');
      onExport?.(target);
    } catch (err) {
      setExportStatus('error');
    }
  };

  const exportToNotion = async (data: any) => {
    // Implementation would use Notion OAuth flow
    // For now, show a prompt for manual paste
    alert('Notion export: Please paste your integration token in settings');
  };

  const exportToObsidian = async (data: any) => {
    const client = new ObsidianClient();
    const result = client.exportArticle({
      article: data.article,
      annotations: annotations.map((a) => ({
        id: a.id,
        quote: a.quote,
        comment: a.comment,
        color: a.color,
        tags: a.tags,
        createdAt: a.createdAt,
      })),
    });

    // Download the file
    const blob = new Blob([result.content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = result.filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadMarkdown = (data: any) => {
    let content = `# ${data.article.title} - Insights\n\n`;
    content += `## Key Insights\n\n`;
    data.insights.forEach((insight: any, i: number) => {
      content += `${i + 1}. **${insight.type}**: ${insight.content}\n`;
      content += `   - Source: "${insight.sourceQuote.substring(0, 100)}..."\n`;
      content += `   - Confidence: ${insight.confidence}\n\n`;
    });

    content += `## Notes\n\n${data.notes}\n\n`;

    content += `## Suggested Actions\n\n`;
    data.actions.forEach((action: any, i: number) => {
      content += `- [ ] ${action.description} (${action.priority} priority)\n`;
    });

    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${article.title.substring(0, 30)} - Insights.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const toggleInsightSelection = (id: string) => {
    const newSet = new Set(selectedInsightIds);
    if (newSet.has(id)) {
      newSet.delete(id);
    } else {
      newSet.add(id);
    }
    setSelectedInsightIds(newSet);
  };

  if (annotations.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        <p>添加标注以提取洞察</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Extract Button */}
      {!showPanel && (
        <motion.button
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          onClick={() => {
            setShowPanel(true);
            handleExtract();
          }}
          className="w-full py-3 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-xl font-medium shadow-lg hover:shadow-xl transition-shadow"
        >
          ✨ 提取洞察 ({annotations.length} 个标注)
        </motion.button>
      )}

      {/* Results Panel */}
      <AnimatePresence>
        {showPanel && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="bg-white rounded-xl border shadow-lg overflow-hidden"
          >
            {/* Header */}
            <div className="px-4 py-3 border-b bg-gray-50 flex items-center justify-between">
              <h3 className="font-semibold">🧠 AI 洞察提取</h3>
              <button
                onClick={() => {
                  setShowPanel(false);
                  reset();
                }}
                className="text-gray-400 hover:text-gray-600"
              >
                ✕
              </button>
            </div>

            {/* Progress */}
            {isProcessing && (
              <div className="px-4 py-3">
                <div className="flex items-center gap-3">
                  <div className="w-5 h-5 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
                  <span className="text-sm text-gray-600">正在分析标注...</span>
                </div>
                <div className="mt-2 h-1 bg-gray-200 rounded-full overflow-hidden">
                  <motion.div
                    className="h-full bg-purple-500"
                    initial={{ width: 0 }}
                    animate={{ width: `${progress}%` }}
                  />
                </div>
              </div>
            )}

            {error && (
              <div className="px-4 py-3 bg-red-50 text-red-700 text-sm">
                {error}
              </div>
            )}

            {/* Insights */}
            {insights.length > 0 && (
              <div className="px-4 py-3 space-y-3">
                <h4 className="text-sm font-medium text-gray-700">
                  核心洞察 ({insights.length})
                </h4>
                {insights.map((insight) => (
                  <div
                    key={insight.id}
                    onClick={() => toggleInsightSelection(insight.id)}
                    className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                      selectedInsightIds.has(insight.id)
                        ? 'border-purple-500 bg-purple-50'
                        : 'border-gray-200 hover:border-purple-300'
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <span
                        className={`text-xs px-2 py-0.5 rounded ${
                          insight.type === 'concept'
                            ? 'bg-blue-100 text-blue-700'
                            : insight.type === 'method'
                            ? 'bg-green-100 text-green-700'
                            : insight.type === 'case_study'
                            ? 'bg-yellow-100 text-yellow-700'
                            : 'bg-gray-100 text-gray-700'
                        }`}
                      >
                        {insight.type}
                      </span>
                      <span
                        className={`text-xs px-2 py-0.5 rounded ${
                          insight.confidence === 'high'
                            ? 'bg-green-100 text-green-700'
                            : insight.confidence === 'medium'
                            ? 'bg-yellow-100 text-yellow-700'
                            : 'bg-gray-100 text-gray-700'
                        }`}
                      >
                        {insight.confidence}
                      </span>
                    </div>
                    <p className="mt-2 text-sm">{insight.content}</p>
                    <p className="mt-1 text-xs text-gray-500 line-clamp-2">
                      来源: "{insight.sourceQuote}"
                    </p>
                  </div>
                ))}
              </div>
            )}

            {/* Actions */}
            {actions.length > 0 && (
              <div className="px-4 py-3 border-t">
                <h4 className="text-sm font-medium text-gray-700 mb-2">
                  建议行动 ({actions.length})
                </h4>
                <div className="space-y-2">
                  {actions.slice(0, 3).map((action, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-2 text-sm p-2 bg-gray-50 rounded"
                    >
                      <span
                        className={`w-2 h-2 rounded-full ${
                          action.priority === 'high'
                            ? 'bg-red-500'
                            : action.priority === 'medium'
                            ? 'bg-yellow-500'
                            : 'bg-gray-400'
                        }`}
                      />
                      <span className="flex-1">{action.description}</span>
                      {action.estimatedTime && (
                        <span className="text-xs text-gray-500">
                          {action.estimatedTime}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Export Section */}
            {notes && (
              <div className="px-4 py-3 border-t bg-gray-50">
                <h4 className="text-sm font-medium text-gray-700 mb-3">
                  导出到工作流
                </h4>
                <div className="grid grid-cols-3 gap-2">
                  <button
                    onClick={() => handleExport('notion')}
                    disabled={exportStatus === 'exporting'}
                    className="flex flex-col items-center gap-1 p-3 bg-white border rounded-lg hover:border-blue-500 hover:bg-blue-50 transition-colors disabled:opacity-50"
                  >
                    <span className="text-2xl">📓</span>
                    <span className="text-xs">Notion</span>
                  </button>
                  <button
                    onClick={() => handleExport('obsidian')}
                    disabled={exportStatus === 'exporting'}
                    className="flex flex-col items-center gap-1 p-3 bg-white border rounded-lg hover:border-purple-500 hover:bg-purple-50 transition-colors disabled:opacity-50"
                  >
                    <span className="text-2xl">📝</span>
                    <span className="text-xs">Obsidian</span>
                  </button>
                  <button
                    onClick={() => handleExport('markdown')}
                    disabled={exportStatus === 'exporting'}
                    className="flex flex-col items-center gap-1 p-3 bg-white border rounded-lg hover:border-gray-500 hover:bg-gray-50 transition-colors disabled:opacity-50"
                  >
                    <span className="text-2xl">📄</span>
                    <span className="text-xs">Markdown</span>
                  </button>
                </div>

                {exportStatus === 'success' && (
                  <p className="mt-2 text-sm text-green-600 text-center">
                    ✓ 导出成功
                  </p>
                )}
                {exportStatus === 'error' && (
                  <p className="mt-2 text-sm text-red-600 text-center">
                    ✗ 导出失败，请重试
                  </p>
                )}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
