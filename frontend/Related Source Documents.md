Related Source Documents 

Tech Talent Transformation Program Dashboard Corrected.xlsx — learner, cohort, activity and course data 

Financial Tracker.xlsx — program budget, resource cost and overhead data 

Approved Government of Alberta / company brochure, flyer and standee collateral — brand and typography reference 

Tech Talent Transformation — Power Fx Formula Reference (companion document, referenced in Appendix A) 

 

Distribution 

Development / Implementation Team (Power Apps build) 

Program Office (Elaiyaraja,  Dey) 

Program Leadership ( Srinivasan,  Shaikh4) 

1. Executive Summary 

The Tech Talent Transformation program, funded by the Government of Alberta and delivered by company, upskills internationally trained IT professionals through a 6-month, multi-stream learning journey (Mandatory, Foundational, Technical, Buddy and Leadership training). The program is tracked today through two Excel workbooks — a Program Dashboard and a Financial Tracker — maintained by the Program Office. 

This pack defines the requirements, scope, solution blueprint and wireframes for a role-based Program Dashboard application to be built in Microsoft Power Apps, replacing manual review of the Excel trackers with an interactive, persona-aware experience for Learners, Learning Managers, Leaders and the Program Office. 

A fully functional interactive prototype has already been built and validated (in HTML/CSS/JS, using the program's real learner, cohort, activity and financial data) to prove out the navigation, role logic, visual design and business rules described in this document. The prototype is the reference implementation the development team should replicate in Power Apps; screen-by-screen wireframes and the exact Power Fx formulas needed are included in Section 5 and Appendix A respectively. 

1.1 Why this matters now 

Cohort1 and Cohort2 are live (3 and 13 learners respectively); ten more cohorts are planned through 2028. 

Leadership currently has no single, governed view of learner progress, cohort pacing, or program financials — data lives in two separate spreadsheets. 

A key gap identified during design review: cohort-level “completion” was being measured only as learner course-completion percentage, which does not answer whether the program is progressing against its planned schedule. This pack corrects that with a dedicated schedule-vs-content completion model (Section 4.6). 

1.2 What this pack contains 

Section 2 — Business Requirements: functional and non-functional requirements, organized by persona, plus the corrected business rule for schedule/content reporting. 

Section 3 — Scope: in-scope and out-of-scope items, assumptions and constraints for the initial release. 

Section 4 — Solution Blueprint: architecture, data model, source-table preparation checklist, roles/access matrix, navigation map and brand/visual guidelines. 

Section 5 — Wireframes: annotated screen-by-screen layouts for all eight core screens. 

Appendix A — Power Fx Formula Reference: pointer and key excerpts from the companion formula document. 

Appendix B — Glossary and confirmed role assignments. 

2. Business Requirements 

2.1 Business Objectives 

Give every learner a single, personal homepage showing their assigned cohort, learning path, and real-time course completion status. 

Give Learning Managers a cohort-scoped operational view limited to the cohorts they are assigned to manage. 

Give Leaders and the Program Office a full program-wide view across all cohorts and learners, plus program financials. 

Report program pacing (“is the program on schedule?”) separately from learner content completion, so leadership is not misled by early-stage cohorts showing low completion. 

Reduce reliance on manually maintained Excel files as the leadership reporting tool, while continuing to use Excel as the system of record for the MVP. 

Present the application using the program's approved Government of Alberta / company branding, typography and color palette. 

 

2.2 Personas / Roles 

Role 

Confirmed people 

Primary needs 

Learner 

All 16 enrolled learners (see Appendix B) 

View my cohort, learning path, course-level progress, and upcoming activities 

Learning Manager 

Tendai MakwanhaBere, Rakesh Behera02, Rishad Luthra 

Manage learners and activities within assigned cohorts only 

Leader 

 Srinivasan,  Shaikh4 

Full program visibility, schedule pacing, and financials 

Program Office 

Elaiyaraja, Dey 

Full program visibility, financials, and data-quality oversight 

 

2.3 Functional Requirements 

Requirements are grouped by persona. Each requirement is uniquely numbered for traceability during development and testing. 

2.3.1 Learner 

ID 

Requirement 

Priority 

FR-01 

On sign-in, the app must identify the learner from their signed-in email and show only their own record — never another learner's data. 

Must have 

FR-02 

Display the learner's name, employee ID, assigned cohort, learning stream, and joining date. 

Must have 

FR-03 

Display an overall weighted completion percentage, based on completed vs. planned learning hours (not a simple average of course percentages). 

Must have 

FR-04 

Show a 5-stage learning journey stepper (Mandatory → Foundational → Technical → Buddy → Leadership) with per-stage completion. 

Must have 

FR-05 

Provide a searchable, filterable course list (by learning phase and status) showing per-course platform, hours and completion %. 

Must have 

FR-06 

Clicking a KPI card (Completed / In Progress / Not Started) filters the course list to that status. 

Should have 

FR-07 

Clicking a journey stage filters the course list to that stage. 

Should have 

FR-08 

Show the learner's cohort timeline (planned start/end dates, actual vs. planned enrollment) and up to 3 upcoming, non-completed cohort activities. 

Must have 

 

2.3.2 Learning Manager 

ID 

Requirement 

Priority 

FR-10 

Show only learners and cohorts the signed-in Learning Manager is explicitly granted access to (cohort-level access control). 

Must have 

FR-11 

Provide a learner directory (search, cohort filter, sortable by name/cohort/stream/progress) scoped to assigned cohorts. 

Must have 

FR-12 

Allow drill-through from the directory into any assigned learner's full detail view (read-only, same layout as the learner's own homepage). 

Must have 

FR-13 

Provide a cohort list and cohort detail view scoped to assigned cohorts, including schedule-vs-content progress (see 2.5). 

Must have 

 

2.3.3 Leader & Program Office 

ID 

Requirement 

Priority 

FR-20 

Show full visibility across all 16 learners and all 12 cohorts, with no cohort-access restriction. 

Must have 

FR-21 

Display true program-wide totals sourced from the Dashboard sheet (total cohorts, total learners, activities completed, trainings completed) alongside computed metrics. 

Must have 

FR-22 

Display a single “Program schedule progress” KPI, calculated from planned cohort timelines (not learner content completion) — see Business Rule BR-01 in 2.5. 

Must have 

FR-23 

Display “Avg course completion” as a separate, clearly labeled, informational KPI — never combined with or substituted for schedule progress. 

Must have 

FR-24 

Provide a full learner directory and full cohort list/detail across the whole program. 

Must have 

FR-25 

Provide a dedicated Program Financials screen, visible only to Leader and Program Office roles (see 2.3.4). 

Must have 

FR-26 

On the cohort list and cohort detail screens, show a computed status badge: On Track / Ahead of Schedule / Behind Schedule / Not Started (see BR-01). 

Must have 

 

2.3.4 Program Financials (Leader & Program Office only) 

ID 

Requirement 

Priority 

FR-30 

Restrict the Financials screen and its navigation entry to Leader and Program Office roles only, enforced both in navigation and on the screen itself. 

Must have 

FR-31 

Show total program budget, actual cost to date, estimate to complete, and budget usage %, sourced from the Financial Tracker Summary sheet. 

Must have 

FR-32 

Show a Resource Cost vs. Overhead Cost breakdown, each clickable to filter the detail tables below. 

Must have 

FR-33 

Show resource cost by team member (budget, actual, remaining, usage %) and overhead cost by line item. 

Must have 

FR-34 

Provide a Monthly / Quarterly toggle on the spend-trend chart; clicking any bar reveals exact figures and variance/delta for that period. 

Should have 

 

2.4 Non-Functional Requirements 

Category 

Requirement 

Branding 

Visuals must use the approved Government of Alberta / company color palette and typography, sampled directly from approved brochure, flyer and standee collateral (see 4.7). 

Theming 

The application must support both light and dark mode, toggleable by the user, with the preference remembered between sessions. 

Security 

Role and cohort access must be enforced by data source filtering (Power Fx formulas), not by hiding controls alone. Financial data requires an additional SharePoint/Excel-level permission layer. 

Performance 

Screens must load learner- and cohort-scoped data without requiring the full dataset to be pulled into the client where avoidable (use delegable Filter/LookUp patterns). 

Data integrity 

The application must not silently “correct” known data-quality issues in the source workbook; it should surface them transparently (see 4.4). 

Auditability 

All financial and schedule calculations must be traceable to a named source sheet/column, documented in Section 4 and Appendix A. 

Testability 

The application must include a role-switch mechanism restricted to a non-production/test context, so QA can validate every persona without needing separate Entra ID test accounts (see 4.5). 

 

2.5 Key Business Rules 

BR-01 — Schedule progress vs. content completion (critical, corrects an earlier design gap) 

“Cohort completion” must never be reported as a single number derived only from average learner course-completion percentage. That measures learning content progress, not program pacing, and can make an on-track, just-started cohort look alarmingly incomplete. 

Two distinct metrics must always be shown together, clearly labeled: 

Schedule / timeline progress — % of the cohort's planned calendar (start date to end date) elapsed as of today, calculated from Cohort Plan dates only. 

Content completion — average learner course-completion % for learners enrolled in that cohort, calculated from the Learner Tracker (unchanged calculation, relabeled for clarity). 

A computed status compares the two: Ahead of Schedule (content − timeline ≥ +5 pts), Behind Schedule (content − timeline ≤ −10 pts), otherwise On Track. Not Started applies before a cohort's planned start date. See Section 4.6 for the full model and Appendix A for exact formulas. 

BR-02 — Weighted, not simple-average, learner completion 

A learner's overall completion percentage must be the ratio of completed learning hours to planned learning hours (hours-weighted), not a simple average of individual course percentages, so that longer courses are weighted appropriately. 

BR-03 — Role-scoped data, not just role-scoped screens 

Cohort and learner visibility for Learning Managers must be enforced through a data filter joined against an explicit Cohort Access table — never by simply hiding navigation items while leaving the underlying data query unrestricted. 