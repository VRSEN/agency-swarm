import json
import re

def try_parse_json(message: str):
    try:
        data = json.loads(message)
        if isinstance(data, list) or isinstance(data, dict) or isinstance(data, str):
            return data
        else:
            return message
    except json.JSONDecodeError:
        pattern = r"```(?:json\s*)?(.*?)```"
        try:
            match = re.search(pattern, message, flags=re.DOTALL)
            if match:
                data = json.loads(match.group(1).strip())
                return data
            else:
                return message
        except (ValueError, json.JSONDecodeError):
            return message
        
def assert_list_of_dicts(object):
    assert isinstance(object, list) and all(isinstance(item, dict) for item in object), f"{object} should be a list of dicts"
    return