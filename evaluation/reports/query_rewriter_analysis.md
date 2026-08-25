# PHASE 2D — QUERY REWRITER IMPACT

Dataset: 51 queries

Query:
What days are we expected in the office?

Original:
What days are we expected in the office?

Rewritten:
Expected office days

Expected chunks:
['hr_policy_chunk_000']

Raw-query retrieved chunks:
['hr_policy_chunk_000', 'office_facilities_chunk_000', 'product_roadmap_chunk_000', 'it_hardware_chunk_000', 'data_retention_chunk_000']

Rewritten-query retrieved chunks:
['hr_policy_chunk_000', 'office_facilities_chunk_000', 'product_roadmap_chunk_000', 'it_hardware_chunk_000', 'data_retention_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
How many days of remote work from another country?

Original:
How many days of remote work from another country?

Rewritten:
Remote work days from another country

Expected chunks:
['hr_policy_chunk_000']

Raw-query retrieved chunks:
['hr_policy_chunk_000', 'data_retention_chunk_000', 'vendor_management_chunk_000', 'it_hardware_chunk_000', 'security_protocol_chunk_000']

Rewritten-query retrieved chunks:
['hr_policy_chunk_000', 'data_retention_chunk_000', 'vendor_management_chunk_000', 'it_hardware_chunk_000', 'security_protocol_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
How many PTO days do we get?

Original:
How many PTO days do we get?

Rewritten:
pto days allowed

Expected chunks:
['hr_policy_chunk_000']

Raw-query retrieved chunks:
['hr_policy_chunk_000', 'marketing_guidelines_chunk_000', 'data_retention_chunk_000', 'company_values_chunk_000', 'vendor_management_chunk_000']

Rewritten-query retrieved chunks:
['hr_policy_chunk_000', 'marketing_guidelines_chunk_000', 'data_retention_chunk_000', 'company_values_chunk_000', 'vendor_management_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
Does sick leave roll over?

Original:
Does sick leave roll over?

Rewritten:
Does sick leave carry over?

Expected chunks:
['hr_policy_chunk_000']

Raw-query retrieved chunks:
['hr_policy_chunk_000', 'travel_policy_chunk_000', 'vendor_management_chunk_000', 'benefits_overview_chunk_000', 'company_values_chunk_000']

Rewritten-query retrieved chunks:
['hr_policy_chunk_000', 'travel_policy_chunk_000', 'vendor_management_chunk_000', 'benefits_overview_chunk_000', 'company_values_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
What laptop do engineers get?

Original:
What laptop do engineers get?

Rewritten:
Best laptops for engineers

Expected chunks:
['it_hardware_chunk_000']

Raw-query retrieved chunks:
['it_hardware_chunk_000', 'marketing_guidelines_chunk_000', 'tech_stack_chunk_000', 'benefits_overview_chunk_000', 'company_values_chunk_000']

Rewritten-query retrieved chunks:
['it_hardware_chunk_000', 'marketing_guidelines_chunk_000', 'tech_stack_chunk_000', 'benefits_overview_chunk_000', 'company_values_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
How much is the home office hardware stipend?

Original:
How much is the home office hardware stipend?

Rewritten:
home office hardware stipend amount

Expected chunks:
['it_hardware_chunk_000']

Raw-query retrieved chunks:
['it_hardware_chunk_000', 'office_facilities_chunk_000', 'hr_policy_chunk_000', 'benefits_overview_chunk_000', 'product_roadmap_chunk_000']

Rewritten-query retrieved chunks:
['it_hardware_chunk_000', 'office_facilities_chunk_000', 'hr_policy_chunk_000', 'benefits_overview_chunk_000', 'product_roadmap_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
When must expense claims for hardware be submitted?

Original:
When must expense claims for hardware be submitted?

Rewritten:
When is the deadline for submitting hardware expense claims?

Expected chunks:
['it_hardware_chunk_000']

Raw-query retrieved chunks:
['it_hardware_chunk_000', 'data_retention_chunk_000', 'training_budget_chunk_000', 'security_protocol_chunk_000', 'customer_support_chunk_000']

Rewritten-query retrieved chunks:
['it_hardware_chunk_000', 'data_retention_chunk_000', 'training_budget_chunk_000', 'security_protocol_chunk_000', 'customer_support_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
Do non-engineers get a MacBook Pro?

Original:
Do non-engineers get a MacBook Pro?

Rewritten:
Non-engineers use MacBook Pro?

Expected chunks:
['it_hardware_chunk_000']

Raw-query retrieved chunks:
['it_hardware_chunk_000', 'vendor_management_chunk_000', 'marketing_guidelines_chunk_000', 'tech_stack_chunk_000', 'tech_stack_chunk_001']

Rewritten-query retrieved chunks:
['it_hardware_chunk_000', 'vendor_management_chunk_000', 'marketing_guidelines_chunk_000', 'tech_stack_chunk_000', 'tech_stack_chunk_001']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
What frontend framework do we use?

Original:
What frontend framework do we use?

Rewritten:
frontend framework used

Expected chunks:
['engineering_stack_chunk_000']

Raw-query retrieved chunks:
['engineering_stack_chunk_000', 'tech_stack_chunk_000', 'marketing_guidelines_chunk_000', 'security_protocol_chunk_000', 'company_values_chunk_000']

Rewritten-query retrieved chunks:
['engineering_stack_chunk_000', 'tech_stack_chunk_000', 'marketing_guidelines_chunk_000', 'security_protocol_chunk_000', 'company_values_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
Is Next.js approved?

Original:
Is Next.js approved?

Rewritten:
Is Next.js officially supported or recommended?

Expected chunks:
['engineering_stack_chunk_000']

Raw-query retrieved chunks:
['engineering_stack_chunk_000', 'hr_policy_chunk_000', 'sales_playbook_chunk_000', 'tech_stack_chunk_000', 'performance_reviews_chunk_000']

Rewritten-query retrieved chunks:
['engineering_stack_chunk_000', 'hr_policy_chunk_000', 'sales_playbook_chunk_000', 'tech_stack_chunk_000', 'performance_reviews_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
What database does Celery use?

Original:
What database does Celery use?

Rewritten:
Celery database used

Expected chunks:
['engineering_stack_chunk_000']

Raw-query retrieved chunks:
['engineering_stack_chunk_000', 'tech_stack_chunk_000', 'security_protocol_chunk_000', 'benefits_overview_chunk_000', 'company_values_chunk_000']

Rewritten-query retrieved chunks:
['engineering_stack_chunk_000', 'tech_stack_chunk_000', 'security_protocol_chunk_000', 'benefits_overview_chunk_000', 'company_values_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
Do we use Kubernetes?

Original:
Do we use Kubernetes?

Rewritten:
Kubernetes usage?

Expected chunks:
['engineering_stack_chunk_000']

Raw-query retrieved chunks:
['engineering_stack_chunk_000', 'tech_stack_chunk_000', 'marketing_guidelines_chunk_000', 'security_protocol_chunk_000', 'company_values_chunk_000']

Rewritten-query retrieved chunks:
['engineering_stack_chunk_000', 'tech_stack_chunk_000', 'marketing_guidelines_chunk_000', 'security_protocol_chunk_000', 'company_values_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
What to do in a Sev-1 incident?

Original:
What to do in a Sev-1 incident?

Rewritten:
How to respond to a Sev-1 incident?

Expected chunks:
['incident_management_chunk_000']

Raw-query retrieved chunks:
['tech_stack_chunk_001', 'incident_management_chunk_000', 'qa_testing_chunk_000', 'marketing_guidelines_chunk_000', 'hr_policy_chunk_000']

Rewritten-query retrieved chunks:
['tech_stack_chunk_001', 'incident_management_chunk_000', 'qa_testing_chunk_000', 'marketing_guidelines_chunk_000', 'hr_policy_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
How many approvals for a PR?

Original:
How many approvals for a PR?

Rewritten:
PR approval count

Expected chunks:
['incident_management_chunk_000']

Raw-query retrieved chunks:
['incident_management_chunk_000', 'marketing_guidelines_chunk_000', 'tech_stack_chunk_000', 'customer_support_chunk_000', 'data_retention_chunk_000']

Rewritten-query retrieved chunks:
['incident_management_chunk_000', 'marketing_guidelines_chunk_000', 'tech_stack_chunk_000', 'customer_support_chunk_000', 'data_retention_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
What is the minimum test coverage?

Original:
What is the minimum test coverage?

Rewritten:
minimum test coverage requirements

Expected chunks:
['incident_management_chunk_000']

Raw-query retrieved chunks:
['incident_management_chunk_000', 'tech_stack_chunk_000', 'qa_testing_chunk_000', 'marketing_guidelines_chunk_000', 'office_facilities_chunk_000']

Rewritten-query retrieved chunks:
['incident_management_chunk_000', 'tech_stack_chunk_000', 'qa_testing_chunk_000', 'marketing_guidelines_chunk_000', 'office_facilities_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
Who is the target audience for sales?

Original:
Who is the target audience for sales?

Rewritten:
Target audience for sales efforts

Expected chunks:
['sales_playbook_chunk_000']

Raw-query retrieved chunks:
['sales_playbook_chunk_000', 'customer_support_chunk_000', 'benefits_overview_chunk_000', 'product_roadmap_chunk_000', 'qa_testing_chunk_000']

Rewritten-query retrieved chunks:
['sales_playbook_chunk_000', 'customer_support_chunk_000', 'benefits_overview_chunk_000', 'product_roadmap_chunk_000', 'qa_testing_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
How much does the enterprise tier cost?

Original:
How much does the enterprise tier cost?

Rewritten:
Enterprise tier pricing

Expected chunks:
['sales_playbook_chunk_000']

Raw-query retrieved chunks:
['sales_playbook_chunk_000', 'customer_support_chunk_000', 'benefits_overview_chunk_000', 'product_roadmap_chunk_000', 'office_facilities_chunk_000']

Rewritten-query retrieved chunks:
['sales_playbook_chunk_000', 'customer_support_chunk_000', 'benefits_overview_chunk_000', 'product_roadmap_chunk_000', 'office_facilities_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
Who can approve a 15% discount?

Original:
Who can approve a 15% discount?

Rewritten:
Who has authority to approve a 15% discount?

Expected chunks:
['sales_playbook_chunk_000']

Raw-query retrieved chunks:
['sales_playbook_chunk_000', 'training_budget_chunk_000', 'it_hardware_chunk_000', 'office_facilities_chunk_000', 'engineering_stack_chunk_000']

Rewritten-query retrieved chunks:
['sales_playbook_chunk_000', 'training_budget_chunk_000', 'it_hardware_chunk_000', 'office_facilities_chunk_000', 'engineering_stack_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
What is the primary brand color hex code?

Original:
What is the primary brand color hex code?

Rewritten:
Primary brand color hex code

Expected chunks:
['marketing_guidelines_chunk_000']

Raw-query retrieved chunks:
['marketing_guidelines_chunk_000', 'tech_stack_chunk_000', 'incident_management_chunk_000', 'engineering_stack_chunk_000', 'vendor_management_chunk_000']

Rewritten-query retrieved chunks:
['marketing_guidelines_chunk_000', 'tech_stack_chunk_000', 'incident_management_chunk_000', 'engineering_stack_chunk_000', 'vendor_management_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
Who reviews social media posts?

Original:
Who reviews social media posts?

Rewritten:
Social media content reviewers

Expected chunks:
['marketing_guidelines_chunk_000']

Raw-query retrieved chunks:
['marketing_guidelines_chunk_000', 'social_events_chunk_000', 'performance_reviews_chunk_000', 'incident_management_chunk_000', 'benefits_overview_chunk_000']

Rewritten-query retrieved chunks:
['marketing_guidelines_chunk_000', 'social_events_chunk_000', 'performance_reviews_chunk_000', 'incident_management_chunk_000', 'benefits_overview_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
When do we publish blog posts on Medium?

Original:
When do we publish blog posts on Medium?

Rewritten:
Best time to publish blog posts on Medium

Expected chunks:
['marketing_guidelines_chunk_000']

Raw-query retrieved chunks:
['marketing_guidelines_chunk_000', 'data_retention_chunk_000', 'company_values_chunk_000', 'engineering_stack_chunk_000', 'tech_stack_chunk_000']

Rewritten-query retrieved chunks:
['marketing_guidelines_chunk_000', 'data_retention_chunk_000', 'company_values_chunk_000', 'engineering_stack_chunk_000', 'tech_stack_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
When can I book Premium Economy?

Original:
When can I book Premium Economy?

Rewritten:
When is Premium Economy available for booking?

Expected chunks:
['travel_policy_chunk_000']

Raw-query retrieved chunks:
['travel_policy_chunk_000', 'data_retention_chunk_000', 'training_budget_chunk_000', 'office_facilities_chunk_000', 'sales_playbook_chunk_000']

Rewritten-query retrieved chunks:
['travel_policy_chunk_000', 'data_retention_chunk_000', 'training_budget_chunk_000', 'office_facilities_chunk_000', 'sales_playbook_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
Who approves Business class flights?

Original:
Who approves Business class flights?

Rewritten:
Who approves business class flights?

Expected chunks:
['travel_policy_chunk_000']

Raw-query retrieved chunks:
['travel_policy_chunk_000', 'benefits_overview_chunk_000', 'company_values_chunk_000', 'customer_support_chunk_000', 'data_retention_chunk_000']

Rewritten-query retrieved chunks:
['travel_policy_chunk_000', 'benefits_overview_chunk_000', 'company_values_chunk_000', 'customer_support_chunk_000', 'data_retention_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
What is the hotel per diem?

Original:
What is the hotel per diem?

Rewritten:
hotel per diem definition

Expected chunks:
['travel_policy_chunk_000']

Raw-query retrieved chunks:
['travel_policy_chunk_000', 'social_events_chunk_000', 'hr_policy_chunk_000', 'office_facilities_chunk_000', 'benefits_overview_chunk_000']

Rewritten-query retrieved chunks:
['travel_policy_chunk_000', 'social_events_chunk_000', 'hr_policy_chunk_000', 'office_facilities_chunk_000', 'benefits_overview_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
Which password manager do we use?

Original:
Which password manager do we use?

Rewritten:
Recommended password manager

Expected chunks:
['security_protocol_chunk_000']

Raw-query retrieved chunks:
['security_protocol_chunk_000', 'marketing_guidelines_chunk_000', 'engineering_stack_chunk_000', 'training_budget_chunk_000', 'tech_stack_chunk_000']

Rewritten-query retrieved chunks:
['security_protocol_chunk_000', 'marketing_guidelines_chunk_000', 'engineering_stack_chunk_000', 'training_budget_chunk_000', 'tech_stack_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
How often must passwords be rotated?

Original:
How often must passwords be rotated?

Rewritten:
Password rotation frequency guidelines

Expected chunks:
['security_protocol_chunk_000']

Raw-query retrieved chunks:
['security_protocol_chunk_000', 'travel_policy_chunk_000', 'training_budget_chunk_000', 'vendor_management_chunk_000', 'performance_reviews_chunk_000']

Rewritten-query retrieved chunks:
['security_protocol_chunk_000', 'travel_policy_chunk_000', 'training_budget_chunk_000', 'vendor_management_chunk_000', 'performance_reviews_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
What encryption is used for databases at rest?

Original:
What encryption is used for databases at rest?

Rewritten:
Encryption for databases at rest

Expected chunks:
['security_protocol_chunk_000']

Raw-query retrieved chunks:
['security_protocol_chunk_000', 'training_budget_chunk_000', 'engineering_stack_chunk_000', 'data_retention_chunk_000', 'tech_stack_chunk_000']

Rewritten-query retrieved chunks:
['security_protocol_chunk_000', 'training_budget_chunk_000', 'engineering_stack_chunk_000', 'data_retention_chunk_000', 'tech_stack_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
What time is the IT orientation on day 1?

Original:
What time is the IT orientation on day 1?

Rewritten:
IT orientation start time day 1

Expected chunks:
['onboarding_checklist_chunk_000']

Raw-query retrieved chunks:
['onboarding_checklist_chunk_000', 'hr_policy_chunk_000', 'training_budget_chunk_000', 'it_hardware_chunk_000', 'company_values_chunk_000']

Rewritten-query retrieved chunks:
['onboarding_checklist_chunk_000', 'hr_policy_chunk_000', 'training_budget_chunk_000', 'it_hardware_chunk_000', 'company_values_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
When is the security compliance training due?

Original:
When is the security compliance training due?

Rewritten:
security compliance training deadline

Expected chunks:
['onboarding_checklist_chunk_000']

Raw-query retrieved chunks:
['onboarding_checklist_chunk_000', 'data_retention_chunk_000', 'training_budget_chunk_000', 'vendor_management_chunk_000', 'security_protocol_chunk_000']

Rewritten-query retrieved chunks:
['onboarding_checklist_chunk_000', 'data_retention_chunk_000', 'training_budget_chunk_000', 'vendor_management_chunk_000', 'security_protocol_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
Does the company pay 100% of dependent health insurance?

Original:
Does the company pay 100% of dependent health insurance?

Rewritten:
Does the company cover 100% of dependent health insurance?

Expected chunks:
['benefits_overview_chunk_000']

Raw-query retrieved chunks:
['benefits_overview_chunk_000', 'social_events_chunk_000', 'company_values_chunk_000', 'office_facilities_chunk_000', 'tech_stack_chunk_001']

Rewritten-query retrieved chunks:
['benefits_overview_chunk_000', 'social_events_chunk_000', 'company_values_chunk_000', 'office_facilities_chunk_000', 'tech_stack_chunk_001']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
What is the 401k match limit?

Original:
What is the 401k match limit?

Rewritten:
401(k) match contribution limit

Expected chunks:
['benefits_overview_chunk_000']

Raw-query retrieved chunks:
['office_facilities_chunk_000', 'benefits_overview_chunk_000', 'product_roadmap_chunk_000', 'customer_support_chunk_000', 'performance_reviews_chunk_000']

Rewritten-query retrieved chunks:
['office_facilities_chunk_000', 'benefits_overview_chunk_000', 'product_roadmap_chunk_000', 'customer_support_chunk_000', 'performance_reviews_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
What is the Q3 focus for the core platform?

Original:
What is the Q3 focus for the core platform?

Rewritten:
Q3 core platform focus

Expected chunks:
['product_roadmap_chunk_000']

Raw-query retrieved chunks:
['product_roadmap_chunk_000', 'company_values_chunk_000', 'customer_support_chunk_000', 'benefits_overview_chunk_000', 'office_facilities_chunk_000']

Rewritten-query retrieved chunks:
['product_roadmap_chunk_000', 'company_values_chunk_000', 'customer_support_chunk_000', 'benefits_overview_chunk_000', 'office_facilities_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
When is the iOS app version 2 launching?

Original:
When is the iOS app version 2 launching?

Rewritten:
iOS app version 2 release date

Expected chunks:
['product_roadmap_chunk_000']

Raw-query retrieved chunks:
['product_roadmap_chunk_000', 'hr_policy_chunk_000', 'data_retention_chunk_000', 'qa_testing_chunk_000', 'office_facilities_chunk_000']

Rewritten-query retrieved chunks:
['product_roadmap_chunk_000', 'hr_policy_chunk_000', 'data_retention_chunk_000', 'qa_testing_chunk_000', 'office_facilities_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
Does the new app have Dark Mode?

Original:
Does the new app have Dark Mode?

Rewritten:
Dark Mode in new app

Expected chunks:
['product_roadmap_chunk_000']

Raw-query retrieved chunks:
['product_roadmap_chunk_000', 'marketing_guidelines_chunk_000', 'onboarding_checklist_chunk_000', 'qa_testing_chunk_000', 'tech_stack_chunk_000']

Rewritten-query retrieved chunks:
['product_roadmap_chunk_000', 'marketing_guidelines_chunk_000', 'onboarding_checklist_chunk_000', 'qa_testing_chunk_000', 'tech_stack_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
When are performance reviews?

Original:
When are performance reviews?

Rewritten:
When are performance reviews typically scheduled?

Expected chunks:
['performance_reviews_chunk_000']

Raw-query retrieved chunks:
['performance_reviews_chunk_000', 'data_retention_chunk_000', 'incident_management_chunk_000', 'benefits_overview_chunk_000', 'company_values_chunk_000']

Rewritten-query retrieved chunks:
['performance_reviews_chunk_000', 'data_retention_chunk_000', 'incident_management_chunk_000', 'benefits_overview_chunk_000', 'company_values_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
What is the minimum rating for a bonus?

Original:
What is the minimum rating for a bonus?

Rewritten:
minimum bonus rating criteria

Expected chunks:
['performance_reviews_chunk_000']

Raw-query retrieved chunks:
['performance_reviews_chunk_000', 'incident_management_chunk_000', 'marketing_guidelines_chunk_000', 'customer_support_chunk_000', 'benefits_overview_chunk_000']

Rewritten-query retrieved chunks:
['performance_reviews_chunk_000', 'incident_management_chunk_000', 'marketing_guidelines_chunk_000', 'customer_support_chunk_000', 'benefits_overview_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
Where is the Austin office located?

Original:
Where is the Austin office located?

Rewritten:
Location of Austin office

Expected chunks:
['office_facilities_chunk_000']

Raw-query retrieved chunks:
['office_facilities_chunk_000', 'performance_reviews_chunk_000', 'hr_policy_chunk_000', 'it_hardware_chunk_000', 'benefits_overview_chunk_000']

Rewritten-query retrieved chunks:
['office_facilities_chunk_000', 'performance_reviews_chunk_000', 'hr_policy_chunk_000', 'it_hardware_chunk_000', 'benefits_overview_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
Is the HVAC on at night?

Original:
Is the HVAC on at night?

Rewritten:
HVAC running at night?

Expected chunks:
['office_facilities_chunk_000']

Raw-query retrieved chunks:
['office_facilities_chunk_000', 'travel_policy_chunk_000', 'incident_management_chunk_000', 'marketing_guidelines_chunk_000', 'onboarding_checklist_chunk_000']

Rewritten-query retrieved chunks:
['office_facilities_chunk_000', 'travel_policy_chunk_000', 'incident_management_chunk_000', 'marketing_guidelines_chunk_000', 'onboarding_checklist_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
Who approves software purchases over 5000?

Original:
Who approves software purchases over 5000?

Rewritten:
Who approves software purchases over $5000?

Expected chunks:
['vendor_management_chunk_000']

Raw-query retrieved chunks:
['vendor_management_chunk_000', 'travel_policy_chunk_000', 'hr_policy_chunk_000', 'benefits_overview_chunk_000', 'company_values_chunk_000']

Rewritten-query retrieved chunks:
['vendor_management_chunk_000', 'travel_policy_chunk_000', 'hr_policy_chunk_000', 'benefits_overview_chunk_000', 'company_values_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
Do external contractors need an NDA?

Original:
Do external contractors need an NDA?

Rewritten:
Do external contractors require an NDA?

Expected chunks:
['vendor_management_chunk_000']

Raw-query retrieved chunks:
['vendor_management_chunk_000', 'social_events_chunk_000', 'marketing_guidelines_chunk_000', 'benefits_overview_chunk_000', 'company_values_chunk_000']

Rewritten-query retrieved chunks:
['vendor_management_chunk_000', 'social_events_chunk_000', 'marketing_guidelines_chunk_000', 'benefits_overview_chunk_000', 'company_values_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
What is the SLA for enterprise high-priority tickets?

Original:
What is the SLA for enterprise high-priority tickets?

Rewritten:
SLA for enterprise high priority support tickets

Expected chunks:
['customer_support_chunk_000']

Raw-query retrieved chunks:
['customer_support_chunk_000', 'sales_playbook_chunk_000', 'office_facilities_chunk_000', 'benefits_overview_chunk_000', 'product_roadmap_chunk_000']

Rewritten-query retrieved chunks:
['customer_support_chunk_000', 'sales_playbook_chunk_000', 'office_facilities_chunk_000', 'benefits_overview_chunk_000', 'product_roadmap_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
Where are tickets escalated after 48 hours?

Original:
Where are tickets escalated after 48 hours?

Rewritten:
Ticket escalation after 48 hours process

Expected chunks:
['customer_support_chunk_000']

Raw-query retrieved chunks:
['customer_support_chunk_000', 'tech_stack_chunk_001', 'incident_management_chunk_000', 'performance_reviews_chunk_000', 'office_facilities_chunk_000']

Rewritten-query retrieved chunks:
['customer_support_chunk_000', 'tech_stack_chunk_001', 'incident_management_chunk_000', 'performance_reviews_chunk_000', 'office_facilities_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
What tool is used for UI automation?

Original:
What tool is used for UI automation?

Rewritten:
UI automation tools

Expected chunks:
['qa_testing_chunk_000']

Raw-query retrieved chunks:
['qa_testing_chunk_000', 'training_budget_chunk_000', 'engineering_stack_chunk_000', 'tech_stack_chunk_000', 'customer_support_chunk_000']

Rewritten-query retrieved chunks:
['qa_testing_chunk_000', 'training_budget_chunk_000', 'engineering_stack_chunk_000', 'tech_stack_chunk_000', 'customer_support_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
What blocks a release?

Original:
What blocks a release?

Rewritten:
What prevents a release?

Expected chunks:
['qa_testing_chunk_000']

Raw-query retrieved chunks:
['qa_testing_chunk_000', 'tech_stack_chunk_001', 'incident_management_chunk_000', 'it_hardware_chunk_000', 'social_events_chunk_000']

Rewritten-query retrieved chunks:
['qa_testing_chunk_000', 'tech_stack_chunk_001', 'incident_management_chunk_000', 'it_hardware_chunk_000', 'social_events_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
How long are access logs kept in Elasticsearch?

Original:
How long are access logs kept in Elasticsearch?

Rewritten:
Elasticsearch access log retention period

Expected chunks:
['data_retention_chunk_000']

Raw-query retrieved chunks:
['data_retention_chunk_000', 'security_protocol_chunk_000', 'office_facilities_chunk_000', 'onboarding_checklist_chunk_000', 'vendor_management_chunk_000']

Rewritten-query retrieved chunks:
['data_retention_chunk_000', 'security_protocol_chunk_000', 'office_facilities_chunk_000', 'onboarding_checklist_chunk_000', 'vendor_management_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
What happens to logs after 90 days?

Original:
What happens to logs after 90 days?

Rewritten:
log retention after 90 days

Expected chunks:
['data_retention_chunk_000']

Raw-query retrieved chunks:
['data_retention_chunk_000', 'hr_policy_chunk_000', 'security_protocol_chunk_000', 'vendor_management_chunk_000', 'qa_testing_chunk_000']

Rewritten-query retrieved chunks:
['data_retention_chunk_000', 'hr_policy_chunk_000', 'security_protocol_chunk_000', 'vendor_management_chunk_000', 'qa_testing_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
How long do we have for GDPR account deletion?

Original:
How long do we have for GDPR account deletion?

Rewritten:
GDPR account deletion request response time

Expected chunks:
['data_retention_chunk_000']

Raw-query retrieved chunks:
['data_retention_chunk_000', 'marketing_guidelines_chunk_000', 'security_protocol_chunk_000', 'sales_playbook_chunk_000', 'tech_stack_chunk_000']

Rewritten-query retrieved chunks:
['data_retention_chunk_000', 'marketing_guidelines_chunk_000', 'security_protocol_chunk_000', 'sales_playbook_chunk_000', 'tech_stack_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
What is the training budget per year?

Original:
What is the training budget per year?

Rewritten:
annual training budget

Expected chunks:
['training_budget_chunk_000']

Raw-query retrieved chunks:
['training_budget_chunk_000', 'social_events_chunk_000', 'hr_policy_chunk_000', 'travel_policy_chunk_000', 'performance_reviews_chunk_000']

Rewritten-query retrieved chunks:
['training_budget_chunk_000', 'social_events_chunk_000', 'hr_policy_chunk_000', 'travel_policy_chunk_000', 'performance_reviews_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
Are board meeting minutes available to employees?

Original:
Are board meeting minutes available to employees?

Rewritten:
Are employee board meeting minutes accessible?

Expected chunks:
['company_values_chunk_000']

Raw-query retrieved chunks:
['company_values_chunk_000', 'office_facilities_chunk_000', 'hr_policy_chunk_000', 'performance_reviews_chunk_000', 'sales_playbook_chunk_000']

Rewritten-query retrieved chunks:
['company_values_chunk_000', 'office_facilities_chunk_000', 'hr_policy_chunk_000', 'performance_reviews_chunk_000', 'sales_playbook_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
Where is the annual retreat this year?

Original:
Where is the annual retreat this year?

Rewritten:
annual retreat location this year

Expected chunks:
['social_events_chunk_000']

Raw-query retrieved chunks:
['social_events_chunk_000', 'performance_reviews_chunk_000', 'training_budget_chunk_000', 'hr_policy_chunk_000', 'product_roadmap_chunk_000']

Rewritten-query retrieved chunks:
['social_events_chunk_000', 'performance_reviews_chunk_000', 'training_budget_chunk_000', 'hr_policy_chunk_000', 'product_roadmap_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
What is the monthly team lunch budget?

Original:
What is the monthly team lunch budget?

Rewritten:
Monthly team lunch budget amount

Expected chunks:
['social_events_chunk_000']

Raw-query retrieved chunks:
['social_events_chunk_000', 'training_budget_chunk_000', 'customer_support_chunk_000', 'marketing_guidelines_chunk_000', 'onboarding_checklist_chunk_000']

Rewritten-query retrieved chunks:
['social_events_chunk_000', 'training_budget_chunk_000', 'customer_support_chunk_000', 'marketing_guidelines_chunk_000', 'onboarding_checklist_chunk_000']

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

## AGGREGATE IMPACT

| Metric | Raw | Rewritten | Delta |
|---|---|---|---|
| Recall@1 | 96.1% | 96.1% | +0.0% |
| Recall@3 | 100.0% | 100.0% | +0.0% |
| Recall@5 | 100.0% | 100.0% | +0.0% |
| Recall@10| 100.0%| 100.0%| +0.0%|
| MRR | 0.980 | 0.980 | +0.000 |

Rewrite Impact:
Improved: 0
Same: 51
Degraded: 0

Rewrite Latency:
Mean: 0.22 s
P50: 0.17 s
P95: 0.29 s

Token Usage:
Total Tokens: N/A

Conclusion:
Query rewriting was observed to have a mixed/negative impact in these isolated tests because ... (see full report)
