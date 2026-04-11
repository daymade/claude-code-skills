export interface Article {
  id: number;
  url: string;
  title: string;
  author: string;
  publish_time: string;
  content: string;
  content_hash: string;
  images: { src: string; alt?: string; width?: number; height?: number }[];
  videos: { src?: string; poster?: string; title?: string; duration?: string }[];
  engagement: { readCount?: number | string; likeCount?: number | string; watchCount?: number | string; commentCount?: number | string } | null;
  wci_score: number | null;
  category: string;
  strategy: string;
  content_status: string;
  created_at: string;
  updated_at: string;
}

export interface Queue {
  id: string;
  name: string;
  status: 'idle' | 'running' | 'paused' | 'stopping' | 'stopped';
  total_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface Task {
  id: number;
  queue_id: string;
  task_type: 'scrape' | 'search';
  target: string;
  status: string;
  priority: number;
  retry_count: number;
  max_retries: number;
  result: any;
  error_message: string;
  created_at: string;
}

export interface QueueStatus {
  queue_id: string;
  name: string;
  status: string;
  total_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  progress: {
    percentage: number;
    completed: number;
    failed: number;
    remaining: number;
  };
}

export interface Statistics {
  total_articles: number;
  top_authors: { author: string; count: number }[];
  category_distribution: { category: string; count: number }[];
  wci_distribution: { level: string; count: number }[];
  database_path: string;
  generated_at: string;
}

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}
