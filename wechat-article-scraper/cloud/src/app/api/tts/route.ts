/**
 * TTS API Routes
 * Handles Azure TTS token generation and audio caching
 */

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
);

/**
 * GET /api/tts/azure-token
 * Get Azure TTS access token
 */
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const action = searchParams.get('action');

  if (action === 'azure-token') {
    return getAzureToken();
  }

  return NextResponse.json({ error: 'Invalid action' }, { status: 400 });
}

async function getAzureToken() {
  try {
    const azureKey = process.env.AZURE_TTS_KEY;
    const azureRegion = process.env.AZURE_TTS_REGION || 'eastasia';

    if (!azureKey) {
      return NextResponse.json(
        { error: 'Azure TTS not configured' },
        { status: 503 }
      );
    }

    const response = await fetch(
      `https://${azureRegion}.api.cognitive.microsoft.com/sts/v1.0/issueToken`,
      {
        method: 'POST',
        headers: {
          'Ocp-Apim-Subscription-Key': azureKey,
          'Content-Type': 'application/x-www-form-urlencoded',
        },
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to get token: ${response.status}`);
    }

    const token = await response.text();
    const expiry = Date.now() + 9 * 60 * 1000; // Token valid for 10 minutes, use 9

    return NextResponse.json({ token, expiry });
  } catch (error) {
    console.error('Azure TTS token error:', error);
    return NextResponse.json(
      { error: 'Failed to get Azure token' },
      { status: 500 }
    );
  }
}

/**
 * POST /api/tts
 * Synthesize text to speech
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { text, voice = 'zh-CN-XiaoxiaoNeural', rate = 1, pitch = 1 } = body;

    if (!text) {
      return NextResponse.json({ error: 'Text is required' }, { status: 400 });
    }

    const azureKey = process.env.AZURE_TTS_KEY;
    const azureRegion = process.env.AZURE_TTS_REGION || 'eastasia';

    if (!azureKey) {
      return NextResponse.json(
        { error: 'Azure TTS not configured' },
        { status: 503 }
      );
    }

    // Build SSML
    const ssml = `
      <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="zh-CN">
        <voice name="${voice}">
          <prosody rate="${(rate * 100).toFixed(0)}%" pitch="${(pitch * 100).toFixed(0)}%">
            ${escapeXml(text)}
          </prosody>
        </voice>
      </speak>
    `;

    const response = await fetch(
      `https://${azureRegion}.tts.speech.microsoft.com/cognitiveservices/v1`,
      {
        method: 'POST',
        headers: {
          'Ocp-Apim-Subscription-Key': azureKey,
          'Content-Type': 'application/ssml+xml',
          'X-Microsoft-OutputFormat': 'audio-24khz-160kbitrate-mono-mp3',
        },
        body: ssml,
      }
    );

    if (!response.ok) {
      throw new Error(`TTS synthesis failed: ${response.status}`);
    }

    const audioBuffer = await response.arrayBuffer();

    return new NextResponse(audioBuffer, {
      headers: {
        'Content-Type': 'audio/mpeg',
        'Cache-Control': 'public, max-age=86400',
      },
    });
  } catch (error) {
    console.error('TTS synthesis error:', error);
    return NextResponse.json(
      { error: 'Failed to synthesize speech' },
      { status: 500 }
    );
  }
}

function escapeXml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}
