# Permission And Failure Boundaries

## Allowed

- Access public KDocs/WPS/ProcessOn endpoints that load without authentication.
- Use the user's already-open browser session only to view content the user can legitimately access.
- Save local copies of source JSON, rendered DOM/SVG, screenshots, PNGs, and Markdown.
- Use official public download/export buttons when they are visible and do not require saving the file into an account.

## Not Allowed

- Logging into WPS/KDocs without explicit user instruction.
- Clicking "save to my cloud", "copy to my drive", or similar account-mutating actions unless explicitly requested.
- Bypassing CAPTCHAs, tenant restrictions, paywalls, password prompts, disabled download controls, or private-share limits.
- Reconstructing hidden or permission-denied content from guesses.
- Treating a login-wall JSON response as usable source data.

## Failure Reporting

If extraction fails, report the exact boundary:

- public link metadata unavailable
- ProcessOn API did not include `definition`
- browser rendered only a login shell
- original image could not be captured
- PNG renderer missing Quick Look or ImageMagick

Keep any partial raw artifacts that were legitimately fetched and mark the archive partial.
