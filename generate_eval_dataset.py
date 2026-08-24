import json

mapping = {
  "benefits_overview": 0,
  "company_values": 1,
  "customer_support": 2,
  "data_retention": 3,
  "engineering_stack": 4,
  "hr_policy": 5,
  "incident_management": 6,
  "it_hardware": 7,
  "marketing_guidelines": 8,
  "office_facilities": 9,
  "onboarding_checklist": 10,
  "performance_reviews": 11,
  "product_roadmap": 12,
  "qa_testing": 13,
  "sales_playbook": 14,
  "security_protocol": 15,
  "social_events": 16,
  "tech_stack": 18,
  "training_budget": 19,
  "travel_policy": 20,
  "vendor_management": 21
}

queries = [
    # HR Policy
    ("What days are we expected in the office?", "hr_policy"),
    ("How many days of remote work from another country?", "hr_policy"),
    ("How many PTO days do we get?", "hr_policy"),
    ("Does sick leave roll over?", "hr_policy"),
    
    # IT Hardware
    ("What laptop do engineers get?", "it_hardware"),
    ("How much is the home office hardware stipend?", "it_hardware"),
    ("When must expense claims for hardware be submitted?", "it_hardware"),
    ("Do non-engineers get a MacBook Pro?", "it_hardware"),
    
    # Engineering Stack
    ("What frontend framework do we use?", "engineering_stack"),
    ("Is Next.js approved?", "engineering_stack"),
    ("What database does Celery use?", "engineering_stack"),
    ("Do we use Kubernetes?", "engineering_stack"),
    
    # Incident Management
    ("What to do in a Sev-1 incident?", "incident_management"),
    ("How many approvals for a PR?", "incident_management"),
    ("What is the minimum test coverage?", "incident_management"),
    
    # Sales Playbook
    ("Who is the target audience for sales?", "sales_playbook"),
    ("How much does the enterprise tier cost?", "sales_playbook"),
    ("Who can approve a 15% discount?", "sales_playbook"),
    
    # Marketing
    ("What is the primary brand color hex code?", "marketing_guidelines"),
    ("Who reviews social media posts?", "marketing_guidelines"),
    ("When do we publish blog posts on Medium?", "marketing_guidelines"),
    
    # Travel
    ("When can I book Premium Economy?", "travel_policy"),
    ("Who approves Business class flights?", "travel_policy"),
    ("What is the hotel per diem?", "travel_policy"),
    
    # Security
    ("Which password manager do we use?", "security_protocol"),
    ("How often must passwords be rotated?", "security_protocol"),
    ("What encryption is used for databases at rest?", "security_protocol"),
    
    # Onboarding
    ("What time is the IT orientation on day 1?", "onboarding_checklist"),
    ("When is the security compliance training due?", "onboarding_checklist"),
    
    # Benefits
    ("Does the company pay 100% of dependent health insurance?", "benefits_overview"),
    ("What is the 401k match limit?", "benefits_overview"),
    
    # Roadmap
    ("What is the Q3 focus for the core platform?", "product_roadmap"),
    ("When is the iOS app version 2 launching?", "product_roadmap"),
    ("Does the new app have Dark Mode?", "product_roadmap"),
    
    # Reviews
    ("When are performance reviews?", "performance_reviews"),
    ("What is the minimum rating for a bonus?", "performance_reviews"),
    
    # Office
    ("Where is the Austin office located?", "office_facilities"),
    ("Is the HVAC on at night?", "office_facilities"),
    
    # Vendor
    ("Who approves software purchases over 5000?", "vendor_management"),
    ("Do external contractors need an NDA?", "vendor_management"),
    
    # Support
    ("What is the SLA for enterprise high-priority tickets?", "customer_support"),
    ("Where are tickets escalated after 48 hours?", "customer_support"),
    
    # QA
    ("What tool is used for UI automation?", "qa_testing"),
    ("What blocks a release?", "qa_testing"),
    
    # Data Retention
    ("How long are access logs kept in Elasticsearch?", "data_retention"),
    ("What happens to logs after 90 days?", "data_retention"),
    ("How long do we have for GDPR account deletion?", "data_retention"),
    
    # Training
    ("What is the training budget per year?", "training_budget"),
    
    # Values & Social
    ("Are board meeting minutes available to employees?", "company_values"),
    ("Where is the annual retreat this year?", "social_events"),
    ("What is the monthly team lunch budget?", "social_events")
]

dataset = []
for i, (q, src) in enumerate(queries):
    dataset.append({
        "id": f"rag_{100+i}",
        "category": "rag",
        "query": q,
        "expected_sources": [mapping[src]]
    })
    
with open("evaluation/datasets/retrieval_extended.json", "w") as f:
    json.dump(dataset, f, indent=2)

print(f"Generated {len(dataset)} evaluation queries.")
