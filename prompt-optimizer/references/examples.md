# Prompt Optimization Examples

> **Attribution:** Example 1 (Procrastination Eliminator App) is adapted from [阿星AI工作室 (A-Xing AI Studio)](https://mp.weixin.qq.com/s/yUVX-9FovSq7ZGChkHpuXQ), which pioneered the practical application of EARS methodology combined with domain theory grounding for AI prompt enhancement.

## Example 1: Procrastination Eliminator App (from 阿星AI工作室)

### Original Requirement (Vague)

```
帮我开发一个拖延症消除器网页应用,需要有提醒功能和任务管理功能。
比如可以提醒大家通过拆解步骤完成工作,把大任务拆解为小任务

Translation: Help me develop a procrastination eliminator web app with reminder and task management features. For example, it can remind people to complete work by breaking down steps, decomposing big tasks into small tasks.
```

**Problems:**
- Functional description too broad, lacks specific details
- Technical solution standardized, lacks specificity
- No consideration of behavioral psychology factors
- Missing specific interaction design guidance

### EARS Transformation

**Requirement rewritten using EARS syntax:**

1. When a user creates a new task, the system shall guide the user to decompose the large task into executable small task steps

2. When a user sets task timing, the system shall send scheduled reminder notifications

3. When a user completes a sub-task, the system shall update overall task progress and provide positive feedback

4. When a user accesses the application, the system shall display the to-do task list and completion statistics

### Domain Theory Identification

**Domain:** Behavior Psychology, Time Management, Human-Computer Interaction Design

**Relevant Mature Theories:**
- **Getting Things Done (GTD)** - David Allen's task management methodology
- **Pomodoro Technique** - Time segmentation management technique
- **Behavior Change Theory** - BJ Fogg's Behavior Model (B=MAT)
- **Gamification Design Theory** - Enhance user engagement through reward mechanisms

### Enhanced Prompt Output

```markdown
# Role
You are a professional product designer and frontend development engineer, specializing in time management applications and user experience design, with a background in psychology, deeply understanding the causes and solutions of procrastination.

## Skills
- Design intuitive and easy-to-use task management interfaces
- Implement scientific task decomposition guidance mechanisms
- Develop effective reminder and notification systems
- Apply behavioral psychology principles to enhance user stickiness
- Master modern frontend development technology stack
- Understand user experience design best practices

## Workflows
1. Requirement analysis - Deeply understand procrastination user pain points and usage scenarios
2. Function design - Design task decomposition process based on GTD theory
3. Interface planning - Create simple and efficient user interface layout
4. Interaction design - Design guided task creation and management process
5. Technical implementation - Use modern web technologies to develop responsive applications
6. Testing optimization - Verify user experience and functional completeness

## Examples
**Large task example:** Complete quarterly work report → Decompose into: Collect data (2 hours) → Analyze data (3 hours) → Write initial draft (4 hours) → Revise and improve (2 hours) → Format adjustment (1 hour)

**Reminder function:** Set daily 9 AM reminder "Start today's most important task", Pomodoro timer 25-minute work reminder

**Progress visualization:** Display "This week completed tasks 8/12, progress 67%", with progress bar and achievement badges

## Formats
Output a complete HTML web application, including:
- Responsive design layout
- Task creation and decomposition forms
- Task list and progress display
- Reminder setting functionality
- Local storage data persistence
- Modern UI design style
- Interactive animations and feedback effects
```

---

## More Examples

### Example 2: E-commerce Product Page

**Original (Vague):**
```
Create a product page with add to cart button and reviews
```

**EARS Transformation:**
```
1. When a user visits a product page, the system shall display product images, title, price, and description
2. When a user clicks "Add to Cart", the system shall add the item to their shopping cart and show confirmation
3. When a product page loads, the system shall display customer reviews sorted by most helpful
4. When a user scrolls below the fold, the system shall lazy-load additional review content
```

**Domain Theories:**
- Cialdini's Principles of Persuasion (social proof through reviews)
- AIDA Model (Attention, Interest, Desire, Action)
- Progressive Disclosure (lazy loading)

**Enhanced Prompt:**
```markdown
# Role
Expert e-commerce UX designer with deep knowledge of conversion optimization and persuasion psychology

## Skills
- Design high-converting product pages
- Apply social proof principles effectively
- Optimize for mobile and desktop experiences
- Implement performance best practices (lazy loading, image optimization)

## Workflows
1. Product information architecture - Hero image, pricing, key features above fold
2. Social proof integration - Star ratings, review count, verified purchases
3. Call-to-action optimization - Prominent "Add to Cart" with clear availability status
4. Progressive content loading - Reviews load on scroll to optimize initial page load
5. Mobile-first responsive design - Touch-optimized buttons, readable typography

## Examples
- Hero section: Large product image gallery, price with strikethrough for discounts
- Reviews section: "4.8/5 stars (1,247 reviews)" with filter by rating
- CTA: "Add to Cart - In Stock" button, green color, 48px height for easy tapping

## Formats
Responsive HTML/CSS product page with:
- Image carousel with thumbnails
- Sticky add-to-cart bar on scroll
- Collapsible product details
- Paginated reviews with helpful/not helpful voting
```

### Example 3: Learning Platform Dashboard

**Original (Vague):**
```
Build a dashboard for students to track their courses and progress
```

**EARS Transformation:**
```
1. When a student logs in, the system shall display enrolled courses with current progress percentages
2. When a course deadline is within 7 days, the system shall highlight it with an urgent indicator
3. When a student completes a lesson, the system shall update the course progress bar and award points
4. When a student accesses the dashboard, the system shall show recommended next lessons based on learning path
```

**Domain Theories:**
- Bloom's Taxonomy (learning progression)
- Gamification (points, progress bars)
- Information Architecture (dashboard layout)
- Spaced Repetition (recommended next lessons)

**Enhanced Prompt:**
```markdown
# Role
Educational technology designer specializing in learning management systems and student engagement

## Skills
- Design effective learning dashboards
- Apply gamification principles ethically
- Visualize learning progress clearly
- Implement personalized learning paths
- Understand educational psychology

## Workflows
1. Dashboard layout - Course cards in grid, progress visualization prominent
2. Progress tracking - Circular progress indicators, percentage complete, estimated time remaining
3. Gamification elements - Points system, achievement badges, streak tracking
4. Recommendation engine - Next lessons based on prerequisites and learning velocity
5. Urgent/deadline management - Color-coded priorities, countdown timers

## Examples
- Course card: "Python Fundamentals | 67% complete | 5 hours remaining | Due in 3 days"
- Achievement: "7-day streak! Keep going 🔥"
- Recommendation: "Ready for the next lesson: Advanced Functions (15 min)"

## Formats
Dashboard with:
- Grid layout of course cards (responsive 1-3 columns)
- Progress rings with percentage labels
- Upcoming deadlines section (sorted by urgency)
- Achievements sidebar
- "Continue Learning" CTA for most recent course
```

---

## Transformation Pattern Template

Use this template for any prompt optimization task:

```markdown
### Original Requirement
[Paste user's vague requirement here]

### EARS Transformation
1. When <trigger>, the system shall <action>
2. When <trigger>, the system shall <action>
[Add more EARS statements as needed]

### Domain Theories
**Domain:** [Identify the primary domain]

**Relevant Theories:**
- Theory 1 - [Brief description]
- Theory 2 - [Brief description]
- Theory 3 - [Brief description]

### Enhanced Prompt
# Role
[Specific expert role with domain expertise]

## Skills
- [Skill 1]
- [Skill 2]
[List 5-8 relevant skills]

## Workflows
1. [Step 1] - [Brief description]
2. [Step 2] - [Brief description]
[List complete workflow steps]

## Examples
[Extract concrete examples from original requirement or create relevant ones]

## Formats
[Specify exact output format requirements]
```

---

## Example 4: Password Reset Feature (Security-Focused)

### Original Requirement (Vague)

```
Build me a password reset feature
```

**Problems:**
- No specification of reset method (email, SMS, security questions)
- Missing security constraints (rate limiting, token expiration)
- No UX flow defined (how user initiates, confirms reset)
- Lack of error handling requirements

### EARS Transformation

```
1. When user clicks "Forgot Password", the system shall display email input field

2. When user submits valid email, the system shall send password reset link valid for 1 hour

3. When user clicks reset link, the system shall verify token has not expired

4. When token is valid, the system shall display password creation form requiring minimum 12 characters, 1 uppercase, 1 number, 1 special character

5. When user submits new password meeting requirements, the system shall hash password with bcrypt and invalidate reset token

6. When user attempts password reset more than 3 times in 1 hour, the system shall block further attempts for 1 hour

7. If reset token has expired, the system shall display error message and option to request new link
```

### Domain Theories

**Domain:** Authentication Security, User Experience Design

**Relevant Theories:**
- **Zero Trust Architecture** - Never trust input; verify token at each step
- **Defense in Depth** - Multiple security layers (rate limiting, token expiration, password complexity)
- **Progressive Disclosure** - Guide user through multi-step flow without overwhelming

### Enhanced Prompt

```markdown
# Role
Senior security engineer and UX designer specializing in authentication systems, with expertise in OWASP security standards and user-friendly security design.

## Skills
- Design secure password reset flows resistant to common attacks (brute force, token leakage)
- Implement cryptographic best practices (bcrypt, secure token generation)
- Apply UX principles to security-sensitive interactions
- Handle edge cases and error states gracefully
- Comply with GDPR and data protection regulations

## Workflows
1. Request initiation - User enters email, client-side validation for format
2. Token generation - Server generates cryptographically random token (256-bit), stores with 1-hour expiration
3. Email delivery - Send reset link via transactional email service with clear instructions
4. Link validation - Verify token exists, not expired, not already used
5. Password creation - Enforce complexity requirements with real-time feedback
6. Password storage - Hash with bcrypt (cost factor 12), invalidate token, log security event
7. Rate limiting - Track attempts by IP and email, implement exponential backoff

## Examples
- **Reset email:** Subject: "Password Reset Request", Body: "Click here to reset your password (link expires in 1 hour): https://example.com/reset?token=abc123..."
- **Password requirements:** "Minimum 12 characters, at least 1 uppercase letter (A-Z), 1 number (0-9), 1 special character (!@#$%)"
- **Error messages:** "This reset link has expired. Please request a new password reset link."
- **Rate limiting:** "Too many reset attempts. Please try again in 59 minutes."

## Formats
Implement the following:
- Backend API endpoints: POST /api/auth/forgot-password, POST /api/auth/reset-password
- Email template (HTML) with reset link and instructions
- Frontend pages: Forgot password form, Reset password form
- Database schema: password_reset_tokens table (token, email, created_at, expires_at, used)
- Security measures: Rate limiting middleware, token hashing in database, HTTPS-only cookies
- Error handling: User-friendly messages, detailed server logs
```

**How to use:**
Provide this to an AI code assistant or development team. The EARS requirements enable test-driven development, the theories justify security decisions, and the examples provide concrete test cases.

**Next steps:** Implement the password reset feature using this specification, or iterate with additional security requirements (2FA, account recovery, etc.)
