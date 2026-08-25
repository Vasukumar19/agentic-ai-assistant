# Phase 3 Baseline (Current ReAct Agent)

Total cases run: 50

## Metrics
- Tool Selection Accuracy: 44.0%
- Tool Sequence Accuracy: 40.0%
- Multi-Step Completion Rate: 40.0%
- Average Latency: 1.56s

## Failure Analysis
| Failure Mode | Count |
|---|---|
| unnecessary_tool | 17 |
| missing_tool | 6 |
| premature_stop | 7 |

## Failed Cases
- Query: Subtract 45 from 200.
  Expected: ['calculator']
  Actual: ['web_search']
  Failure: unnecessary_tool

- Query: Find the square root of 144.
  Expected: ['calculator']
  Actual: ['web_search']
  Failure: unnecessary_tool

- Query: What is the distance to the Moon?
  Expected: ['web_search']
  Actual: ['calculator']
  Failure: unnecessary_tool

- Query: What is the height of Mount Everest in meters, and what is that divided by 2?
  Expected: ['web_search', 'calculator']
  Actual: ['calculator']
  Failure: missing_tool

- Query: Find the GDP of Germany and calculate 1% of it.
  Expected: ['web_search', 'calculator']
  Actual: ['web_search']
  Failure: premature_stop

- Query: Compare the GDP of USA and Japan.
  Expected: ['web_search', 'web_search']
  Actual: ['calculator']
  Failure: missing_tool

- Query: Who is older: Joe Biden or Donald Trump?
  Expected: ['web_search', 'web_search']
  Actual: ['web_search']
  Failure: premature_stop

- Query: Find the tallest building in New York and the tallest building in Dubai, and tell me the difference in height.
  Expected: ['web_search', 'web_search', 'calculator']
  Actual: ['web_search']
  Failure: premature_stop

- Query: Compare the current stock price of Apple and Microsoft.
  Expected: ['web_search', 'web_search']
  Actual: ['web_search']
  Failure: premature_stop

- Query: Find the wellness stipend amount in our policies and calculate 10% of it.
  Expected: ['rag', 'calculator']
  Actual: ['rag', 'web_search']
  Failure: unnecessary_tool

- Query: According to our internal document, what frontend framework do we use, and what is the latest version of it on the web?
  Expected: ['rag', 'web_search']
  Actual: ['rag', 'calculator']
  Failure: unnecessary_tool

- Query: What cloud provider is listed in our engineering stack, and what is their current stock price?
  Expected: ['rag', 'web_search']
  Actual: ['web_search']
  Failure: missing_tool

- Query: Which laptop do engineers get according to policy, and what is its retail price online?
  Expected: ['rag', 'web_search']
  Actual: ['rag', 'calculator']
  Failure: unnecessary_tool

- Query: Find the CEO of the company in our internal docs, and search the web for their latest news.
  Expected: ['rag', 'web_search']
  Actual: ['web_search']
  Failure: missing_tool

- Query: What is our primary database technology internally, and what is its latest release date?
  Expected: ['rag', 'web_search']
  Actual: ['calculator']
  Failure: missing_tool

- Query: Find India's population, China's population, subtract them, and find 10% of the difference.
  Expected: ['web_search', 'web_search', 'calculator', 'calculator']
  Actual: ['calculator']
  Failure: missing_tool

- Query: Check the hardware policy for the laptop budget, search for a MacBook Pro price, and calculate if it is within budget.
  Expected: ['rag', 'web_search', 'calculator']
  Actual: ['rag', 'web_search']
  Failure: premature_stop

- Query: What is the training budget? Find the cost of an AWS Certified Solutions Architect exam, and tell me how much budget would be left.
  Expected: ['rag', 'web_search', 'calculator']
  Actual: ['rag', 'web_search']
  Failure: premature_stop

- Query: Find the distance from Earth to Mars, and from Earth to Venus. Which is closer?
  Expected: ['web_search', 'web_search', 'calculator']
  Actual: ['web_search']
  Failure: premature_stop

- Query: Remember that my name is Alice.
  Expected: ['memory_update']
  Actual: ['memory_search', 'web_search']
  Failure: unnecessary_tool

- Query: What did I say my name was?
  Expected: ['memory_search']
  Actual: ['memory_search', 'web_search']
  Failure: unnecessary_tool

- Query: Calculate 38 + 76
  Expected: ['calculator']
  Actual: ['web_search']
  Failure: unnecessary_tool

- Query: Calculate 39 + 78
  Expected: ['calculator']
  Actual: ['web_search']
  Failure: unnecessary_tool

- Query: Calculate 42 + 84
  Expected: ['calculator']
  Actual: ['web_search']
  Failure: unnecessary_tool

- Query: Calculate 44 + 88
  Expected: ['calculator']
  Actual: ['web_search']
  Failure: unnecessary_tool

- Query: Calculate 45 + 90
  Expected: ['calculator']
  Actual: ['web_search']
  Failure: unnecessary_tool

- Query: Calculate 46 + 92
  Expected: ['calculator']
  Actual: ['web_search']
  Failure: unnecessary_tool

- Query: Calculate 47 + 94
  Expected: ['calculator']
  Actual: ['web_search']
  Failure: unnecessary_tool

- Query: Calculate 48 + 96
  Expected: ['calculator']
  Actual: ['web_search']
  Failure: unnecessary_tool

- Query: Calculate 50 + 100
  Expected: ['calculator']
  Actual: ['web_search']
  Failure: unnecessary_tool

