/**
 * WeChat Mini Program Save API
 * Round 92: WeChat Ecosystem Integration
 *
 * Handles article saving from Mini Program
 * - Authentication via WeChat login code
 * - URL validation
 * - Async scrape job creation
 */

import { createClient } from '@supabase/supabase-js';
import { NextRequest } from 'next/server';

// Initialize Supabase client
const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
);

// WeChat Mini Program config
const WECHAT_APPID = process.env.WECHAT_MINIAPP_APPID!;
const WECHAT_SECRET = process.env.WECHAT_MINIAPP_SECRET!;

interface MiniAppLoginResponse {
  openid: string;
  session_key: string;
  unionid?: string;
  errcode?: number;
  errmsg?: string;
}

interface SaveRequest {
  url: string;
  title?: string;
  code: string; // WeChat login code
}

/**
 * Exchange WeChat login code for openid
 */
async function code2Session(code: string): Promise<MiniAppLoginResponse> {
  const url = `https://api.weixin.qq.com/sns/jscode2session?appid=${WECHAT_APPID}&secret=${WECHAT_SECRET}&js_code=${code}&grant_type=authorization_code`;

  const response = await fetch(url);
  const data = await response.json();

  if (data.errcode) {
    throw new Error(`WeChat API error: ${data.errmsg} (${data.errcode})`);
  }

  return data;
}

/**
 * Get or create user by WeChat OpenID
 */
async function getOrCreateUser(
  openid: string,
  sessionKey: string,
  unionid?: string
): Promise<string> {
  // Check existing binding
  const { data: existing } = await supabase
    .from('wechat_bindings')
    .select('user_id')
    .eq('openid', openid)
    .eq('app_type', 'miniapp')
    .single();

  if (existing) {
    // Update session key and last used
    await supabase
      .from('wechat_bindings')
      .update({
        session_key: sessionKey,
        last_used_at: new Date().toISOString()
      })
      .eq('openid', openid)
      .eq('app_type', 'miniapp');

    return existing.user_id;
  }

  // Create new user
  const { data: user, error: userError } = await supabase.auth.admin.createUser({
    email: `wechat_${openid}@miniapp.local`,
    email_confirm: true,
    user_metadata: {
      source: 'wechat_miniapp',
      openid
    }
  });

  if (userError) throw userError;

  // Create binding
  await supabase.from('wechat_bindings').insert({
    user_id: user.user!.id,
    openid,
    unionid,
    app_type: 'miniapp',
    session_key: sessionKey
  });

  // Create default workspace
  await supabase.from('workspaces').insert({
    name: '我的收藏',
    slug: `user-${user.user!.id.slice(0, 8)}`,
    owner_id: user.user!.id
  });

  return user.user!.id;
}

/**
 * Validate WeChat article URL
 */
function isValidWechatUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return parsed.hostname.includes('mp.weixin.qq.com') ||
           parsed.hostname.includes('weixin.qq.com');
  } catch {
    return false;
  }
}

/**
 * Check if article already exists for user
 */
async function findExistingArticle(
  userId: string,
  url: string
): Promise<{ id: string; title: string } | null> {
  const { data } = await supabase
    .rpc('find_existing_article', {
      p_user_id: userId,
      p_url: url
    });

  if (data && data.length > 0) {
    const { data: article } = await supabase
      .from('articles')
      .select('id, title')
      .eq('id', data[0].article_id)
      .single();
    return article;
  }

  return null;
}

/**
 * Create scrape job
 */
async function createScrapeJob(
  url: string,
  userId: string,
  title?: string
): Promise<string> {
  // Get user's default workspace
  const { data: workspace } = await supabase
    .from('workspaces')
    .select('id')
    .eq('owner_id', userId)
    .order('created_at', { ascending: true })
    .limit(1)
    .single();

  if (!workspace) {
    throw new Error('No workspace found for user');
  }

  const { data, error } = await supabase
    .from('scrape_jobs')
    .insert({
      url,
      user_id: userId,
      workspace_id: workspace.id,
      source: 'wechat_miniapp',
      priority: 'high',
      status: 'pending',
      metadata: { title }
    })
    .select('id')
    .single();

  if (error) throw error;
  return data.id;
}

/**
 * POST handler - Save article from Mini Program
 */
export async function POST(request: NextRequest) {
  try {
    const body: SaveRequest = await request.json();
    const { url, title, code } = body;

    // Validate input
    if (!url || !code) {
      return Response.json(
        { error: 'Missing required fields: url, code' },
        { status: 400 }
      );
    }

    // Validate URL
    if (!isValidWechatUrl(url)) {
      return Response.json(
        { error: 'Invalid WeChat article URL' },
        { status: 400 }
      );
    }

    // Exchange code for openid
    let sessionData: MiniAppLoginResponse;
    try {
      sessionData = await code2Session(code);
    } catch (error) {
      return Response.json(
        { error: 'Invalid WeChat login code', details: error instanceof Error ? error.message : 'Unknown error' },
        { status: 401 }
      );
    }

    // Get or create user
    const userId = await getOrCreateUser(
      sessionData.openid,
      sessionData.session_key,
      sessionData.unionid
    );

    // Check if already saved
    const existing = await findExistingArticle(userId, url);

    if (existing) {
      return Response.json({
        success: true,
        articleId: existing.id,
        title: existing.title,
        message: 'Article already saved',
        duplicate: true
      });
    }

    // Create scrape job
    const jobId = await createScrapeJob(url, userId, title);

    // Trigger async processing
    processScrapeJob(jobId, url, userId);

    return Response.json({
      success: true,
      jobId,
      status: 'processing',
      message: 'Article is being saved'
    });

  } catch (error) {
    console.error('MiniApp save error:', error);
    return Response.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}

/**
 * GET handler - Check job status
 */
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;
    const jobId = searchParams.get('jobId');

    if (!jobId) {
      return Response.json(
        { error: 'Missing jobId parameter' },
        { status: 400 }
      );
    }

    const { data: job, error } = await supabase
      .from('scrape_jobs')
      .select('*')
      .eq('id', jobId)
      .single();

    if (error || !job) {
      return Response.json(
        { error: 'Job not found' },
        { status: 404 }
      );
    }

    return Response.json({
      jobId: job.id,
      status: job.status,
      result: job.result,
      error: job.error_message,
      createdAt: job.created_at,
      completedAt: job.completed_at
    });

  } catch (error) {
    console.error('Status check error:', error);
    return Response.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}

/**
 * Process scrape job asynchronously
 */
async function processScrapeJob(
  jobId: string,
  url: string,
  userId: string
): Promise<void> {
  try {
    // Update job status
    await supabase
      .from('scrape_jobs')
      .update({
        status: 'processing',
        started_at: new Date().toISOString()
      })
      .eq('id', jobId);

    // Call internal scrape API
    const response = await fetch(`${process.env.NEXT_PUBLIC_APP_URL}/api/scrape`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url,
        userId,
        source: 'wechat_miniapp'
      })
    });

    if (!response.ok) {
      throw new Error(`Scrape failed: ${response.statusText}`);
    }

    const result = await response.json();

    // Update job as completed
    await supabase
      .from('scrape_jobs')
      .update({
        status: 'completed',
        completed_at: new Date().toISOString(),
        result
      })
      .eq('id', jobId);

  } catch (error) {
    // Update job as failed
    await supabase
      .from('scrape_jobs')
      .update({
        status: 'failed',
        error_message: error instanceof Error ? error.message : 'Unknown error',
        completed_at: new Date().toISOString()
      })
      .eq('id', jobId);

    console.error(`Job ${jobId} failed:`, error);
  }
}
