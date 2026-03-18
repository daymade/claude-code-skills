# YouTube Downloader Internal SOP

Use this SOP to avoid common yt-dlp failures and confusion:

1. Quote YouTube URLs in shell commands (zsh treats `?` as glob). Example: `'https://www.youtube.com/watch?v=VIDEO_ID'`.
2. Ensure proxy is active for both yt-dlp and PO Token providers (HTTP_PROXY/HTTPS_PROXY/ALL_PROXY).
3. If you see "Sign in to confirm you're not a bot", request cookie permission and use browser cookies.
4. Start the PO Token provider before downloading. Prefer Docker bgutil; fall back to browser-based WPC when Docker is unavailable or fails.
5. Use `web_safari` client when cookies are present; otherwise use `mweb` for PO tokens.
6. Keep the browser window open while WPC is minting tokens and make sure it can reach YouTube through the same proxy.
7. If you see "Only images are available" or "Requested format is not available", treat it as PO token failure and retry after fixing provider/browser state.
8. If you see SSL EOF or fragment errors, treat it as proxy instability. Retry with progressive formats or switch to a more stable proxy.
