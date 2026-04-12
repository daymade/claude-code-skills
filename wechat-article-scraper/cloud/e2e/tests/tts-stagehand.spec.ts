import { test, expect } from '@playwright/test';
import { Stagehand } from '@anthropic-ai/stagehand';
import { createTestUser, cleanupTestUser, createTestArticle } from '../utils/test-helpers';

/**
 * TTS Audio Player E2E Tests with Stagehand AI
 *
 * Tests: Audio generation → Playback controls → Speed adjustment
 * Using Stagehand for natural language interaction and visual verification
 */

test.describe('TTS Audio Player - Stagehand AI Tests', () => {
  let testUser: { id: string; email: string; token: string };
  let testArticleId: string;
  let stagehand: Stagehand;

  test.beforeAll(async ({ browser }) => {
    // Create test user and article
    testUser = await createTestUser();
    testArticleId = await createTestArticle(testUser.token, {
      title: 'TTS测试文章',
      content: `
        <p>这是第一段测试内容，用于验证语音合成功能是否正常工作。</p>
        <p>这是第二段内容，测试朗读时的段落切换。</p>
        <p>这是第三段内容，用于测试快进和暂停功能。</p>
      `,
    });

    // Initialize Stagehand with Anthropic AI
    stagehand = new Stagehand({
      browser,
      model: 'claude-sonnet-4-6',
      vision: true,
    });
  });

  test.afterAll(async () => {
    await stagehand.close();
    await cleanupTestUser(testUser.id);
  });

  test.beforeEach(async () => {
    // Navigate to article and login
    await stagehand.goto(`/articles/${testArticleId}`);
    await stagehand.act('Login with test user credentials if login form is present');
  });

  test('should display audio player with play button', async () => {
    // Use Stagehand to verify UI elements visually
    const hasAudioPlayer = await stagehand.ask(
      'Can you see an audio player component with a play button on the page?'
    );
    expect(hasAudioPlayer).toBe(true);

    // Verify play button is visible and clickable
    await stagehand.act('Click the play button in the audio player');

    // Verify player enters playing state
    const isPlaying = await stagehand.ask(
      'Is the audio player now showing a pause button instead of play, indicating it is playing?'
    );
    expect(isPlaying).toBe(true);
  });

  test('should play audio and show progress', async () => {
    // Start playback
    await stagehand.act('Click the play button');

    // Wait for audio to start
    await stagehand.wait(2000);

    // Verify progress is being tracked
    const hasProgress = await stagehand.ask(
      'Can you see a progress bar that has started to fill, showing the current playback position?'
    );
    expect(hasProgress).toBe(true);

    // Verify segment counter
    const showsSegment = await stagehand.ask(
      'Does the audio player show something like "段落 1 / 3" indicating the current segment?'
    );
    expect(showsSegment).toBe(true);
  });

  test('should pause and resume playback', async () => {
    // Start playing
    await stagehand.act('Click the play button');
    await stagehand.wait(3000);

    // Pause
    await stagehand.act('Click the pause button');

    // Verify paused state
    const isPaused = await stagehand.ask(
      'Is the audio player now showing a play button instead of pause, indicating it is paused?'
    );
    expect(isPaused).toBe(true);

    // Resume
    await stagehand.act('Click the play button to resume');

    // Verify playing again
    const isPlaying = await stagehand.ask('Is the audio player showing a pause button again?');
    expect(isPlaying).toBe(true);
  });

  test('should navigate between segments', async () => {
    // Start playing
    await stagehand.act('Click the play button');
    await stagehand.wait(2000);

    // Click next segment
    await stagehand.act('Click the next segment button (right arrow) in the audio player');

    // Verify segment changed
    const isSegment2 = await stagehand.ask(
      'Does the audio player now show "段落 2 / 3" or similar, indicating it moved to the second segment?'
    );
    expect(isSegment2).toBe(true);

    // Click previous
    await stagehand.act('Click the previous segment button (left arrow)');

    // Verify back to segment 1
    const isSegment1 = await stagehand.ask(
      'Does the audio player show "段落 1 / 3" again?'
    );
    expect(isSegment1).toBe(true);
  });

  test('should adjust playback speed', async () => {
    // Open speed menu
    await stagehand.act('Click the playback speed button that currently shows "1x"');

    // Select 1.5x speed
    await stagehand.act('Click the "1.5x" option in the speed dropdown menu');

    // Verify speed changed
    const shows15x = await stagehand.ask(
      'Does the speed button now show "1.5x" instead of "1x"?'
    );
    expect(shows15x).toBe(true);

    // Start playing to verify speed takes effect
    await stagehand.act('Click the play button');
    await stagehand.wait(2000);

    // Stop
    await stagehand.act('Click the stop button');
  });

  test('should display current segment text', async () => {
    // Start playing
    await stagehand.act('Click the play button');

    // Verify segment text is displayed
    const showsText = await stagehand.ask(
      'Can you see a text preview below the audio player controls showing the current segment content?'
    );
    expect(showsText).toBe(true);

    const textCorrect = await stagehand.ask(
      'Does the text preview contain "这是第一段测试内容"?'
    );
    expect(textCorrect).toBe(true);
  });

  test('should stop playback and reset position', async () => {
    // Play for a bit
    await stagehand.act('Click the play button');
    await stagehand.wait(3000);

    // Click next to move forward
    await stagehand.act('Click the next segment button');
    await stagehand.wait(1000);

    // Stop
    await stagehand.act('Click the stop button');

    // Verify reset
    const isReset = await stagehand.ask(
      'Does the audio player show "段落 1 / 3" and a play button, indicating it stopped and reset to the beginning?'
    );
    expect(isReset).toBe(true);
  });

  test('should handle errors gracefully', async () => {
    // Try to navigate to a non-existent article with TTS
    await stagehand.goto('/articles/invalid-id');

    // Check if error state is handled
    const handledGracefully = await stagehand.ask(
      'Does the page show a user-friendly error message or a fallback state for the audio player, rather than crashing?'
    );
    expect(handledGracefully).toBe(true);
  });
});
