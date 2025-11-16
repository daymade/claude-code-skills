# Advanced Prompt Optimization Techniques

## Overview

This reference covers advanced EARS transformation patterns for complex requirements involving multiple stakeholders, non-functional constraints, and sophisticated conditional logic.

## Multi-Stakeholder Requirements

When requirements involve multiple user types with different needs and permissions:

### Approach

1. Create EARS statements for each stakeholder
2. Identify conflicting requirements (admin vs. user permissions)
3. Specify role-based conditions explicitly
4. Use nested conditions when access depends on multiple factors

### Patterns

**Basic role-based access:**
```
If user role is 'Admin', the system shall display all user management controls
If user role is 'Editor', the system shall display content editing controls
If user role is 'Viewer', the system shall prevent access to editing functions
```

**Hierarchical permissions:**
```
If user role is 'Owner' OR 'Admin', the system shall allow deletion of any content
If user role is 'Editor' AND content.author is current user, the system shall allow editing of that content
If user role is 'Viewer', the system shall display content in read-only mode
```

**Context-dependent access:**
```
When user requests sensitive data:
  - If user role is 'Manager' AND user.department matches data.department, the system shall grant access
  - If user role is 'Executive', the system shall grant access regardless of department
  - Otherwise, the system shall deny access and log the attempt
```

### Example: Content Management System

**Requirement:** "Different users should have different permissions"

**EARS transformation:**
```
1. When user logs in with 'Admin' role, the system shall display dashboard with user management, content moderation, and system settings

2. When user logs in with 'Author' role, the system shall display dashboard with create post, edit own posts, and view analytics

3. When 'Author' attempts to publish post, the system shall set post status to 'pending review'

4. When 'Editor' reviews pending post, the system shall provide approve/reject/request changes options

5. If 'Author' attempts to access another author's draft, the system shall prevent access and display "Access Denied" message

6. When 'Admin' accesses any post, the system shall grant full permissions (view, edit, delete, publish) regardless of author
```

## Non-Functional Requirements

Performance, security, scalability, and reliability requirements need precise quantification.

### Approach

1. Quantify constraints explicitly (no vague terms like "fast" or "secure")
2. Specify measurement methods (how to verify the requirement)
3. Include threshold values (acceptable ranges)
4. Define degradation behavior (what happens when thresholds are exceeded)

### Patterns

**Performance requirements:**
```
When search query is submitted, the system shall return results within 200ms for 95% of requests
When page load is initiated, the system shall display first contentful paint within 1.5 seconds for 90% of requests
While concurrent user count exceeds 10,000, the system shall maintain response time below 500ms
```

**Security requirements:**
```
When user authentication fails 5 times within 15 minutes, the system shall lock the account for 30 minutes
When password is created, the system shall enforce minimum 12 characters, 1 uppercase, 1 number, 1 special character
While session is active, the system shall invalidate session after 30 minutes of inactivity
If SQL injection pattern is detected in input, the system shall sanitize input and log security event
```

**Scalability requirements:**
```
When concurrent user count reaches 50,000, the system shall auto-scale to additional server instances
When database query time exceeds 100ms, the system shall use read replicas for load balancing
While system is under load, the system shall queue requests beyond 100,000/second and process FIFO
```

**Reliability requirements:**
```
When service fails, the system shall attempt retry with exponential backoff (1s, 2s, 4s, 8s)
When database connection is lost, the system shall failover to backup database within 5 seconds
While maintenance window is active, the system shall display maintenance page and queue incoming requests
If data corruption is detected, the system shall rollback to last known good state within 10 minutes
```

### Example: E-commerce Checkout

**Requirement:** "The checkout should be fast and secure"

**EARS transformation:**
```
1. When user clicks "Place Order", the system shall process payment within 3 seconds for 95% of transactions

2. When payment processing exceeds 5 seconds, the system shall display "Processing..." indicator and prevent duplicate submissions

3. When payment is processed, the system shall use TLS 1.3 encryption for all data transmission

4. When credit card number is entered, the system shall tokenize the number and never store raw card data

5. When payment gateway is unavailable, the system shall retry 3 times with 2-second intervals, then display user-friendly error

6. If payment fails after retries, the system shall store order in "pending" state for 24 hours and email user with recovery link

7. When concurrent checkout requests exceed 1,000/second, the system shall queue additional requests and process within 10 seconds

8. When fraud detection score exceeds 70, the system shall require additional verification (SMS code or manual review)
```

## Complex Conditional Logic

Multi-condition requirements with nested logic, boolean operators, and priority rules.

### Approach

1. Use nested conditions with clear hierarchy
2. Specify boolean operators explicitly (AND, OR, NOT)
3. Define priority when conditions conflict
4. Use parentheses to clarify precedence
5. Provide fallback behavior for unmatched conditions

### Patterns

**Nested conditions:**
```
When user submits form:
  If all required fields are filled:
    If email format is valid:
      If password strength is 'strong' OR 'very strong':
        The system shall create account and send verification email
      Else:
        The system shall reject with "Password too weak" message
    Else:
      The system shall highlight email field and display format example
  Else:
    The system shall highlight missing fields and prevent submission
```

**Complex boolean logic:**
```
If (user is logged in AND subscription is active) OR (user has free trial remaining AND trial end date > today):
  The system shall grant access to premium features
  If free trial:
    The system shall display "X days remaining in trial" banner
  If subscription expires within 7 days:
    The system shall show renewal reminder in header
Else:
  The system shall redirect to pricing page with upgrade prompt
```

**Priority-based rules:**
```
When content moderation is triggered:
  Priority 1: If content contains profanity, the system shall immediately hide content and flag for manual review
  Priority 2: Else if content reports exceed 10, the system shall hide content and notify moderator
  Priority 3: Else if AI toxicity score > 0.8, the system shall add warning label "potentially sensitive content"
  Priority 4: Else if content is flagged but reports < 10, the system shall add to moderation queue
  Default: The system shall display content normally
```

**Time-based conditions:**
```
When user accesses course content:
  If (current date >= course.start_date) AND (current date <= course.end_date):
    If user.enrollment_status is 'active':
      The system shall grant full access to all lessons
    Else if user.enrollment_status is 'pending':
      The system shall display "Enrollment pending approval" message
  Else if current date < course.start_date:
    The system shall display "Course starts on [date]" countdown
  Else if (current date > course.end_date) AND (user.completion_rate >= 100%):
    The system shall grant read-only access to completed course materials
  Else:
    The system shall display "Course has ended" message with re-enrollment option
```

### Example: Dynamic Pricing System

**Requirement:** "Prices should change based on demand, inventory, and user type"

**EARS transformation:**
```
When user views product page:
  Base calculation: system shall retrieve base_price from product.price

  Apply inventory adjustments:
    If inventory_count < 10:
      system shall multiply price by 1.2 (20% scarcity premium)
    Else if inventory_count < 50:
      system shall multiply price by 1.1 (10% low stock premium)
    Else if inventory_count > 500:
      system shall multiply price by 0.9 (10% overstock discount)

  Apply demand adjustments:
    If view_count in last 24 hours > 1000:
      system shall multiply price by 1.15 (15% high demand premium)
    If purchase_count in last hour > 50:
      system shall multiply price by 1.1 (10% trending premium)

  Apply user-specific adjustments:
    If user is 'VIP' AND lifetime_purchase_value > $10,000:
      system shall apply 15% discount
    Else if user is 'VIP':
      system shall apply 10% discount
    Else if user is logged in AND first_purchase:
      system shall apply 5% first-time discount
    Else if user has abandoned cart for this product:
      system shall apply 8% re-engagement discount

  Apply time-based promotions:
    If current time is within flash_sale.time_window:
      system shall apply flash_sale.discount_percentage
    Else if current date is user.birthday:
      system shall apply 20% birthday discount

  Final validation:
    If calculated_price < product.minimum_price:
      system shall set price to product.minimum_price
    If calculated_price > product.maximum_price:
      system shall set price to product.maximum_price

  Display:
    system shall display final calculated price rounded to nearest $0.99
    If discount > 0:
      system shall show original price crossed out with discount percentage badge
```

## Combining Techniques

Real-world requirements often combine multiple techniques:

### Example: Healthcare Appointment System

**Requirement:** "Different user types should be able to book appointments with various rules"

**Combined EARS transformation:**
```
Multi-stakeholder + Non-functional + Complex conditional:

When user attempts to book appointment:

  Authentication & Authorization:
    If user role is 'Patient':
      If user has verified insurance AND insurance.status is 'active':
        system shall allow booking appointments with in-network providers
      Else if user has no insurance OR insurance.status is 'expired':
        system shall allow booking with cash payment option only
      Else if user.insurance_verification is 'pending':
        system shall display "Insurance verification in progress" message

    If user role is 'Provider':
      system shall display manage schedule, view appointments, update availability options

    If user role is 'Admin':
      system shall grant full access to all appointments, schedules, and patient records

  Availability checking (Performance requirement):
    When user selects provider and date:
      system shall retrieve available time slots within 100ms
      If query exceeds 100ms:
        system shall use cached availability data with staleness indicator

  Booking constraints (Complex conditional):
    If selected_time is within 24 hours AND user role is 'Patient':
      system shall require phone verification for last-minute bookings
    Else if selected_time is more than 90 days in future:
      system shall prevent booking and display "Cannot book more than 90 days ahead"

    If (appointment_count for user this_month >= 5) AND (user.subscription_tier is 'Basic'):
      system shall prevent booking and prompt upgrade to 'Premium' tier
    Else if (appointment_count for provider this_day >= 20):
      system shall prevent booking and suggest alternative providers or dates

  Concurrent booking prevention (Non-functional - reliability):
    When booking is confirmed:
      system shall use distributed lock to prevent double-booking for 60 seconds
      If lock cannot be acquired within 5 seconds:
        system shall display "This time slot is being booked by another user" and refresh available slots

  Notification rules (Multi-stakeholder):
    When appointment is successfully booked:
      system shall send confirmation email to patient within 30 seconds
      system shall send notification to provider via SMS and in-app notification
      system shall add appointment to provider's calendar with patient details
      If appointment is within 48 hours:
        system shall schedule reminder SMS 24 hours before appointment
        system shall schedule reminder email 2 hours before appointment
```

## Best Practices for Advanced Techniques

1. **Layer incrementally** - Start with basic EARS, then add advanced patterns
2. **Test each condition** - Ensure every branch has a testable outcome
3. **Document assumptions** - Make implicit business rules explicit
4. **Use tables for complex logic** - Decision tables clarify multi-condition scenarios
5. **Validate with stakeholders** - Confirm priority and precedence with domain experts
6. **Consider edge cases** - What happens at boundaries (0, max, negative, null)?
7. **Plan for exceptions** - Every rule needs an "otherwise" clause
8. **Quantify everything** - Replace "many" with numbers, "fast" with milliseconds

## Common Pitfalls

❌ **Circular conditions** - "If A then B, if B then A" creates infinite loops
❌ **Unreachable branches** - Conditions that can never be true
❌ **Ambiguous precedence** - When multiple conditions match, which wins?
❌ **Missing default cases** - What if none of the conditions match?
❌ **Vague thresholds** - "High traffic" → Define "high" numerically
❌ **Incomplete error handling** - What happens when external systems fail?
