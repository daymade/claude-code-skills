'use client';

/**
 * useReadingAgent Hook
 *
 * Integrates the ReadingAgentSDK with React components
 * Provides streaming insights and state management
 */

import { useState, useCallback, useRef } from 'react';
import { createReadingAgent, ReadingAgentSDK } from '@/lib/reading-agent-sdk';
import { Annotation } from '@/lib/annotation-engine';

interface Insight {
  id: string;
  content: string;
  type: 'concept' | 'method' | 'case_study' | 'claim' | 'evidence';
  sourceQuote: string;
  confidence: 'high' | 'medium' | 'low';
}

interface Connection {
  currentInsight: string;
  relatedArticle: string;
  relationship: string;
  strength: 'strong' | 'moderate' | 'weak';
}

interface Action {
  description: string;
  category: 'research' | 'writing' | 'experiment' | 'discussion' | 'implementation';
  priority: 'high' | 'medium' | 'low';
  estimatedTime?: string;
}

interface AgentResult {
  insights: Insight[];
  notes: string;
  connections: Connection[];
  actions: Action[];
}

interface UseReadingAgentReturn {
  isProcessing: boolean;
  progress: number;
  insights: Insight[];
  notes: string | null;
  connections: Connection[];
  actions: Action[];
  error: string | null;
  processAnnotations: (
    annotations: Annotation[],
    articleContext: { title: string; author?: string; content?: string }
  ) => Promise<void>;
  reset: () => void;
}

export function useReadingAgent(apiKey?: string): UseReadingAgentReturn {
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [insights, setInsights] = useState<Insight[]>([]);
  const [notes, setNotes] = useState<string | null>(null);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [actions, setActions] = useState<Action[]>([]);
  const [error, setError] = useState<string | null>(null);

  const agentRef = useRef<ReadingAgentSDK | null>(null);

  const processAnnotations = useCallback(
    async (
      annotations: Annotation[],
      articleContext: { title: string; author?: string; content?: string }
    ) => {
      if (!apiKey) {
        setError('API key not configured');
        return;
      }

      if (annotations.length === 0) {
        setError('No annotations to process');
        return;
      }

      setIsProcessing(true);
      setProgress(0);
      setError(null);
      setInsights([]);
      setNotes(null);
      setConnections([]);
      setActions([]);

      try {
        // Initialize agent
        if (!agentRef.current) {
          agentRef.current = createReadingAgent(apiKey);
        }

        // Stream results
        const stream = agentRef.current.streamInsights(annotations, articleContext);
        let itemCount = 0;

        for await (const item of stream) {
          itemCount++;
          setProgress(Math.min(itemCount * 20, 90)); // Simulate progress

          switch (item.type) {
            case 'insight':
              setInsights((prev) => [...prev, item.data]);
              break;
            case 'note':
              setNotes(item.data);
              break;
            case 'connection':
              setConnections((prev) => [...prev, item.data]);
              break;
            case 'action':
              setActions((prev) => [...prev, item.data]);
              break;
          }
        }

        setProgress(100);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to process annotations');
      } finally {
        setIsProcessing(false);
      }
    },
    [apiKey]
  );

  const reset = useCallback(() => {
    setIsProcessing(false);
    setProgress(0);
    setInsights([]);
    setNotes(null);
    setConnections([]);
    setActions([]);
    setError(null);
    agentRef.current = null;
  }, []);

  return {
    isProcessing,
    progress,
    insights,
    notes,
    connections,
    actions,
    error,
    processAnnotations,
    reset,
  };
}
