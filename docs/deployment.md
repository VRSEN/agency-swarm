# Deployment to Production

To deploy your Agency on a production server, typically, you need to do the following:

1. **Load Agents and Threads dynamically**: Depending on your use case, you may want to load different agents and threads, based on current user/chat/session.
2. **Deploy each agent as a separate microservice (optional)**: This is useful when you want to scale each agent independently.


## Loading Agents and Threads dynamically

To load agents and threads dynamically, based on specific conditions, you will need to implement `threads_callbacks` and `settings_callbacks` in your agency. 

### Settings Callbacks

Settings is a list of dictionaries that contains states of all the agents within your agency. If any change is detected after you initialize it, settings will be updated, and new settings will be saved to a file specified by `settings_path`. `settings_callbacks` will be executed every time these settings are loaded or saved.

Here is an example of how you can use them:


```python
def load_settings(user_id):
    # your code to load settings from DB here
    settings = load_settings_from_db(user_id)
    return settings

def save_settings(new_settings: List[Dict]):
    # your code to save new_settings to DB here
    save_settings_to_db(new_settings)
```

### Threads Callbacks

Threads is a dictionary that contains all threads between your agents. Loading them from the database, allows your agents to continue their conversations where they left off, even if you are using stateless backend. `threads_callbacks` callbacks work in a same way as `settings_callbacks`, except they are kept in memory, instead of being saved to a file:

```python
def load_threads(chat_id):
    # your code to load threads from DB here
    threads = load_threads_from_db(chat_id)
    return threads

def save_threads(new_threads: Dict):
    # your code to save new_threads to DB here
    save_threads_to_db(new_threads)
```

!!! note
    Make sure you load and return settings and threads in the exact same format as they are saved.

### Example

Below is an example of how you initialize an agency with these callbacks. You will typically need to get some info like `user_id` or `chat_id` beforehand, and pass them into these callbacks, depending on your use case or business logic:
    
```python
agency = Agency([ceo],
                threads_callbacks={
                    'load': lambda: load_threads(chat_id), 
                    'save': lambda new_threads: save_threads(new_threads)
                },
                settings_callbacks={
                    'load': lambda: load_settings(user_id),
                    'save': lambda new_settings: save_settings(new_settings)
                },
                settings_path='my_settings.json'
)
```

## Deploy each agent as a separate microservice

... coming soon ...

