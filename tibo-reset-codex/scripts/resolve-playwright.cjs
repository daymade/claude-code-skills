'use strict';

const path = require('node:path');

function loadPlaywright() {
  try {
    return require('playwright');
  } catch (error) {
    if (error?.code !== 'MODULE_NOT_FOUND' || !/Cannot find module 'playwright'/.test(error.message)) {
      throw error;
    }
  }

  const fallback = process.env.TIBO_PLAYWRIGHT_PATH || (process.env.HOME
    ? path.join(process.env.HOME, '.chrome-profiles', 'tibo-cdp', 'node_modules', 'playwright')
    : null);
  if (!fallback) {
    throw new Error('Playwright 未就绪：请安装依赖，或设置 TIBO_PLAYWRIGHT_PATH 为 playwright 包的绝对路径');
  }
  try {
    return require(fallback);
  } catch (error) {
    throw new Error(`Playwright 未就绪：无法从 ${fallback} 加载；请修复该依赖或设置 TIBO_PLAYWRIGHT_PATH`, { cause: error });
  }
}

module.exports = loadPlaywright;
