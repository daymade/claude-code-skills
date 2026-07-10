-- Run a JavaScript file inside the Chrome tab whose URL contains a given substring.
-- Usage:  osascript runjs.applescript <js-file> <url-substring>
-- Prints the script's final expression to stdout ("TAB_NOT_FOUND" if no tab matched).
--
-- Requires (user-enabled, one time): Chrome menu
--   View > Developer > Allow JavaScript from Apple Events
-- See references/applescript_fallback_channel.md for the full channel guide.

on run argv
	if (count of argv) < 2 then
		return "USAGE: osascript runjs.applescript <js-file> <url-substring>"
	end if
	set jsFile to item 1 of argv
	set urlMatch to item 2 of argv
	set jsCode to read POSIX file jsFile as «class utf8»
	tell application "Google Chrome"
		repeat with w in windows
			repeat with t in tabs of w
				if URL of t contains urlMatch then
					return execute t javascript jsCode
				end if
			end repeat
		end repeat
	end tell
	return "TAB_NOT_FOUND"
end run
