class AgencySwarmValueError(ValueError):
    def __init__(self, message, message_content):
        super().__init__(message)
        self.message_content = message_content