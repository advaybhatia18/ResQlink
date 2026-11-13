# RESQLINK — COMPLETE SYSTEM IMPLEMENTATION, UI/UX, TESTING & DEPLOYMENT MASTER PROMPT

You are acting as a senior full-stack engineer, backend architect, UI/UX designer, database engineer, security engineer, QA automation engineer and DevOps engineer.

Your task is to take the existing ResQlink repository and transform it into a complete, functional, thoroughly tested emergency-assistance platform and emergency-response simulation system.

Repository:
https://github.com/advaybhatia18/ResQlink

The current main branch is the source of truth.

IMPORTANT: Do not merely provide recommendations, code snippets, mockups or a roadmap. Inspect the repository, implement the changes, run tests, fix errors and deliver working code.

Your objective is to make every implemented component functional and integrated with the rest of the application.

==================================================
1. NON-NEGOTIABLE DEVELOPMENT RULES
==================================================

1. Inspect the complete repository before making changes.
2. Understand the existing architecture and preserve working functionality.
3. Do not blindly rewrite existing files.
4. Do not remove the existing C emergency priority engine.
5. Preserve the existing Python/FastAPI backend.
6. Preserve Supabase Auth and PostgreSQL.
7. Preserve the existing GitHub Pages and Render deployment architecture.
8. Preserve Leaflet where appropriate.
9. Do not introduce unnecessary frameworks or dependencies.
10. Do not duplicate functionality already implemented.
11. Use modular, reusable code.
12. Implement actual backend/database integration rather than frontend-only demonstrations.
13. Never hardcode secrets, credentials, administrator tokens or API keys.
14. Do not claim an operation succeeded until the backend confirms it.
15. Every page must have loading, success, empty and error states where appropriate.
16. All important actions must be tested.
17. Do not leave placeholder buttons, non-functional links or fake functionality.
18. Update documentation whenever configuration or API contracts change.
19. Keep the application efficient, responsive and lightweight.
20. Do not declare the project complete while critical tests are failing.

Work directly in the existing repository and preserve its conventions.

==================================================
2. SYSTEM ARCHITECTURE
==================================================

Maintain this architecture unless an actual technical problem requires a justified change.

Frontend:
- HTML
- CSS
- Vanilla JavaScript
- Leaflet
- Responsive mobile-first interface
- GitHub Pages deployment

Backend:
- Python
- FastAPI
- Existing C emergency priority engine
- Secure REST APIs
- Render deployment

Database and authentication:
- Supabase Auth
- Supabase PostgreSQL
- Row Level Security
- User roles
- Emergency records
- Emergency contacts

Testing:
- pytest
- FastAPI TestClient
- JavaScript frontend tests
- Integration tests using isolated test data
- GitHub Actions

The C engine must remain responsible for the existing emergency severity-to-priority calculation. Do not present this calculation as medically validated triage.

==================================================
3. FEATURE ONE — INTELLIGENT EMERGENCY SEVERITY AND SERVICE SELECTION
==================================================

Transform the existing severity selector into a structured emergency classification and service recommendation system.

The system must display individual emergency service cards:

- POLICE
- FIRE & RESCUE
- AMBULANCE / MEDICAL

Each service card must display:

- Service name
- Icon
- Severity level
- Reason for recommendation
- Selection status
- Priority
- Relevant emergency information

Create five configurable emergency levels.

Suggested initial configuration:

LEVEL 1 — LOW
- No automatic emergency-service recommendation.
- Display safety guidance.
- Allow the user to request assistance.

LEVEL 2 — MODERATE
- Display the most relevant service recommendation.
- Allow additional services to be selected.

LEVEL 3 — HIGH
- Recommend the relevant emergency service.
- Allow multiple service combinations.

LEVEL 4 — VERY HIGH
- Recommend multiple relevant emergency services where justified.
- Clearly display the recommended combination.

LEVEL 5 — CRITICAL
- Display all relevant emergency service cards.
- Prioritize urgent medical, police or fire response according to the reported situation.

Important design rules:

- Service recommendations must depend on the reported emergency type and severity.
- Do not assume every critical emergency requires all three services.
- Allow users to modify recommendations where safe and appropriate.
- Never delay an emergency request unnecessarily.
- Clearly distinguish recommended services from services actually contacted.
- Do not imply that a dispatch has occurred in the absence of a real authorized integration.

Create a configurable emergency classification engine.

Separate:
- Severity calculation
- Emergency category
- Service recommendation rules
- Priority calculation
- Display labels

Do not bury business rules inside frontend JavaScript.

Store the selected emergency category, severity, recommended services and requested services in the database where appropriate.

Add tests for all severity levels and service combinations.

==================================================
4. FEATURE TWO — EMERGENCY CONTACT MANAGEMENT
==================================================

Implement a complete emergency contacts system.

Users must be able to:

1. Add an emergency contact.
2. Edit an existing contact.
3. Delete a contact.
4. View all saved contacts.
5. Mark a primary contact.
6. Add relationship information.
7. Add contact name and telephone number.
8. Verify ownership of every contact record.

Database design:

Create an emergency_contacts table with appropriate fields:

- id
- user_id
- name
- phone
- relationship
- is_primary
- created_at
- updated_at

Requirements:

- Contacts belong to authenticated users.
- Users cannot read, modify or delete other users' contacts.
- Add proper RLS policies.
- Validate telephone numbers.
- Prevent duplicate contacts where appropriate.
- Limit the maximum number of contacts per user.
- Handle empty contact lists.
- Add confirmation before deletion.

Emergency contact functionality:

- Provide click-to-call links using tel:.
- Provide an option to copy contact details.
- Provide consent-based notification workflows.
- Show whether a notification was actually sent.
- Maintain an audit record of notification attempts.

Do not pretend an SMS, call or WhatsApp message has been sent unless an actual authorized provider confirms it.

If no notification provider is configured, provide a clear manual-contact fallback.

==================================================
5. FEATURE THREE — COMPLETE ADMIN COMMAND CENTER
==================================================

Build a professional emergency-response command center.

It must be restricted to authenticated ADMIN users.

Do not rely on frontend role checks alone. All administrative access must be verified by the backend.

Command center sections:

A. OVERVIEW

Display:
- Total emergency alerts
- Active emergencies
- Resolved emergencies
- Critical emergencies
- Alerts by severity
- Alerts by emergency category
- Requested services
- Recent emergency activity

B. LIVE EMERGENCY MONITOR

Display:
- Emergency ID
- User/report identifier where permitted
- Emergency category
- Severity
- Priority
- Requested services
- Location
- GPS accuracy
- Submission timestamp
- Current status

C. MAP VIEW

Use Leaflet.

Requirements:
- Show authorized emergency markers.
- Use different marker styles for severity levels.
- Cluster markers when appropriate.
- Display useful emergency information on marker selection.
- Add filters.
- Add location accuracy information.
- Avoid unnecessary map reloads.
- Do not expose unauthorized location information.

D. EMERGENCY DETAILS

An administrator should be able to:

- Open an emergency record.
- Review its details.
- View its location.
- Review its service recommendations.
- Update operational status.
- Record administrative notes.
- Resolve an emergency.
- View status history.

E. ADMIN AUDIT LOG

Record:
- Administrator ID
- Action
- Emergency ID
- Timestamp
- Previous status
- New status
- Relevant metadata

F. DASHBOARD FILTERS

Add filters for:
- Severity
- Status
- Emergency category
- Service type
- Date range
- Search

G. REAL-TIME UPDATES

Implement an appropriate update strategy.

Prefer Supabase Realtime or an efficient polling strategy depending on the current architecture.

Avoid excessive polling and unnecessary database requests.

Clearly distinguish real-time updates from periodic refreshes.

==================================================
6. FEATURE FOUR — COMPLETE EMERGENCY SIMULATOR
==================================================

Create a dedicated emergency simulation environment.

This is a testing environment, not a real emergency-dispatch system.

Create a simulator accessible to authorized administrators and developers.

SIMULATOR FEATURES:

1. Generate synthetic emergency cases.
2. Select emergency category.
3. Select severity level.
4. Select service combinations.
5. Generate synthetic GPS coordinates.
6. Simulate GPS unavailable.
7. Simulate inaccurate GPS.
8. Simulate delayed network responses.
9. Simulate backend failure.
10. Simulate database failure.
11. Simulate duplicate requests.
12. Simulate successful emergency submission.
13. Simulate administrator acknowledgement.
14. Simulate dispatch workflow.
15. Simulate emergency resolution.

SIMULATION SCENARIOS:

- Medical emergency
- Road accident
- Fire
- Theft
- Personal safety emergency
- Multiple-service emergency
- Critical emergency
- Emergency without GPS
- Emergency with poor GPS accuracy
- Duplicate SOS request
- Offline device
- Database unavailable
- Unauthorized user
- Unauthorized administrator action

Create synthetic scenario templates.

SIMULATOR OUTPUT:

Display:
- Scenario ID
- Generated emergency ID
- Severity
- Priority
- Recommended services
- Simulated location
- Processing duration
- Simulated status
- Result
- Errors encountered

IMPORTANT SAFETY REQUIREMENTS:

- Never contact actual police, ambulance, fire services or emergency contacts during simulation.
- Never send real notifications from simulated scenarios.
- Use clearly labelled synthetic data.
- Keep simulated and real records separate.
- Mark every simulator record as SIMULATED.
- Prevent simulated data from appearing in real emergency statistics.
- Prevent simulated alerts from triggering real workflows.
- Provide a reset and cleanup mechanism for test records.
- Do not allow simulator access to modify production emergency records.

If necessary, create separate database tables or a strict environment-based data isolation mechanism.

==================================================
7. FEATURE FIVE — COMPLETE ALL USER-FACING PAGES
==================================================

Audit every HTML page in the repository.

Complete and integrate the pages in the following user-experience order.

PAGE 1 — LANDING PAGE

Create a polished introduction to ResQlink.

Include:
- Branding
- Main value proposition
- How it works
- Key features
- Login
- Registration
- Safety and demo disclaimer

PAGE 2 — REGISTRATION

Include:
- Name
- Email
- Password
- Password visibility
- Input validation
- Error feedback
- Successful registration state

Integrate with Supabase Auth through the existing FastAPI backend.

PAGE 3 — LOGIN

Include:
- Email
- Password
- Remember-session behavior only if supported safely
- Forgot password
- Login errors
- Loading state

PAGE 4 — PASSWORD RECOVERY

Implement the full Supabase password recovery workflow.

Include:
- Email request
- Confirmation message
- Recovery link handling
- New password form
- Password update
- Session validation

PAGE 5 — USER DASHBOARD

Display:
- User information
- Recent personal alerts
- Emergency contact summary
- Account settings
- SOS access
- Logout

PAGE 6 — SOS EMERGENCY PAGE

Make this the primary user experience.

Include:
- Large SOS action
- Emergency category
- Severity
- Police card
- Fire card
- Ambulance card
- Recommended combinations
- GPS location
- GPS accuracy
- Leaflet map preview
- Emergency contacts
- Submission status
- Alert ID
- Error handling

Keep the emergency workflow simple and fast.

Do not introduce unnecessary confirmation steps.

PAGE 7 — EMERGENCY HISTORY

Display:
- User's own emergency records
- Severity
- Category
- Date
- Requested services
- Status
- Available location information

PAGE 8 — EMERGENCY CONTACTS

Implement the complete contact management functionality.

PAGE 9 — ADMIN LOGIN / ACCESS

Use the existing Supabase authentication system and server-verified ADMIN role.

Do not create a separate insecure administrator login system.

PAGE 10 — ADMIN COMMAND CENTER

Implement the full command center described above.

PAGE 11 — SIMULATOR

Implement the emergency simulator described above.

PAGE 12 — ACCOUNT SETTINGS

Include:
- Profile information
- Password management
- Emergency contacts shortcut
- Logout
- Account deletion request or documented deletion workflow

All navigation must work.

All buttons must perform actual actions.

All forms must validate.

All pages must work on mobile and desktop.

==================================================
8. FEATURE SIX — USER EXPERIENCE AND VISUAL DESIGN
==================================================

Create a consistent ResQlink design system.

Design direction:

- Modern
- Professional
- Premium
- Clean
- Dark navy / charcoal foundation
- High-visibility emergency red
- Subtle accent colors
- Clear visual hierarchy
- Smooth but restrained animations
- Accessible typography

Requirements:

1. Create reusable CSS variables.
2. Standardize typography.
3. Standardize buttons.
4. Standardize cards.
5. Standardize navigation.
6. Standardize form controls.
7. Standardize modals.
8. Standardize status indicators.
9. Standardize severity colors.
10. Create reusable loading indicators.
11. Create reusable error messages.
12. Create responsive layouts.
13. Support keyboard navigation.
14. Support screen readers.
15. Maintain sufficient color contrast.
16. Avoid excessive animation.
17. Respect prefers-reduced-motion.

Do not make every page visually identical. Preserve the distinct purpose of the SOS interface and admin command center.

The SOS interface must prioritize speed, readability and accessibility over decorative elements.

==================================================
9. FEATURE SEVEN — PERFORMANCE AND RESOURCE OPTIMIZATION
==================================================

Optimize both client and server performance.

FRONTEND:

- Avoid unnecessary JavaScript dependencies.
- Avoid large frontend frameworks.
- Use reusable CSS.
- Avoid duplicate event listeners.
- Avoid repeated DOM rendering.
- Use efficient DOM updates.
- Lazy-load noncritical resources.
- Optimize map initialization.
- Avoid excessive map marker recreation.
- Debounce search.
- Avoid excessive network calls.
- Cache safe non-sensitive data appropriately.
- Keep bundle and page sizes small.

BACKEND:

- Reuse database clients appropriately.
- Add request timeouts.
- Use efficient database queries.
- Add pagination to large datasets.
- Avoid loading all emergency records unnecessarily.
- Use appropriate database indexes.
- Validate all input.
- Add structured logging.
- Avoid logging passwords, tokens and precise coordinates unnecessarily.
- Handle database failures gracefully.

Measure performance where possible.

Do not sacrifice emergency reliability for marginal performance improvements.

==================================================
10. FEATURE EIGHT — COMPLETE DATABASE DESIGN
==================================================

Inspect the existing Supabase schema before adding anything.

Preserve existing tables and migrations.

Add only the missing schema.

Review these entities:

- profiles
- emergencies
- emergency_contacts
- emergency_status_history
- admin_audit_logs
- simulator_scenarios
- simulator_runs

Use appropriate:
- Foreign keys
- Constraints
- Indexes
- Timestamps
- Ownership relationships
- RLS policies
- Grants

Important:

- Real emergency data and simulator data must be isolated.
- User-owned records must remain private.
- Only authorized administrators can access the command center.
- Do not allow clients to assign their own ADMIN role.
- Use migrations for schema changes.
- Never destroy existing data.
- Document migration order and rollback considerations.

==================================================
11. FEATURE NINE — FULL TESTING
==================================================

Create a complete automated test suite.

BACKEND TESTING:

Test:
- Registration
- Login
- Logout
- Token verification
- Password recovery
- Password update
- User authorization
- Administrator authorization
- Emergency submission
- Emergency ownership
- Emergency listing
- Emergency resolution
- Emergency contacts CRUD
- Service recommendation logic
- Severity logic
- Duplicate requests
- GPS validation
- GPS unavailable
- Rate limits
- Database errors
- Simulator scenarios
- Simulator isolation
- Audit logs

DATABASE TESTING:

Test:
- Table constraints
- Foreign keys
- RLS policies
- User ownership
- Admin access
- Unauthorized access
- Simulator separation
- Duplicate contacts
- Data consistency

FRONTEND TESTING:

Test:
- Navigation
- Login
- Registration
- Logout
- Password recovery
- SOS flow
- Severity selection
- Service card combinations
- GPS status
- Emergency contacts
- Dashboard filters
- Admin access
- Simulator interface
- Error states
- Mobile layout

INTEGRATION TESTING:

Test the full workflow:

1. User registers.
2. Supabase creates the Auth user.
3. Profile is created.
4. User logs in.
5. User adds emergency contacts.
6. User initiates SOS.
7. Backend verifies identity.
8. Emergency engine calculates priority.
9. Service recommendation engine determines the relevant services.
10. Emergency is saved.
11. User sees the confirmation.
12. Administrator accesses the alert.
13. Administrator acknowledges it.
14. Administrator updates status.
15. Administrator resolves the alert.
16. User sees the updated status.

Use synthetic data and isolated test credentials.

Do not perform real emergency dispatch or real notification actions in automated tests.

Add a GitHub Actions workflow that runs the test suite.

All test failures must be investigated and fixed.

Never report tests as passed unless they were actually executed.

==================================================
12. FEATURE TEN — SECURITY AND PRIVACY
==================================================

Conduct a security review.

Verify:

- Supabase service-role key is backend-only.
- No secrets are committed.
- Authentication is enforced.
- Admin authorization is server-side.
- User ownership is enforced.
- RLS is enabled and tested.
- Request validation is strict.
- Rate limits are appropriate.
- CORS is restricted.
- Request size limits are configured.
- XSS risks are controlled.
- SQL injection risks are controlled.
- Passwords are handled only by Supabase Auth.
- Sensitive logs are avoided.
- Precise location access is restricted.
- Emergency data retention is documented.
- Account deletion is handled safely.
- Simulator data cannot affect real emergency operations.

Do not claim legal compliance or production readiness without proper independent review.

==================================================
13. FEATURE ELEVEN — DOCUMENTATION AND MANUAL TODO
==================================================

Create or update:

README.md
TODO.md
DEPLOYMENT.md
TESTING.md
ARCHITECTURE.md
SUPABASE_SETUP.md
API_DOCUMENTATION.md

TODO.md is especially important.

It must list ONLY tasks that genuinely require manual action from me or an external account owner.

Examples:

- Create or configure Supabase project.
- Add private Supabase credentials to Render.
- Configure SMTP credentials.
- Create an administrator account and assign its role securely.
- Configure Render environment variables.
- Configure GitHub Actions repository variables.
- Apply database migrations if they cannot be executed automatically.
- Configure a real SMS provider if notification functionality is required.
- Verify email delivery.
- Perform manual mobile GPS testing.
- Review privacy and retention policy.
- Obtain appropriate authorization before any real emergency-service integration.

For each manual task include:

1. Task name.
2. Why it requires manual action.
3. Exact dashboard or file location.
4. Exact steps.
5. Expected result.
6. Verification method.
7. Whether it blocks deployment.

Automate everything else that can safely be automated.

Do not put already completed tasks into TODO.md.

==================================================
14. REQUIRED IMPLEMENTATION ORDER
==================================================

Execute the project in this order:

PHASE 1 — Repository audit and architecture
PHASE 2 — Database schema and migrations
PHASE 3 — Backend emergency classification and service recommendation
PHASE 4 — Emergency contact backend
PHASE 5 — Authentication and authorization verification
PHASE 6 — User-facing pages
PHASE 7 — SOS interface integration
PHASE 8 — Emergency history
PHASE 9 — Admin command center
PHASE 10 — Emergency simulator
PHASE 11 — Audit logging and operational status
PHASE 12 — UI consistency and accessibility
PHASE 13 — Performance optimization
PHASE 14 — Automated tests
PHASE 15 — Deployment configuration
PHASE 16 — Documentation and TODO.md
PHASE 17 — Final complete regression testing

Do not jump ahead and create a visually polished page with nonfunctional backend behavior.

Complete the dependencies first.

==================================================
15. FINAL ACCEPTANCE CRITERIA
==================================================

The project is considered implementation-complete only when:

1. All required pages exist.
2. All navigation works.
3. All forms work.
4. All backend endpoints are integrated.
5. Supabase authentication works.
6. Database operations work.
7. User ownership is enforced.
8. Admin access is secure.
9. Emergency severity logic works.
10. Service recommendations work.
11. Emergency contacts work.
12. Emergency history works.
13. Admin command center works.
14. Simulator works.
15. Simulator records are isolated.
16. Audit logs work.
17. GPS handling works.
18. Error states are handled.
19. Mobile layout works.
20. Automated tests pass.
21. GitHub Actions passes.
22. Deployment configuration is valid.
23. Documentation is complete.
24. TODO.md contains all remaining manual requirements.

==================================================
16. FINAL DELIVERY REPORT
==================================================

When finished, provide:

A. Summary of all changes.
B. Complete updated file tree.
C. New files created.
D. Existing files modified.
E. Database migrations added.
F. New API endpoints.
G. UI pages completed.
H. Automated tests executed.
I. Test results.
J. Deployment readiness.
K. Security findings.
L. Remaining manual tasks.
M. Contents of TODO.md.
N. Known limitations.
O. Final project completion percentage with a clear calculation method.

Do not fabricate completion percentages or claim external services have been configured when they have not.

Do not claim that police, ambulance or fire services have been contacted.

If a feature requires credentials, paid services, external authorization or manual configuration, implement the integration interface and safe fallback, then list the exact remaining action in TODO.md.

FINAL INSTRUCTION:

Do not stop after producing a plan.

Inspect, implement, integrate, test, fix and document the project.

Every implemented component must be usable, connected to its required dependencies and covered by appropriate tests.

Make ResQlink a coherent, efficient, secure and demonstrable emergency-assistance platform rather than a collection of disconnected pages.