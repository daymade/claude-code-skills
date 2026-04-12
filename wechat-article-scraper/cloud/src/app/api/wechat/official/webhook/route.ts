/**
 * WeChat Official Account Webhook Handler
 * Round 92: WeChat Ecosystem Integration
 *
 * Handles incoming messages from WeChat Official Account
 * - URL extraction and validation
 * - Async article scraping
 * - User binding flow
 */

import { createClient } from '@supabase/supabase-js';
import { NextRequest } from 'next/server';
import crypto from 'crypto';

// Initialize Supabase client
const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
);

// WeChat Official Account config
const WECHAT_TOKEN = process.env.WECHAT_OFFICIAL_TOKEN!;
const WECHAT_APPID = process.env.WECHAT_OFFICIAL_APPID!;
const WECHAT_SECRET = process.env.WECHAT_OFFICIAL_SECRET!;

interface WeChatMessage {
  ToUserName: string;
  FromUserName: string;
  CreateTime: number;
  MsgType: string;
  Content?: string;
  MsgId?: number;
  Event?: string;
  EventKey?: string;
}

/**
 * Verify WeChat signature for GET requests (server validation)
 */
function verifyWechatSignature(
  signature: string,
  timestamp: string,
  nonce: string
): boolean {
  const params = [WECHAT_TOKEN, timestamp, nonce].sort().join('');
  const hash = crypto.createHash('sha1').update(params).digest('hex');
  return hash === signature;
}

/**
 * Extract URL from message content
 */
function extractUrl(content: string): string | null {
  const urlRegex = /https?:\/\/[^\s<>"{}|\\^`\[\]]+/gi;
  const matches = content.match(urlRegex);
  return matches ? matches[0] : null;
}

/**
 * Check if URL is a WeChat article
 */
function isWechatArticle(url: string): boolean {
  return /mp\.weixin\.qq\.com/.test(url) ||
         /weixin\.qq\.com/.test(url);
}

/**
 * Parse XML message from WeChat
 */
function parseXmlMessage(xml: string): WeChatMessage {
  const result: Partial<WeChatMessage> = {};

  const toUserMatch = xml.match(/<ToUserName>([^<]+)<\/ToUserName>/);
  const fromUserMatch = xml.match(/<FromUserName>([^<]+)<\/FromUserName>/);
  const createTimeMatch = xml.match(/<CreateTime>(\d+)<\/CreateTime>/);
  const msgTypeMatch = xml.match(/<MsgType>([^<]+)<\/MsgType>/);
  const contentMatch = xml.match(/<Content>([^<]*)<\/Content>/);
  const msgIdMatch = xml.match(/<MsgId>(\d+)<\/MsgId>/);
  const eventMatch = xml.match(/<Event>([^<]+)<\/Event>/);

  if (toUserMatch) result.ToUserName = toUserMatch[1];
  if (fromUserMatch) result.FromUserName = fromUserMatch[1];
  if (createTimeMatch) result.CreateTime = parseInt(createTimeMatch[1]);
  if (msgTypeMatch) result.MsgType = msgTypeMatch[1];
  if (contentMatch) result.Content = contentMatch[1];
  if (msgIdMatch) result.MsgId = parseInt(msgIdMatch[1]);
  if (eventMatch) result.Event = eventMatch[1];

  return result as WeChatMessage;
}

/**
 * Build XML response for WeChat
 */
function buildXmlResponse(
  toUser: string,
  fromUser: string,
  content: string
): string {
  const timestamp = Math.floor(Date.now() / 1000);
  return `<xml>
<ToUserName><![CDATA[${toUser}]]></ToUserName>
<FromUserName><![CDATA[${fromUser}]]></FromUserName>
<CreateTime>${timestamp}</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[${content}]]></Content>
</xml>`;
}

/**
 * Get or create user by WeChat OpenID
 */
async function getOrCreateUser(openid: string): Promise<string | null> {
  // Check existing binding
  const { data: existing } = await supabase
    .from('wechat_bindings')
    .select('user_id')
    .eq('openid', openid)
    .eq('app_type', 'official')
    .single();

  if (existing) {
    // Update last used
    await supabase
      .from('wechat_bindings')
      .update({ last_used_at: new Date().toISOString() })
      .eq('openid', openid)
      .eq('app_type', 'official');
    return existing.user_id;
  }

  return null;
}

/**
 * Create scrape job for article
 */
async function createScrapeJob(
  url: string,
  userId: string | null,
  openid: string
): Promise<string> {
  const { data, error } = await supabase
    .from('scrape_jobs')
    .insert({
      url,
      user_id: userId,
      source: 'wechat_official',
      priority: 'high',
      status: 'pending',
      metadata: { openid }
    })
    .select('id')
    .single();

  if (error) throw error;
  return data.id;
}

/**
 * Check if article already exists
 */
async function findExistingArticle(
  userId: string | null,
  url: string
): Promise<{ id: string; title: string } | null> {
  if (!userId) return null;

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
 * GET handler - WeChat server validation
 */
export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const signature = searchParams.get('signature') || '';
  const timestamp = searchParams.get('timestamp') || '';
  const nonce = searchParams.get('nonce') || '';
  const echostr = searchParams.get('echostr') || '';

  if (!verifyWechatSignature(signature, timestamp, nonce)) {
    return new Response('Invalid signature', { status: 401 });
  }

  return new Response(echostr);
}

/**
 * POST handler - Process incoming messages
 */
export async function POST(request: NextRequest) {
  try {
    // Verify signature
    const searchParams = request.nextUrl.searchParams;
    const signature = searchParams.get('signature') || '';
    const timestamp = searchParams.get('timestamp') || '';
    const nonce = searchParams.get('nonce') || '';

    if (!verifyWechatSignature(signature, timestamp, nonce)) {
      return new Response('Invalid signature', { status: 401 });
    }

    // Parse message
    const xmlBody = await request.text();
    const message = parseXmlMessage(xmlBody);

    // Log message for debugging
    await supabase.from('wechat_message_logs').insert({
      app_type: 'official',
      openid: message.FromUserName,
      msg_type: message.MsgType,
      content: message.Content,
      raw_payload: message
    });

    // Handle different message types
    let responseContent = '';

    if (message.MsgType === 'event') {
      // Handle subscription/unsubscription
      if (message.Event === 'subscribe') {
        responseContent = `🎉 欢迎订阅文章收藏助手！

使用说明：
1️⃣ 在公众号对话框发送微信公众号文章链接
2️⃣ 系统自动保存文章内容
3️⃣ 保存完成后会收到通知

💡 提示：首次使用需要绑定账号，请访问：
${process.env.NEXT_PUBLIC_APP_URL}/wechat/bind`;
      }
    } else if (message.MsgType === 'text' && message.Content) {
      const url = extractUrl(message.Content);

      if (url) {
        if (isWechatArticle(url)) {
          // Get or create user
          const userId = await getOrCreateUser(message.FromUserName);

          // Check if already saved
          const existing = await findExistingArticle(userId, url);

          if (existing) {
            responseContent = `✅ 该文章已在您的收藏中

📖 ${existing.title}

👉 点击阅读：${process.env.NEXT_PUBLIC_APP_URL}/articles/${existing.id}`;
          } else {
            // Create scrape job
            const jobId = await createScrapeJob(url, userId, message.FromUserName);

            if (userId) {
              responseContent = `🔄 正在保存文章，请稍候...

预计 10-30 秒完成，完成后将通知您。

任务ID: ${jobId}`;

              // Trigger async processing
              processScrapeJob(jobId, url, userId, message.FromUserName);
            } else {
              responseContent = `⚠️ 请先绑定账号后再保存文章

绑定链接：${process.env.NEXT_PUBLIC_APP_URL}/wechat/bind?openid=${message.FromUserName}`;
            }
          }
        } else {
          responseContent = '❌ 请发送微信公众号文章链接（mp.weixin.qq.com 域名）';
        }
      } else {
        responseContent = `👋 收到您的消息！

请直接发送微信公众号文章链接，我会自动为您保存。

💡 提示：链接格式应为 https://mp.weixin.qq.com/s/...`;
      }
    }

    // Return XML response
    const xmlResponse = buildXmlResponse(
      message.FromUserName,
      message.ToUserName,
      responseContent
    );

    return new Response(xmlResponse, {
      headers: { 'Content-Type': 'application/xml' }
    });

  } catch (error) {
    console.error('Webhook error:', error);
    return new Response('Internal error', { status: 500 });
  }
}

/**
 * Process scrape job asynchronously
 */
async function processScrapeJob(
  jobId: string,
  url: string,
  userId: string,
  openid: string
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

    // Call scrape API
    const response = await fetch(`${process.env.NEXT_PUBLIC_APP_URL}/api/scrape`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url,
        userId,
        source: 'wechat_official'
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

    // Send completion notification (would integrate with WeChat API in production)
    console.log(`Article saved: ${result.articleId} for user ${userId}`);

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
