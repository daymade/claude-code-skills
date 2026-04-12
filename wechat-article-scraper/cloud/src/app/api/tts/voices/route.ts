/**
 * TTS Voices API
 * Returns available voices for Web Speech and Azure
 */

import { NextResponse } from 'next/server';

export interface VoiceInfo {
  id: string;
  name: string;
  lang: string;
  gender: 'male' | 'female' | 'neutral';
  provider: 'webspeech' | 'azure';
  quality: 'standard' | 'high' | 'neural';
}

const AZURE_VOICES: VoiceInfo[] = [
  // Chinese voices
  { id: 'zh-CN-XiaoxiaoNeural', name: '晓晓', lang: 'zh-CN', gender: 'female', provider: 'azure', quality: 'neural' },
  { id: 'zh-CN-YunyangNeural', name: '云扬', lang: 'zh-CN', gender: 'male', provider: 'azure', quality: 'neural' },
  { id: 'zh-CN-YunxiNeural', name: '云希', lang: 'zh-CN', gender: 'male', provider: 'azure', quality: 'neural' },
  { id: 'zh-CN-XiaoyiNeural', name: '晓伊', lang: 'zh-CN', gender: 'female', provider: 'azure', quality: 'neural' },
  { id: 'zh-CN-YunjianNeural', name: '云健', lang: 'zh-CN', gender: 'male', provider: 'azure', quality: 'neural' },
  { id: 'zh-HK-HiuMaanNeural', name: '曉曼', lang: 'zh-HK', gender: 'female', provider: 'azure', quality: 'neural' },
  { id: 'zh-HK-HiuGaaiNeural', name: '曉佳', lang: 'zh-HK', gender: 'female', provider: 'azure', quality: 'neural' },
  { id: 'zh-TW-HsiaoChenNeural', name: '曉臻', lang: 'zh-TW', gender: 'female', provider: 'azure', quality: 'neural' },
  { id: 'zh-TW-YunJheNeural', name: '雲哲', lang: 'zh-TW', gender: 'male', provider: 'azure', quality: 'neural' },
  // English voices
  { id: 'en-US-JennyNeural', name: 'Jenny', lang: 'en-US', gender: 'female', provider: 'azure', quality: 'neural' },
  { id: 'en-US-GuyNeural', name: 'Guy', lang: 'en-US', gender: 'male', provider: 'azure', quality: 'neural' },
  { id: 'en-GB-SoniaNeural', name: 'Sonia', lang: 'en-GB', gender: 'female', provider: 'azure', quality: 'neural' },
  { id: 'en-GB-RyanNeural', name: 'Ryan', lang: 'en-GB', gender: 'male', provider: 'azure', quality: 'neural' },
  // Japanese voices
  { id: 'ja-JP-NanamiNeural', name: '七海', lang: 'ja-JP', gender: 'female', provider: 'azure', quality: 'neural' },
  { id: 'ja-JP-KeitaNeural', name: '圭太', lang: 'ja-JP', gender: 'male', provider: 'azure', quality: 'neural' },
  // Korean voices
  { id: 'ko-KR-SunHiNeural', name: '선희', lang: 'ko-KR', gender: 'female', provider: 'azure', quality: 'neural' },
  { id: 'ko-KR-InJoonNeural', name: '인준', lang: 'ko-KR', gender: 'male', provider: 'azure', quality: 'neural' },
];

/**
 * GET /api/tts/voices
 * Get available TTS voices
 */
export async function GET() {
  try {
    // Web Speech voices are client-side only, so we return Azure voices
    // Client can merge with local SpeechSynthesis voices
    return NextResponse.json({
      voices: AZURE_VOICES,
      webspeech: false, // Client needs to check SpeechSynthesis
    });
  } catch (error) {
    console.error('Get voices error:', error);
    return NextResponse.json(
      { error: 'Failed to get voices' },
      { status: 500 }
    );
  }
}
