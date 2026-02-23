# Apple Code Signing + Notarization Guide

For macOS desktop apps (Electron or native) distributed outside the App Store. Without signing + notarization, users see "Apple cannot check this app for malicious software."

---

## Prerequisites

- Apple Developer Program ($99/year)
- Record **Team ID** (developer.apple.com → Account → Membership Details)

---

## Step 1: Create Developer ID Application Certificate

> **Developer ID Application** = distribution outside App Store (DMG/ZIP).
> **Mac App Distribution** = App Store only.

### 1a. Generate CSR

Keychain Access → Certificate Assistant → **Request a Certificate from a Certificate Authority**:

| Field | Value |
|-------|-------|
| User Email Address | Apple Developer email |
| Common Name | Anything (Apple overrides this) |
| CA Email Address | Leave empty |
| Request is | **Saved to disk** |

### 1b. Request Certificate

1. Go to [developer.apple.com/account/resources/certificates/add](https://developer.apple.com/account/resources/certificates/add)
2. Select **Developer ID Application**
3. Choose **G2 Sub-CA (Xcode 11.4.1 or later)** (not Previous Sub-CA)
4. Upload CSR, download `.cer`

### 1c. Install to Keychain

Double-click `.cer` → **must choose `login` keychain**. Choosing iCloud/System causes Error -25294 (private key not in same keychain).

### 1d. Verify

```bash
security find-identity -v -p codesigning | grep "Developer ID Application"
```

---

## Step 2: Export P12 (for CI)

1. Keychain Access → My Certificates → find `Developer ID Application: ...`
2. Right-click → Export → `.p12` format → set strong password
3. Convert to base64:

```bash
base64 -i ~/Desktop/codesign.p12 | pbcopy
```

---

## Step 3: Create App Store Connect API Key (for notarization)

> API Key avoids 2FA prompts in CI. Apple's recommended approach for automation.

1. Go to [appstoreconnect.apple.com/access/integrations/api](https://appstoreconnect.apple.com/access/integrations/api)
2. Generate API Key (Access: **Developer**)
3. Download `.p8` (one-time only)
4. Record **Key ID** (10 chars) and **Issuer ID** (UUID)

```bash
base64 -i ~/Downloads/AuthKey_KEYID.p8 | pbcopy
```

---

## Step 4: Configure GitHub Secrets

**5 secrets required** (secret names must exactly match workflow references):

| Secret | Source |
|--------|--------|
| `MACOS_CERT_P12` | Step 2 base64 |
| `MACOS_CERT_PASSWORD` | Step 2 password |
| `APPLE_API_KEY` | Step 3 `.p8` base64 |
| `APPLE_API_KEY_ID` | Step 3 Key ID |
| `APPLE_API_ISSUER` | Step 3 Issuer ID |

> **`APPLE_TEAM_ID` is NOT needed and MUST NOT be passed.** `@electron/notarize` v2.5.0's `isNotaryToolPasswordCredentials()` checks `teamId !== undefined`. Passing `teamId` alongside API key credentials triggers: "Cannot use password credentials, API key credentials and keychain credentials at once." `notarytool` infers team from the API key automatically.

### Setting secrets via gh CLI

```bash
# Short values
gh secret set MACOS_CERT_PASSWORD --body 'your-password' --repo owner/repo
gh secret set APPLE_API_KEY_ID --body 'KEYIDHERE' --repo owner/repo
gh secret set APPLE_API_ISSUER --body 'uuid-here' --repo owner/repo

# Long base64 values — use temp file to avoid zsh glob expansion errors
printf '%s' '<base64>' > /tmp/p12.txt
gh secret set MACOS_CERT_P12 < /tmp/p12.txt --repo owner/repo && rm /tmp/p12.txt

printf '%s' '<base64>' > /tmp/apikey.txt
gh secret set APPLE_API_KEY < /tmp/apikey.txt --repo owner/repo && rm /tmp/apikey.txt
```

> **Dual-repo architecture**: If using private dev repo + public release repo, set secrets on both repos separately.

### Verify

```bash
gh secret list --repo owner/repo
```

---

## Step 5: Electron Forge Configuration

### osxSign (signing)

```typescript
const SHOULD_CODESIGN = process.env.FLOWZERO_CODESIGN === '1';
const SHOULD_NOTARIZE = process.env.FLOWZERO_NOTARIZE === '1';
const CODESIGN_IDENTITY = process.env.CODESIGN_IDENTITY || 'Developer ID Application';

// In packagerConfig:
...(SHOULD_CODESIGN ? {
  osxSign: {
    identity: CODESIGN_IDENTITY,
    hardenedRuntime: true,
    entitlements: 'entitlements.mac.plist',
    entitlementsInherit: 'entitlements.mac.plist',
    // CRITICAL: @electron/packager defaults continueOnError to true,
    // which silently swallows ALL signing failures and falls back to adhoc.
    continueOnError: false,
    // Skip non-binary files in large embedded runtimes (e.g. Python).
    // Without this, osx-sign traverses 50k+ files → EMFILE errors.
    // Native .so/.dylib/.node binaries are still signed.
    ignore: (filePath: string) => {
      if (!filePath.includes('python-runtime')) return false;
      if (/\.(so|dylib|node)$/.test(filePath)) return false;
      return true;
    },
    // CI: apple-actions/import-codesign-certs@v3 imports to signing_temp.keychain,
    // but @electron/osx-sign searches system keychain by default.
    ...(process.env.MACOS_SIGNING_KEYCHAIN
      ? { keychain: process.env.MACOS_SIGNING_KEYCHAIN }
      : {}),
  },
} : {}),
```

### osxNotarize (notarization)

```typescript
...(SHOULD_NOTARIZE ? {
  osxNotarize: {
    tool: 'notarytool',
    appleApiKey: process.env.APPLE_API_KEY_PATH,
    appleApiKeyId: process.env.APPLE_API_KEY_ID,
    appleApiIssuer: process.env.APPLE_API_ISSUER,
    // NOTE: Do NOT pass teamId. See Step 4 explanation above.
  },
} : {}),
```

### postPackage Fail-Fast Verification

Add `codesign --verify --deep --strict` + adhoc detection in the `postPackage` hook:

```typescript
import { execSync } from 'child_process';

// In postPackage hook:
if (SHOULD_CODESIGN && process.platform === 'darwin') {
  const appDir = fs.readdirSync(buildPath).find(e => e.endsWith('.app'));
  if (!appDir) throw new Error('CODESIGN FAIL-FAST: No .app bundle found');
  const appPath = path.join(buildPath, appDir);

  // 1. Verify signature is valid
  try {
    execSync(`codesign --verify --deep --strict "${appPath}"`, { stdio: 'pipe' });
  } catch (e) {
    const stderr = (e as { stderr?: Buffer })?.stderr?.toString() || '';
    throw new Error(`CODESIGN FAIL-FAST: Verification failed.\n  ${stderr}`);
  }

  // 2. Check it's NOT adhoc
  const info = execSync(`codesign -dvv "${appPath}" 2>&1`, { encoding: 'utf-8' });
  if (info.includes('Signature=adhoc')) {
    throw new Error('CODESIGN FAIL-FAST: App has adhoc signature! Signing silently failed.');
  }

  const authority = info.match(/Authority=(.+)/);
  if (authority) console.log(`Signed by: ${authority[1]}`);
}
```

### entitlements.mac.plist (Electron + Python)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>com.apple.security.app-sandbox</key>
  <false/>
  <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
  <true/>
  <key>com.apple.security.cs.disable-library-validation</key>
  <true/>
  <key>com.apple.security.cs.allow-jit</key>
  <true/>
  <key>com.apple.security.device.microphone</key>
  <true/>
  <key>com.apple.security.network.client</key>
  <true/>
</dict>
</plist>
```

---

## Step 6: GitHub Actions Workflow

### Key pattern: secrets in step `if:` conditions

`secrets.*` context **cannot** be used directly in step `if:`. Use `env:` intermediate variables:

```yaml
# WRONG — causes HTTP 422: "Unrecognized named-value: 'secrets'"
- name: Import certs
  if: ${{ secrets.MACOS_CERT_P12 != '' }}

# CORRECT — use env: intermediate variable
- name: Import certs
  if: ${{ env.HAS_CERT == 'true' }}
  env:
    HAS_CERT: ${{ secrets.MACOS_CERT_P12 != '' }}
```

### Complete workflow example

```yaml
- name: Import Apple certificates
  if: ${{ env.HAS_CERT == 'true' }}
  uses: apple-actions/import-codesign-certs@v3
  with:
    p12-file-base64: ${{ secrets.MACOS_CERT_P12 }}
    p12-password: ${{ secrets.MACOS_CERT_PASSWORD }}
  env:
    HAS_CERT: ${{ secrets.MACOS_CERT_P12 != '' }}

- name: Verify signing identity
  if: ${{ env.HAS_CERT == 'true' }}
  run: security find-identity -v -p codesigning | grep "Developer ID"
  env:
    HAS_CERT: ${{ secrets.MACOS_CERT_P12 != '' }}

- name: Prepare API key
  if: ${{ env.HAS_API_KEY == 'true' }}
  run: |
    set -euo pipefail
    if [[ "$APPLE_API_KEY" == *"BEGIN PRIVATE KEY"* ]]; then
      printf "%s" "$APPLE_API_KEY" > /tmp/AuthKey.p8
    else
      echo "$APPLE_API_KEY" | base64 --decode > /tmp/AuthKey.p8
    fi
  env:
    HAS_API_KEY: ${{ secrets.APPLE_API_KEY != '' }}
    APPLE_API_KEY: ${{ secrets.APPLE_API_KEY }}

- name: Build & sign
  env:
    FLOWZERO_CODESIGN: ${{ secrets.MACOS_CERT_P12 != '' && '1' || '' }}
    FLOWZERO_NOTARIZE: ${{ secrets.APPLE_API_KEY != '' && '1' || '' }}
    APPLE_API_KEY_PATH: /tmp/AuthKey.p8
    APPLE_API_KEY_ID: ${{ secrets.APPLE_API_KEY_ID }}
    APPLE_API_ISSUER: ${{ secrets.APPLE_API_ISSUER }}
    # NOTE: APPLE_TEAM_ID intentionally omitted — notarytool infers from API key
  run: |
    ulimit -n 65536  # Prevent EMFILE when signing large app bundles
    pnpm run forge:make -- --arch=arm64
```

---

## Fail-Fast Three-Layer Defense

Signing can fail silently in many ways. This architecture ensures any failure is caught immediately:

| Layer | Mechanism | What it catches |
|-------|-----------|-----------------|
| 1. `@electron/osx-sign` | `continueOnError: false` | Signing errors (EMFILE, cert not found, timestamp failures) |
| 2. `postPackage` hook | `codesign --verify --deep --strict` + adhoc detection | Silent signing failures, unexpected adhoc fallback |
| 3. Release trigger | Verify local HEAD matches remote branch | Stale code reaching CI (SHA vs branch name issue) |

### Release trigger script pattern

```bash
# Send branch name, NOT commit SHA
BRANCH=$(git rev-parse --abbrev-ref HEAD)
LOCAL_HEAD=$(git rev-parse HEAD)
REMOTE_HEAD=$(git ls-remote origin "$BRANCH" 2>/dev/null | awk '{print $1}')

if [[ "$LOCAL_HEAD" != "$REMOTE_HEAD" ]]; then
  echo "FAIL-FAST: Local HEAD does not match remote!"
  echo "  Local:  $LOCAL_HEAD"
  echo "  Remote: $REMOTE_HEAD"
  echo "  Push first: git push origin $BRANCH"
  exit 1
fi

# Dispatch with branch name (not SHA)
gh api repos/OWNER/REPO/dispatches -f event_type=release -f 'client_payload[ref]='"$BRANCH"
```

> **Why branch name, not SHA**: `actions/checkout` uses `refs/heads/<ref>*` glob matching for shallow clones. Commit SHAs don't match this pattern and cause checkout failure.

---

## Troubleshooting

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| App signed as adhoc despite certificate configured | `@electron/packager` defaults `continueOnError: true` in `createSignOpts()` (mac.js line 402-404). Signing error was silently swallowed. | Set `continueOnError: false` in osxSign config |
| "Cannot use password credentials, API key credentials and keychain credentials at once" | `@electron/notarize` v2.5.0 `isNotaryToolPasswordCredentials()` checks `teamId !== undefined`. Passing `teamId` with API key = credential conflict. | Remove `teamId` from osxNotarize config. `notarytool` infers team from API key. |
| EMFILE: too many open files | `@electron/osx-sign` `walkAsync()` traverses ALL files in .app. Large embedded runtimes (Python: 51k+ files) exhaust file descriptors. | Add `ignore` filter to skip non-binary files + `ulimit -n 65536` in CI |
| CI signing: cert not found | `apple-actions/import-codesign-certs@v3` imports to `signing_temp.keychain`, but osx-sign searches system keychain. | Pass `keychain: process.env.MACOS_SIGNING_KEYCHAIN` in osxSign |
| Install .cer: Error -25294 | Certificate imported to wrong keychain (iCloud/System). Private key from CSR is in `login` keychain. | Re-import `.cer` choosing `login` keychain |
| `security find-identity` shows nothing | Private key and certificate in different keychains | Ensure CSR private key and imported cert are both in `login` keychain |
| CI step `if:` with secrets → HTTP 422 | `secrets.*` context not available in step `if:` conditions | Use `env:` intermediate variable pattern (see workflow section) |
| CI checkout fails: "git failed with exit code 1" | `actions/checkout` shallow clone can't resolve commit SHA as ref | Send branch name (not SHA) in `repository_dispatch`. Verify local HEAD matches remote before dispatch. |
| CI signing steps silently skipped | Secret names don't match workflow `secrets.XXX` references | `gh secret list` and compare against all `secrets.` references in workflow YAML |
| "The timestamp service is not available" | Apple's timestamp server intermittently unavailable during codesign | Retry the build. `ignore` filter reduces files needing timestamps, lowering failure probability. |
| Notarization: "Could not find valid private key" | `.p8` file base64 decoded incorrectly | Verify: `echo "$APPLE_API_KEY" \| base64 --decode \| head -1` should show `-----BEGIN PRIVATE KEY-----` |
| zsh `permission denied` piping long base64 | Shell interprets base64 special chars as glob | Use temp file + `<` redirect: `gh secret set NAME < /tmp/file.txt` |

---

## Local Verification (without notarization)

```bash
# Sign only (fast verification that certificate works)
FLOWZERO_CODESIGN=1 pnpm run forge:make

# Verify signature
codesign --verify --deep --strict path/to/App.app

# Check signing authority
codesign -dvv path/to/App.app 2>&1 | grep Authority

# Gatekeeper assessment
spctl --assess --type exec path/to/App.app
```
