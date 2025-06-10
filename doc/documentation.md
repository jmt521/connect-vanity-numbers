## Architecture Diagram
![Architecture Diagram](./architecture-diagram.png)

## Solution Notes

#### 1. Reasons for implementation choices
- CDK for speed and ease of use
- Python Lambda function for string/list manipulation and popular NLP packages
- LLM call to assist with ranking to attempt to gain more semantic meaning from generated options
    - Programmatic calculation of number options to avoid hallucinations, etc


#### 1a. Struggles and Problems
- More complicated option generation logic than expected
    - Relative difficulty of word lookup, requires use of NLTK
- Difficulty of IaC for Connect Resources
    - Had to work backwards from resources generated through the console
        - e.g. exporting sample flows to get JSON definition, looking at generated Lambda resource policy
    - Easy to miss resources like the Lambda association
- Limited text-to-speech capabilities in Connect flows made reading options difficult


#### 2. Shortcuts
- Relied on LLM to generate "friendly" TTS versions of numbers
    - Not guaranteed to be consistent or accurate
- Download NLTK corpus at Lambda initialization time
    - Leads to occasional timeouts on cold starts
- Used alpha Python Lambda CDK construct in place of custom application bundling
- Minimal code splitting/formatting - just a single Python file for Lambda
- No automated testing or linting


#### 3. With more time
- Do some programmatic ranking in addition to LLM
    - Looking at longest generated word, etc.
- Improve text-to-speech using external service and/or better response formatting
- Tweak LLM ranking prompt and test different models
    - Hit Bedrock quotas and throttling within free tier on newer models
- Improve error handling in Lambda and Connect Flow
- Add the frontend website to view results


#### 4. Before production
- Infrastructure hardening
    - Provisioned capacity for Lambda, Dynamo, and Bedrock
    - VPC where appropriate, least privilege
- Caching 
    - Check Dynamo for prior runs of same caller
    - Optionally cache common digit patterns/substrings
- Performance improvements
    - Pre-download NLTK corpus
    - Look for better word detection patterns
    - Minimize iteration and memory usage for calculating combinations