import os

docs = {
    "hr_policy.txt": """# GlobalTech HR Policy - Remote Work & Leave\n\n## 1. Remote Work Policy\nGlobalTech offers a hybrid work environment. Employees are expected to be in the office 2 days a week (Tuesday and Thursday). Remote work from another country is allowed for up to 30 days per calendar year.\n\n## 2. Paid Time Off (PTO)\nAll full-time employees accrue 20 days of vacation time per year. Sick leave is capped at 10 days annually. Unused vacation days (up to 5) roll over to the next year.\n""",
    
    "it_hardware.txt": """# IT Hardware Standards\n\n## 1. Laptop Allocations\nEngineers receive a MacBook Pro 16-inch (M3 Max, 64GB RAM). Non-engineers receive a MacBook Air 15-inch (M3, 16GB RAM).\n\n## 2. Hardware Stipend\nGlobalTech provides a one-time hardware stipend of $1,000 for new employees to purchase home office equipment, such as monitors, ergonomic chairs, or standing desks. Expense claims must be submitted within the first 60 days of employment.\n""",
    
    "engineering_stack.txt": """# GlobalTech Engineering Standards\n\n## 1. Approved Technology Stack\n- **Frontend**: We use React 18 with TypeScript and TailwindCSS. Next.js is approved for SEO-facing pages.\n- **Backend**: Our primary backend framework is FastAPI (Python). Legacy microservices are written in Go 1.19.\n- **Database**: PostgreSQL 15 is our primary relational database. Redis is used for caching and Celery task queues.\n- **Infrastructure**: All workloads run on AWS EKS (Kubernetes).\n""",
    
    "incident_management.txt": """## 3. Incident Management\nIn the event of a Sev-1 incident (total system outage), the on-call engineer must open a bridge on Slack (#incident-sev1) and page the secondary on-call via PagerDuty. A post-mortem document is required within 48 hours of resolution.\n\n## 4. Code Reviews\nAll pull requests require at least two approvals from code owners. CI pipelines enforce a minimum of 80% test coverage using pytest for Python and Jest for TypeScript.\n""",

    "sales_playbook.txt": """# Enterprise Sales Playbook\n\n## Target Audience\nWe target CTOs and VPs of Engineering at companies with 500-2000 employees. Our key value proposition is reducing cloud infrastructure costs by 30% without sacrificing reliability.\n\n## Pricing Model\nThe enterprise tier costs $50,000 annually. It includes 24/7 priority support and dedicated account management. Discounts up to 15% can be approved by the Regional Sales Director.\n""",

    "marketing_guidelines.txt": """# Marketing & Brand Guidelines\n\n## Logo Usage\nThe GlobalTech logo must always have a minimum clear space of 20px on all sides. Do not alter the logo's aspect ratio. Our primary brand color is 'Tech Blue' (Hex: #0F52BA).\n\n## Social Media\nAll public social media posts must be reviewed by the PR team. We primarily post on LinkedIn and Twitter. Blog posts are published every Tuesday on Medium.\n""",
    
    "travel_policy.txt": """# Corporate Travel Policy\n\n## Flight Bookings\nAll flights under 6 hours must be booked in Economy class. Flights over 6 hours may be booked in Premium Economy. Business class requires VP approval.\n\n## Hotel & Per Diem\nHotel bookings are capped at $250 per night. The daily meal per diem is $75. All receipts over $25 must be uploaded to Expensify.\n""",
    
    "security_protocol.txt": """# Information Security Protocol\n\n## Passwords\nEmployees must use a password manager (1Password). Passwords must be at least 16 characters long and rotated every 90 days. Multi-factor authentication (MFA) is mandatory for all internal systems.\n\n## Data Handling\nCustomer data (PII) must never be stored on local machines. All PII data in databases must be encrypted at rest using AES-256.\n""",
    
    "onboarding_checklist.txt": """# New Hire Onboarding Checklist\n\n## Day 1\nAttend the IT orientation session at 10:00 AM. Setup Okta SSO and verify access to Slack, Jira, and Confluence.\n\n## Week 1\nComplete the mandatory security compliance training on Workday. Schedule 1-on-1 intro meetings with your immediate team members.\n""",
    
    "benefits_overview.txt": """# Employee Benefits Overview\n\n## Healthcare\nGlobalTech covers 100% of the health, dental, and vision insurance premiums for the employee, and 80% for dependents. The provider is BlueCross BlueShield.\n\n## Retirement\nWe offer a 401(k) matching program up to 5% of your base salary. The vesting period is immediate.\n""",
    
    "product_roadmap.txt": """# Q3 Product Roadmap\n\n## Core Platform\nThe main focus for Q3 is migrating the user authentication service from Auth0 to our in-house Go-based microservice. This is expected to finish by August 15th.\n\n## Mobile App\nVersion 2.0 of the iOS app will launch in September, featuring the new Dark Mode interface and offline sync capabilities.\n""",
    
    "performance_reviews.txt": """# Performance Review Process\n\n## Cycle\nPerformance reviews are conducted bi-annually in June and December. Employees must submit self-evaluations one week before their manager's assessment.\n\n## Ratings\nThe rating scale is 1-5, where 1 is "Needs Improvement" and 5 is "Outstanding". Employees must score at least a 3 to be eligible for a year-end bonus.\n""",
    
    "office_facilities.txt": """# Office Facilities Guide\n\n## Building Access\nThe main office is located at 100 Tech Lane, Austin, TX. Building access badges are required at all times. The office is open 24/7, but HVAC is only active from 7 AM to 7 PM.\n\n## Parking\nEmployees can park in the underground garage. Parking validation tickets are available at the front desk.\n""",
    
    "vendor_management.txt": """# Vendor Management Policy\n\n## Procurement\nAny software purchase over $5,000 requires a formal vendor security assessment (VSA) and approval from the CFO. Software renewals must be reviewed 60 days before expiration.\n\n## NDAs\nAll external contractors must sign a standard Non-Disclosure Agreement before receiving access to any internal documentation or source code.\n""",
    
    "customer_support.txt": """# Customer Support SLA\n\n## Response Times\nFor Enterprise customers, the SLA for first response is 1 hour for high-priority tickets. For Standard customers, the SLA is 24 hours.\n\n## Escalation\nIf a ticket remains unresolved for 48 hours, it must be escalated to the Tier 3 Engineering Support team via Jira Service Desk.\n""",
    
    "qa_testing.txt": """# QA & Testing Standards\n\n## Release Testing\nBefore any major release, a full regression test suite must be run. The release is blocked if there are any open Sev-1 or Sev-2 bugs.\n\n## Automation\nWe aim for 90% automation in our UI tests using Cypress. Manual testing is reserved for exploratory testing of new features.\n""",
    
    "data_retention.txt": """# Data Retention Policy\n\n## User Logs\nApplication access logs are retained for 90 days in Elasticsearch before being archived to AWS S3 Glacier. Archived logs are kept for 7 years for compliance reasons.\n\n## Account Deletion\nWhen a user requests account deletion (GDPR RTBF), all associated PII must be completely purged from our databases within 30 days.\n""",
    
    "training_budget.txt": """# Employee Training Budget\n\n## Allocation\nEach full-time employee has a $1,500 annual budget for professional development. This can be used for conferences, courses, or books.\n\n## Approval\nApproval from the direct manager is required before booking any courses. Receipts must be submitted through Workday.\n""",
    
    "company_values.txt": """# Core Company Values\n\n## Innovation\nWe encourage taking calculated risks and thinking outside the box. Failure is a stepping stone to success, provided we learn from it.\n\n## Transparency\nWe default to open communication. All company metrics and board meeting minutes are available to employees on Confluence.\n""",
    
    "social_events.txt": """# Company Social Events\n\n## Annual Retreat\nThe company hosts an annual offsite retreat every October. Attendance is highly encouraged but not mandatory. This year's retreat will be in Denver, Colorado.\n\n## Team Lunches\nEach team is allocated a budget of $30 per person per month for a team-building lunch or activity.\n"""
}

os.makedirs("documents", exist_ok=True)
for name, content in docs.items():
    with open(f"documents/{name}", "w", encoding="utf-8") as f:
        f.write(content)

print(f"Generated {len(docs)} documents.")
