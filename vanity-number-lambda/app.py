import json
import re
import itertools
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, Tuple
import boto3
import nltk
from langchain.chat_models import init_chat_model

KEYPAD = {
    '2': ['A', 'B', 'C'],
    '3': ['D', 'E', 'F'],
    '4': ['G', 'H', 'I'],
    '5': ['J', 'K', 'L'],
    '6': ['M', 'N', 'O'],
    '7': ['P', 'Q', 'R', 'S'],
    '8': ['T', 'U', 'V'],
    '9': ['W', 'X', 'Y', 'Z']
}

# Download the NLTK word corpus
# TODO - use lambda layer for NLTK data to avoid slow cold start 
nltk.download('words', download_dir='/tmp/nltk_data', quiet=True)
nltk.data.path.append('/tmp/nltk_data')
WORD_LIST = set(w.lower() for w in nltk.corpus.words.words())

# Configure LangChain bedrock model
llm_response_schema = {
    "title": "phone_numbers",
    "type": "object",
    "properties": {
        "numbers": {
            "type": "array",
            "description": "List of vanity phone numbers",
            "items": {
                "type": "string",
            }
        },
        "numbers_tts": {
            "type": "array",
            "description": "List of vanity phone numbers formatted for TTS",
            "items": {
                "type": "string",
            }
        }
    },
    "required": ["numbers"],
}
llm = init_chat_model("anthropic.claude-3-5-sonnet-20240620-v1:0", model_provider="bedrock_converse")
structured_llm = llm.with_structured_output(llm_response_schema)

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('DYNAMODB_TABLE_NAME', 'vanity-number-results')
table = dynamodb.Table(table_name)

# Configure logger
logger = logging.getLogger(__name__)
level = logging.INFO  # Default log level
logger.setLevel(level)

if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(console_handler)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Parse the Amazon Connect event to extract the customer phone number
        details = event.get('Details', {})
        contact_data = details.get('ContactData', {})
        customer_endpoint = contact_data.get('CustomerEndpoint', {})
        customer_phone_number = customer_endpoint.get('Address', '')
        
        if not customer_phone_number:
            logger.error("No customer phone number found in event")
            return {
                'vanityNumberSuccess': False,
                'vanityNumbers': []
            }
        
        logger.info(f"Processing vanity numbers for customer phone: {customer_phone_number}")
        
        # Generate vanity number candidates
        candidates = generate_vanity_candidates(customer_phone_number)
        
        if not candidates:
            logger.warning("No vanity candidates generated")
            return {
                'vanityNumberSuccess': False,
                'vanityNumbers': ""
            }
        
        # Rank the candidates using AI
        ranked_candidates, ranked_candidates_tts = rank_vanity_candidates(candidates)
        
        logger.info(f"Generated {len(ranked_candidates)} ranked vanity numbers")
        
        # Store results in DynamoDB
        try:
            store_results_in_dynamodb(customer_phone_number, ranked_candidates, ranked_candidates_tts)
            logger.info(f"Successfully stored results in DynamoDB for {customer_phone_number}")
        except Exception as e:
            logger.error(f"Failed to store results in DynamoDB: {str(e)}")
            # Continue execution even if DynamoDB storage fails
        
        return {
            'vanityNumberSuccess': True,
            'vanityNumbers': ", ".join(ranked_candidates_tts) if ranked_candidates_tts else "",
        }
        
    except Exception as e:
        logger.error(f"Error processing vanity numbers: {str(e)}")
        return {
            'vanityNumberSuccess': False,
            'vanityNumbers': "",
        }

def rank_vanity_candidates(candidates: list[str]) -> Tuple[list[str], list[str]]:
    prompt = (
        "Given a list of vanity phone numbers, rank them based on their desirability. "
        "Only rank numbers that are provided, do not generate new ones. "
        "Desirability is based on how easy they are to remember, pronounce, and type. "
        "Give preference to numbers that form common words or phrases, and to options with longer words. "
        "Remove any innappropriate or offensive options.\n\n"
        "Return a list of the top 5 ranked vanity numbers, sorted by desirability.\n\n"
        "Also include a text-to-speech-friendly version of each ranked number in the response that can be "
        "easily understood when spoken verbally by a basic TTS engine. Keep groups of numbers and words together."
        "Convert words to lowercase. For example \"123-4-LOST-90\" should be formatted as \"1234 lost 90\" \n\n"
        f"Vanity Numbers: {', '.join(candidates)}\n\n"
    )
    response = structured_llm.invoke(prompt)
    if response is None or 'numbers' not in response or not response['numbers']:
        logger.warning("No valid vanity candidates returned from ranking model.")
        return []

    if 'numbers_tts' not in response or len(response['numbers_tts']) != len(response['numbers']):
        logger.warning("TTS versions missing or mismatch with vanity numbers.")
        response['numbers_tts'] = response['numbers'] # Fallback to same as numbers if TTS is missing

    return (response['numbers'][:5], response['numbers_tts'][:5])  # Return top 5 candidates


def generate_vanity_candidates(phone_number: str) -> list[str]:
    # Clean up phone number - remove non-digit characters
    phone_number = re.sub(r'\D', '', phone_number)
    
    # Validate phone number length
    if len(phone_number) not in [10, 11]:
        raise ValueError("Phone number must be US format with 10 or 11 digits.")
    
    # Remove leading country code if present (11 digits)
    if len(phone_number) == 11:
        if phone_number[0] != '1':
            raise ValueError("11-digit number must start with country code '1'.")
        phone_number = phone_number[1:]  # Remove leading country code

    area_code = phone_number[:3]
    phone_number_digits = phone_number[3:]

    logger.info(f"Processing phone number digits: {phone_number_digits}")

    # Convert digits to corresponding letter lists
    digit_letters = []
    for digit in phone_number_digits:
        if digit in KEYPAD:
            digit_letters.append(KEYPAD[digit])
        else:
            digit_letters.append([digit])  # Non-mapped digits (e.g., 0 or 1) remain as is

    logger.debug(f"Digit letters mapping: {digit_letters}")
            
    # Generate all combinations of letters as cartesian product
    digit_combinations = list(itertools.product(*digit_letters))
    logger.debug(f"Digit combinations: {len(digit_combinations)} combinations found.")

    candidates = []
    # Generate candidates by iterating over all substrings of each combination
    for s in digit_combinations:
        for i in range(len(s)):
            for j in range(i + 2, len(s) + 1):  # Minimum 2 characters
                word_candidate = "".join(s[i:j])

                # Check if the candidate is a valid word
                if word_candidate.lower() in WORD_LIST:
                    # Reconstruct the phone number using the word candidate
                    phone_candidate = f"{area_code}-{phone_number_digits[:i]}-{word_candidate}-{phone_number_digits[j:]}"
                    candidates.append(phone_candidate)    
                    
    # Remove duplicates and sort candidates
    candidates = list(set(candidates))
    candidates.sort()

    logger.info(f"Found {len(candidates)} vanity candidates for {phone_number}")
    logger.debug(f"Vanity candidates: {candidates}")
    return candidates


def store_results_in_dynamodb(phone_number: str, vanity_numbers: list[str], vanity_numbers_tts: list[str]) -> None:
    """
    Store vanity number results in DynamoDB table.
    
    Args:
        phone_number: The caller's phone number (partition key)
        vanity_numbers: List of ranked vanity numbers
    """
    try:
        # Create the item to store
        item = {
            'phoneNumber': phone_number,
            'vanityNumbers': vanity_numbers,
            'vanityNumbersTTS': vanity_numbers_tts,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        # Store in DynamoDB
        table.put_item(Item=item)
        logger.info(f"Stored vanity results for phone number: {phone_number}")
        
    except Exception as e:
        logger.error(f"Error storing results in DynamoDB: {str(e)}")
        raise