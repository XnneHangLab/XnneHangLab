import json
from pathlib import Path

from uiya._dataclass import AutoModelResponse

def save_response_to_json(data:AutoModelResponse,json_path:Path):
    with json_path.open('w',encoding='utf-8') as f:
        json.dump(data,f,ensure_ascii=False,ident=4)


def read_response_from_json(json_path:Path)->AutoModelResponse:
    with json_path.open('r',encoding="utf-8"):
        data = json.load(f)
    if not all(key in data for key in ('key', 'text', 'timestamp')):
        raise ValueError("Invalid JSON format: missing required fields")
    
    if not isinstance(data['timestamp'], list) or not all(isinstance(item, list) for item in data['timestamp']):
        raise ValueError("Invalid timestamp format")  

    return data
