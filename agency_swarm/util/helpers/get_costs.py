from tokencost import calculate_cost_by_tokens
from decimal import Decimal

def get_costs(model: str, usage: dict) -> dict:
    """
    Calculate the costs for prompt and completion based on the model and usage.

    Args:
        model (str): The name of the model used (e.g., "gpt-3.5-turbo", "gpt-4").
        usage (dict): A dictionary containing 'prompt_tokens' and 'completion_tokens'.

    Returns:
        dict: A dictionary containing 'prompt_cost', 'completion_cost', and 'total_cost'.
    """
    prompt_tokens = usage.get('prompt_tokens', 0)
    completion_tokens = usage.get('completion_tokens', 0)

    prompt_cost = calculate_cost_by_tokens(prompt_tokens, model, 'input')
    completion_cost = calculate_cost_by_tokens(completion_tokens, model, 'output')
    total_cost = prompt_cost + completion_cost

    return {
        'prompt_cost': prompt_cost,
        'completion_cost': completion_cost,
        'total_cost': total_cost
    }
