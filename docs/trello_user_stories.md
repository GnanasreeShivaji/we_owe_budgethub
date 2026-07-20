# WE_OWE — Updated Trello User Stories

Copy each section into one Trello card.

## US-16 | Confirm Recurring Bills [High]

**As a student,** I want recurring bills to act as monthly templates that I confirm after payment, **so that** reports contain real payments rather than assumed historical spending.

- Priority: Must Have
- Sprint: Sprint 5
- Story Points: 5

Checklist:

- Create monthly recurring-bill templates
- Mark a bill paid or unpaid for a selected month
- Store a dated monthly payment occurrence
- Count only confirmed occurrences in spending and reports
- Preserve templates for future months without inventing transactions
- Test month isolation and totals

## US-17 | Shopping List to Expense [Medium]

**As a group member,** I want to convert priced purchased shopping items into one group expense, **so that** I do not enter the same purchase twice.

- Priority: Should Have
- Sprint: Sprint 5
- Story Points: 5

Checklist:

- Add optional prices to shopping items
- Identify purchased items that are ready for conversion
- Create one expense from purchased priced items
- Split the new expense fairly among group members
- Mark converted items to prevent duplicate expenses
- Test conversion totals and group isolation

## US-18 | Receipt Review and Correction [High]

**As a student uploading a receipt,** I want to review and correct every extracted item, quantity, and unit price, **so that** OCR mistakes do not create incorrect expenses.

- Priority: Must Have
- Sprint: Sprint 5
- Story Points: 8

Checklist:

- Extract product name, quantity, unit price, and line total
- Repair OCR unit-price errors using the printed line total
- Allow editing names, quantities, and unit prices before saving
- Recalculate line totals and receipt total immediately
- Validate quantity and price ranges on the server
- Store reviewed quantity and unit-price data
- Test German decimal commas and multi-quantity lines

## US-19 | Automatic Reminder Worker [High]

**As a group member,** I want scheduled reminders to be processed automatically, **so that** they are delivered without opening the reminder page manually.

- Priority: Must Have
- Sprint: Sprint 5
- Story Points: 5

Checklist:

- Create a separate reminder worker process
- Check due reminders at a configurable interval
- Deliver due reminders through configured SMTP
- Cancel reminders when balances are already settled
- Track sent, failed, cancelled, and preference-disabled delivery
- Document local and production worker commands

## US-20 | Timezone and Currency Preferences [High]

**As an international student,** I want to choose my timezone and currency, **so that** reminders and amounts are displayed in a familiar local format.

- Priority: Must Have
- Sprint: Sprint 5
- Story Points: 8

Checklist:

- Support EUR, USD, INR, and GBP denominations
- Support Germany, India, US, and UTC timezones
- Interpret custom reminder times in the sender's timezone
- Store reminder times in UTC
- Display reminder times in the signed-in user's timezone
- Store the currency on every budget, expense, bill, reminder, and settlement
- Use the chosen currency as the default only for newly created records
- Keep existing records in their original currency when preferences change
- Separate report totals by currency so EUR, USD, INR, and GBP are never added together

## US-21 | Notification Preferences [Medium]

**As a user,** I want to control reminder emails, **so that** I receive only the notifications I want.

- Priority: Should Have
- Sprint: Sprint 5
- Story Points: 3

Checklist:

- Enable or disable immediate reminder emails
- Enable or disable scheduled reminder emails
- Respect recipient preferences before SMTP delivery
- Keep a delivery-history explanation when email is skipped
- Allow preferences to be changed at any time
- Test both enabled and disabled delivery paths

## US-22 | Account Export and Deletion [High]

**As a user,** I want to export or delete my account data, **so that** I retain control over my personal information.

- Priority: Must Have
- Sprint: Sprint 5
- Story Points: 8

Checklist:

- Export profile, budgets, expenses, groups, and settlements as JSON
- Require authentication for exports
- Require the current password before deletion
- Remove private financial data and owned groups
- Anonymize shared history needed for other members' balances
- Prevent deleted accounts from logging in
- Test access control and deletion outcomes

## US-23 | Production Security and Operations [High]

**As a project owner,** I want secure deployment and recovery controls, **so that** WE_OWE can run safely outside development.

- Priority: Must Have
- Sprint: Sprint 5
- Story Points: 8

Checklist:

- Add a production WSGI entrypoint
- Run web and reminder-worker processes separately
- Enable HTTPS-only session cookies in production
- Add security response headers
- Rate-limit repeated login failures
- Provide a consistent database-backup command
- Document PostgreSQL, SMTP, secret-key, HTTPS, and restore requirements
- Keep secrets and `.env` out of version control
