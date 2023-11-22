class User:
    name: str
    def __init__(self, name: str = None):
        if not name:
            self.name = self.__class__.__name__
        else:
            self.name = name
