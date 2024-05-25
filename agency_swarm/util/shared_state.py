class SharedState:
    def __init__(self):
        self.data = {}

    def set(self, key, value):
        if not isinstance(key, str):
            raise ValueError("Key must be a string")
        self.data[key] = value

    def get(self, key, default=None):
        if not isinstance(key, str):
            raise ValueError("Key must be a string")
        return self.data.get(key, default)

    def print_data(self):
        for key, value in self.data.items():
            print(f"{key}: {value}")