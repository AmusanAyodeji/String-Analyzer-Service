import re
from fastapi import HTTPException, APIRouter
import psycopg2
from datetime import datetime, timezone
import hashlib
import os
import requests
import json
from dotenv import load_dotenv
from pydantic import BaseModel

router = APIRouter(prefix="/strings", tags=["Strings"])

load_dotenv()

USER = os.getenv("user")
PASSWORD = os.getenv("password")
HOST = os.getenv("host")
PORT = os.getenv("port")
DBNAME = os.getenv("dbname")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


def init_connection():
    conn = psycopg2.connect(
        user=USER,
        password=PASSWORD,
        host=HOST,
        port=PORT,
        dbname=DBNAME
    )
    cur = conn.cursor()
    return conn, cur

def interpret_with_llm(statement):
    prompt = f"""
You are an assistant that converts English statements about words into structured JSON filters, if the statement provided cannot be parsed into filters, respond with Unable to parse natural language query. if the statement provided contains conflicting filters, respond with Query parsed but resulted in conflicting filters.
Schema: {{
    "is_palindrome": bool = None,
    "min_length": int = None,
    "max_length": int = None,
    "word_count": int = None,
    "contains_character": str = None
}}

Examples:
1. "Find words shorter than 8 characters" → {{
    "is_palindrome": None,
    "min_length": None,
    "max_length": 7,
    "word_count": None,
    "contains_character": None
}}
2. "Palindromic strings that has a s" → {{
    "is_palindrome": None,
    "min_length": None,
    "max_length": None,
    "word_count": None,
    "contains_character": "s"
}}
3. "Single word that contains o" → {{
    "is_palindrome": None,
    "min_length": None,
    "max_length": None,
    "word_count": 1,
    "contains_character": "o"
}}
4. "Words between 5 and 10 letters long" → {{
    "is_palindrome": None,
    "min_length": 5,
    "max_length": 10,
    "word_count": None,
    "contains_character": None
}}

Now respond ONLY with a JSON object for this statement:
\"\"\"{statement}\"\"\"
"""

    response = requests.post(
  url="https://openrouter.ai/api/v1/chat/completions",
  headers={
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
  },
  data=json.dumps({
    "model": "openrouter/andromeda-alpha",
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "text",
            "text": prompt
          }
        ]
      }
    ],    
  })
)

    response_json = response.json()

    try:
        choices = response_json.get("choices")
        if not choices or len(choices) == 0:
            raise ValueError("No choices returned by the model")

        message = choices[0].get("message")
        if not message or "content" not in message:
            raise ValueError("No content in the model's message")

        content_str = message["content"].strip()
        if not content_str:
            raise ValueError("Content is empty")

        if content_str == "Unable to parse natural language query":
            return "Unable to parse natural language query"
        
        if content_str == "Query parsed but resulted in conflicting filters":
            return "Query parsed but resulted in conflicting filters"

        match = re.search(r"\{.*\}", content_str, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in content")

        json_str = match.group()

        json_str = json_str.replace("None", "null").replace("True", "true").replace("False", "false")

        filters_dict = json.loads(json_str)

        return {
            "original": statement,
            "parsed_filters": filters_dict
        }

    except (ValueError, json.JSONDecodeError) as e:
        return None


class StringRequest(BaseModel):
    value: str

@router.post("", status_code=201)
def create_string(req: StringRequest):
    value = req.value
    conn, cur = init_connection()
    cur.execute("SELECT * FROM stringproperties WHERE value = %s;", (value,))
    existing = cur.fetchone()

    if existing:
        raise HTTPException(409, "String already exists in the system")
    elif value is None:
        raise HTTPException(400, "Invalid request body or missing 'value' field")
    elif any(not isinstance(word, str) for word in value.split()):
        raise HTTPException(422, "Invalid data type for 'value' (must be string)")
    
    id = hashlib.sha256(value.encode('utf-8')).hexdigest()
    length = len(value)
    is_palindrome = value == value[::-1]
    unique_characters = len(set(value))
    word_count = len(value.split())
    character_frequency_map = {}
    for letter in value:
        if letter in character_frequency_map:
            continue
        character_frequency_map[letter] = value.count(letter)
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    response = {
        "id": id,
        "value": value,
        "properties": {
            "length": length,
            "is_palindrome": is_palindrome,
            "unique_characters": unique_characters,
            "word_count": word_count,
            "sha256_hash": id,
            "character_frequency_map": character_frequency_map
        },
        "created_at": created_at
    }
    cur.execute(
        "INSERT INTO stringProperties (value, length, is_palindrome, unique_characters, word_count, sha256_hash, character_frequency_map, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (value, length, is_palindrome, unique_characters, word_count, id, json.dumps(character_frequency_map), created_at)
    )
    conn.commit()
    cur.close()
    conn.close() 
    return response

@router.get("/filter-by-natural-language")
def filter_with_nlp(query: str):
    filters = interpret_with_llm(query)
    if filters is None:
        raise HTTPException(500, "Error occurred when parsing the natural language query")
    
    if filters == "Unable to parse natural language query":
        raise HTTPException(400, "Unable to parse natural language query")
    
    if filters == "Query parsed but resulted in conflicting filters":
        raise HTTPException(422, "Query parsed but resulted in conflicting filters")
    
    data = get_all_strings_with_filtering(**filters["parsed_filters"])
    return {
        "data": data["data"],
        "count": data["count"],
        "interpreted query": filters
    }
    
@router.get("/{string_value}")
def get_specific_string(string_value: str):
    conn, cur = init_connection()

    cur.execute("SELECT length, is_palindrome, unique_characters, word_count, sha256_hash, character_frequency_map, created_at FROM stringproperties WHERE value = %s",(string_value,))
    result = cur.fetchone()

    if not result:
        raise HTTPException(404, "String does not exist in the system")
    
    response = {
        "id": result[4],
        "value": string_value,
        "properties": {
            "length": result[0],
            "is_palindrome": result[1],
            "unique_characters": result[2],
            "word_count": result[3],
            "sha256_hash": result[4],
            "character_frequency_map": result[5]
        },
        "created_at": result[6]
    }
    cur.close()
    conn.close() 
    return response

@router.get("")
def get_all_strings_with_filtering(is_palindrome: bool = None, min_length:int = None, max_length:int = None, word_count: int = None, contains_character: str = None):
    conn, cur = init_connection()
    data = []
    query = "SELECT value, length, is_palindrome, unique_characters, word_count, sha256_hash, character_frequency_map, created_at FROM stringproperties WHERE length IS NOT NULL"
    filters = []
    if is_palindrome is not None:
        filters.append(f"AND is_palindrome = {is_palindrome}")
    if min_length is not None:
        filters.append(f"AND length >= {min_length}")
    if max_length is not None:
        filters.append(f"AND length <= {max_length}")
    if word_count is not None:
        filters.append(f"AND word_count = {word_count}")
    if contains_character is not None:
        filters.append(f"AND value LIKE '%{contains_character}%'")

    if filters:
        query += " " + " ".join(filters)

    cur.execute(query)
    results = cur.fetchall()
    cur.close()
    conn.close() 

    for result in results:
        data.append({
            "id": result[5],
            "value": result[0],
            "properties": {
                "length": result[1],
                "is_palindrome": result[2],
                "unique_characters": result[3],
                "word_count": result[4],
                "sha256_hash": result[5],
                "character_frequency_map": result[6]
            },
            "created_at": result[7]
        })

    response = {
        "data": data,
        "count": len(data),
        "filters_applied":{
            "is_palindrome": is_palindrome,
            "min_length": min_length,
            "max_length": max_length,
            "word_count": word_count,
            "contains_character": contains_character
        }        
    }

    return response

@router.delete("/{string_value}")
def delete_string(string_value: str):
    conn, cur = init_connection()

    cur.execute("SELECT * FROM stringproperties WHERE value = %s;", (string_value,))
    existing = cur.fetchone()

    if not existing:
        raise HTTPException(404, "String does not exist in the system")
    
    cur.execute("DELETE FROM stringproperties WHERE value = %s;", (string_value,))
    conn.commit()
    cur.close()
    conn.close()

    raise HTTPException(204)