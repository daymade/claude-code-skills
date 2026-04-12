/**
 * WeChat Mini Program Login API
 * Round 92: WeChat Ecosystem Integration
 *
 * Exchanges WeChat login code for session token
 */

import { createClient } from '@supabase/supabase-js';
import { NextRequest } from 'next/server';

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
);

const WECHAT_APPID = process.env.WECHAT_MINIAPP_APPID!;
const WECHAT_SECRET = process.env.WECHAT_MINIAPP_SECRET!;

interface Code2SessionResponse {
  openid: string;
  session_key: string;
  unionid?: string;
  errcode?: number;
  errmsg?: string;
}

/**
 * Exchange code for session
 */
async function code2Session(code: string): Promise<Code2SessionResponse> {
  const url = `https://api.weixin.qq.com/sns/jscode2session?appid=${WECHAT_APPID}&secret=${WECHAT_SECRET}&js_code=${code}&grant_type=authorization_code`;

  const response = await fetch(url);
  const data = await response.json();

  if (data.errcode) {
    throw new Error(`WeChat API error: ${data.errmsg} (${data.errcode})`);
  }

  return data;
}

/**
 * POST handler - Mini Program login
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { code } = body;

    if (!code) {
      return Response.json(
        { error: 'Missing code parameter' },
        { status: 400 }
      );
    }

    // Exchange code for openid
    const sessionData = await code2Session(code);

    // Check existing binding
    const { data: existing } = await supabase
      .from('wechat_bindings')
      .select('user_id')
      .eq('openid', sessionData.openid)
      .eq('app_type', 'miniapp')
      .single();

    let userId: string;

    if (existing) {
      // Update session key
      await supabase
        .from('wechat_bindings')
        .update({
          session_key: sessionData.session_key,
          last_used_at: new Date().toISOString()
        })
        .eq('openid', sessionData.openid)
        .eq('app_type', 'miniapp');

      userId = existing.user_id;
    } else {
      // Create new user
      const { data: authUser, error: authError } = await supabase.auth.admin.createUser({
        email: `wechat_${sessionData.openid.slice(0, 16)}@miniapp.local`,
        email_confirm: true,
        user_metadata: {
          source: 'wechat_miniapp',
          openid: sessionData.openid
        }
      });

      if (authError) {
        return Response.json(
          { error: 'Failed to create user', details: authError.message },
          { status: 500 }
        );
      }

      userId = authUser.user!.id;

      // Create binding
      await supabase.from('wechat_bindings').insert({
        user_id: userId,
        openid: sessionData.openid,
        unionid: sessionData.unionid,
        app_type: 'miniapp',
        session_key: sessionData.session_key
      });

      // Create default workspace
      await supabase.from('workspaces').insert({
        name: '我的收藏',
        slug: `user-${userId.slice(0, 8)}`,
        owner_id: userId
      });

      // Create user profile
      await supabase.from('profiles').insert({
        id: userId,
        full_name: '微信用户'
      });
    }

    // Create session
    const { data: session, error: sessionError } = await supabase.auth.admin.createUser({
      email: `session_${Date.now()}@temp.local`
    });

    if (sessionError) {
      return Response.json(
        { error: 'Failed to create session' },
        { status: 500 }
      );
    }

    // Generate JWT for Mini Program
    const { data: { session: userSession }, error: signError } = await supabase.auth.admin.signInWithIdToken({
      provider: 'supabase',
      token: userId,
    });

    if (signError) {
      // Fallback: create custom token
      const { data: tokenData, error: tokenError } = await supabase.rpc('create_miniapp_token', {
        p_user_id: userId
      });

      if (tokenError) {
        return Response.json(
          { error: 'Failed to generate token' },
          { status: 500 }
        );
      }

      return Response.json({
        token: tokenData,
        userId,
        isNew: !existing
      });
    }

    return Response.json({
      token: userSession?.access_token,
      userId,
      isNew: !existing
    });

  } catch (error) {
    console.error('MiniApp login error:', error);
    return Response.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
