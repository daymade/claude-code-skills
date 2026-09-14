-- word_export_pdf.applescript — export an existing .docx to PDF via the REAL Microsoft Word
-- app, using the same menu path a human would click. Use this whenever fidelity to Word
-- (fonts, pagination) matters more than convenience — see references/word-to-pdf.md Step 5
-- for when that is.
--
-- Usage:
--   osascript word_export_pdf.applescript <source.docx> <output-basename>
--
-- Writes <basename>.pdf into the SAME DIRECTORY as <source.docx> — the script always opens
-- (or reuses) the document there, so saving to that same folder needs no folder navigation
-- and has round-tripped reliably in testing, cold-launch and already-open alike. If you need
-- the PDF elsewhere (word-to-pdf.md's "new output directory" step), `mv`/`cp` the result
-- afterward; that's one shell command and far more reliable than automating Word's own Save
-- panel's folder navigation, which this script deliberately does NOT attempt — Cmd+Shift+G
-- "Go to Folder" does not work inside Word's save sheet the way it does in Finder, and
-- driving the expanded panel's sidebar/breadcrumb via raw UI-element clicks was tried and
-- found too fragile to bundle.
--
-- PREREQUISITE: the calling process needs Accessibility permission (System Settings >
-- Privacy & Security > Accessibility) and, on first run, will be prompted for Automation
-- consent to control both "System Events" and "Microsoft Word". In a non-interactive context
-- with neither already granted, this script will hang waiting on a permission dialog it
-- cannot see, rather than erroring — grant both once, interactively, before automating.
--
-- Re-running with the same <output-basename> overwrites any previous PDF from an earlier run
-- of this script at that path (deleted before export, not overwritten via a dialog — see the
-- "already exists" note below).
--
-- Verified on: Microsoft Word for Mac, Chinese (Simplified) UI locale, 2026-09. NOT verified
-- on other locales — every UI string this script clicks by name (menu items, field labels,
-- the "另存为.../导出" flow) is a Chinese-locale label, and on a different-locale Word build
-- the very first menu click will fail with an accessibility "can't get menu item" error. The
-- MECHANISM (drive the real menu/window, never AppleScript's own `save as`/`open` verbs) is
-- the portable lesson even where you have to substitute the exact strings for your locale.
--
-- WHY THIS GOES THROUGH THE MENU, NOT THROUGH AppleScript'S OWN `save as` VERB:
-- The obvious one-liner —
--   tell application "Microsoft Word"
--     save as theDoc file name (POSIX file "/path/out.pdf") file format format PDF
--   end tell
-- reliably triggers a macOS sandbox "Grant File Access" dialog for ANY output path, even a
-- path in the same folder Word already opened the source document from (opening a file for
-- READ does not imply a WRITE grant for a new path). That dialog is a `sheet` containing a
-- full NSOpenPanel, and it is NOT reliably dismissible by keystroke or naive button-click
-- automation: Return does nothing, and the dialog's own "Choose..." button opens a *nested*
-- folder-picker sheet that is itself impractical to drive (its confirm control sits several
-- levels deep and a full recursive UI-tree dump to find it is slow enough to time out the
-- whole automation). Driving Word's own File menu instead uses the standard NSSavePanel
-- "powerbox" grant flow, which does not trigger that dialog at all — because interacting
-- with a user-facing system panel is itself the consent, the same reason a human clicking
-- through Finder's Save dialog never sees a permission prompt.

on run argv
	if (count of argv) < 2 then
		error "usage: word_export_pdf.applescript <source.docx> <output-basename>"
	end if
	set srcPath to item 1 of argv
	set outBase to item 2 of argv
	set outDir to my dirnameOf(srcPath)
	set outPath to outDir & "/" & outBase & ".pdf"

	-- Identify whether srcPath is already open — matching by FILENAME (`name of document`),
	-- not by full path. This isn't the obviously-more-precise choice; it's the choice that
	-- survived testing. The precise-looking alternative — compare `POSIX path of (full name
	-- of d)` against srcPath — was tried first and abandoned: `full name` reliably returned
	-- `missing value` for whichever open document was NOT the one Word currently considers
	-- active, in a way that did not reliably fix even after explicitly `activate`-ing that
	-- document first (worked in isolated manual tests, then failed again under the same
	-- conditions minutes later — genuinely flaky, not a mistake in how it was called). A
	-- property this unreliable cannot be the thing a "did we export the right document" check
	-- depends on. `name of document` and `name of window 1 of document`, by contrast, were
	-- reliable in every test regardless of which document was frontmost.
	--
	-- The real risk this exists to prevent — matching by name and then silently acting on the
	-- WRONG same-named document — is handled differently as a result: rather than trying to
	-- disambiguate automatically via a property that can't be trusted, MULTIPLE open documents
	-- sharing srcPath's filename is treated as genuinely ambiguous and fails loudly (see
	-- below), instead of guessing. That is a real, disclosed limitation (two simultaneously
	-- open documents with the same filename need the others closed first), not a silent gap.
	set srcName to my basenameOf(srcPath)
	set targetDoc to missing value
	set matchCount to 0
	tell application "Microsoft Word"
		if it is running then
			set n to count of documents
			repeat with i from 1 to n
				set d to document i
				if (name of d) is srcName then
					set matchCount to matchCount + 1
					set targetDoc to d
				end if
			end repeat
		end if
	end tell

	if matchCount > 1 then
		error "found " & matchCount & " open documents named '" & srcName & "' — can't safely tell which is " & srcPath & ". Close the others (or save this one under a name that doesn't collide) and re-run."
	end if

	if targetDoc is missing value then
		-- CRITICAL: open via `open -a` (LaunchServices — the same mechanism a Finder
		-- double-click uses), NOT AppleScript's `open POSIX file` verb sent to Word.
		-- On a cold-launched Word process, `open POSIX file` does NOT carry the sandbox
		-- write-grant the menu-driven Save As below depends on, so the Grant File Access
		-- dialog reappears even for a document in a folder Word has saved to before in a
		-- PREVIOUS process — the grant is apparently tied to how THIS process's open
		-- happened, not just to the folder. A LaunchServices-mediated open (`open -a`)
		-- counts as user intent to the sandbox and avoids the dialog on the very next
		-- save, same as double-clicking the file in Finder would.
		do shell script "open -a 'Microsoft Word' " & quoted form of srcPath
		-- Poll for the newly-opened document to actually appear (menu-bar existing is only
		-- app-level readiness — a cold, first-run launch can still be mid-open after that).
		repeat with i from 1 to 30
			delay 1
			tell application "Microsoft Word"
				set n to count of documents
				repeat with j from 1 to n
					set d to document j
					if (name of d) is srcName then
						set targetDoc to d
						exit repeat
					end if
				end repeat
			end tell
			if targetDoc is not missing value then exit repeat
		end repeat
		if targetDoc is missing value then
			error "opened " & srcPath & " but it never appeared among Word's open documents within 30s — check for a blocked Accessibility/Automation permission prompt (see this script's PREREQUISITE comment)."
		end if
	end if

	-- Bring the CORRECT document's window to front — `activate` sent to a Word document
	-- object (as opposed to the application) does not actually raise its window on Word for
	-- Mac (confirmed by direct test: it returns success but the wrong window stays frontmost
	-- with two documents open). The reliable mechanism is the same one a human would use: the
	-- Window menu lists every open document by its window title, and clicking that entry
	-- raises it.
	--
	-- MATCH THE WINDOW MENU ITEM BY THE EXACT TITLE OF targetDoc'S OWN WINDOW, never by a
	-- derived prefix — `name of window 1 of targetDoc` was reliable in every test regardless
	-- of frontmost state (unlike `full name`, above), and gives the exact title Word assigned
	-- (including any " - 兼容性模式" suffix, so it needn't be predicted). Since targetDoc was
	-- already uniquely identified above (or the ambiguous case already failed loudly), this
	-- exact-title match cannot collide with a different, same-prefixed document the way an
	-- earlier version's prefix match did.
	set exactTitle to name of window 1 of targetDoc

	tell application "Microsoft Word" to activate
	tell application "System Events"
		tell process "Microsoft Word"
			set raised to false
			-- The document can still be mid-open right after a cold launch even though
			-- Word's menu bar already exists (menu-bar readiness is app-level, not
			-- per-document), so retry the Window-menu lookup briefly rather than failing on
			-- the first enumeration.
			repeat with attempt from 1 to 10
				repeat with mi in menu items of menu 1 of menu bar item "窗口" of menu bar 1
					if (name of mi as string) is exactTitle then
						click mi
						set raised to true
						exit repeat
					end if
				end repeat
				if raised then exit repeat
				delay 1
			end repeat
			if not raised then
				error "could not find the window titled '" & exactTitle & "' in the Window menu after 10s — it may not have finished opening."
			end if
		end tell
	end tell

	-- A prior run of this script against the same <output-basename> leaves a PDF at outPath;
	-- Word's Save panel would raise an unhandled "already exists — replace it?" confirmation
	-- for that, which this script does not detect or dismiss (word-to-pdf.md's own Step 6
	-- explicitly expects "repair failures and rerender" as a normal loop, so hitting this on
	-- a second run is the common case, not an edge case). Since the caller controls
	-- <output-basename> and this script's whole contract is "regenerate the PDF", deleting a
	-- stale prior output before re-exporting is the correct behavior, not data loss.
	try
		do shell script "rm -f " & quoted form of outPath
	end try

	tell application "System Events"
		tell process "Microsoft Word"
			-- Step 1: open the real Save As sheet via the menu (Chinese-locale label; see
			-- the locale note in the header comment).
			click menu item "另存为..." of menu 1 of menu bar item "文件" of menu bar 1
			delay 1

			set theSheet to sheet 1 of front window
			set sg to UI element 1 of theSheet

			-- Step 2: set the filename.
			set value of text field "保存为：" of sg to outBase

			-- Step 3: switch format to PDF. THIS IS WHERE THE SHEET'S LAYOUT CHANGES —
			-- see the comment above the confirm-click below. (The fullwidth "：" on
			-- "保存为：" vs. the halfwidth ":" on "文件格式:" below is Word's own
			-- localization, verified by direct inspection, not a typo — don't "fix" it.)
			click pop up button "文件格式:" of sg
			delay 0.3
			click menu item "PDF" of menu 1 of pop up button "文件格式:" of sg
			delay 0.5

			-- Step 4: confirm. CRITICAL GOTCHA — after switching format to PDF, Word adds a
			-- quality-options radio group to the sheet AND RENAMES THE CONFIRM BUTTON from
			-- "保存" (Save) to "导出" (Export). Reusing a button reference obtained before
			-- the format switch, or hardcoding "保存", fails with an accessibility "Can't
			-- get button" error — the button you're looking for no longer exists under that
			-- name. Always re-query the sheet's current elements after changing the format
			-- popup, and target "导出" here, not "保存".
			set sg2 to UI element 1 of (sheet 1 of front window)
			click button "导出" of sg2
		end tell
	end tell

	-- Step 5: poll for the file rather than assuming the click succeeded synchronously —
	-- Word's own PDF export runs asynchronously after the click returns.
	set posixOut to POSIX file outPath
	set found to false
	repeat with i from 1 to 20
		delay 1
		try
			set fileSize to (get size of (info for posixOut))
			if fileSize > 0 then
				set found to true
				exit repeat
			end if
		end try
	end repeat

	if not found then
		error "PDF did not appear at " & outPath & " within 20s. The pre-delete step above rules out an unhandled 'already exists' dialog for THIS run, but check for one anyway if this script was edited; also check that the raised window (see above) was really '" & exactTitle & "' and not another document that grabbed focus in between."
	end if

	return outPath
end run

on basenameOf(p)
	set AppleScript's text item delimiters to "/"
	set parts to text items of p
	set AppleScript's text item delimiters to ""
	return item -1 of parts
end basenameOf

on dirnameOf(p)
	set AppleScript's text item delimiters to "/"
	set parts to text items of p
	set AppleScript's text item delimiters to "/"
	set d to items 1 thru -2 of parts as text
	set AppleScript's text item delimiters to ""
	return d
end dirnameOf
