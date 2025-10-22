# Developer Information

This file contains additional information for developers who want to use lobe-icons in their projects.

## npm Installation

Icons can be installed as npm packages:

```bash
# React components
npm install @lobehub/icons

# Static SVG files
npm install @lobehub/icons-static-svg

# Static PNG files
npm install @lobehub/icons-static-png

# Static WEBP files
npm install @lobehub/icons-static-webp

# React Native
npm install @lobehub/icons-rn
```

## Usage in React

```tsx
import { Claude, OpenAI, Gemini } from '@lobehub/icons';

function MyComponent() {
  return (
    <div>
      <Claude size={48} />
      <OpenAI size={48} />
      <Gemini size={48} />
    </div>
  );
}
```

## Additional Resources

- **Icon Gallery**: https://lobehub.com/icons
- **GitHub Repository**: https://github.com/lobehub/lobe-icons
- **Documentation**: https://icons.lobehub.com
- **NPM Packages**: https://www.npmjs.com/search?q=%40lobehub%2Ficons
