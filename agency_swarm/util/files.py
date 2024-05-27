import mimetypes

def determine_file_type(file_path):
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type:
        if mime_type in [
            'application/json', 'text/csv', 'application/xml', 
            'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/zip'
        ]:
            return "assistants.code_interpreter"
        elif mime_type in [
            'text/plain', 'text/markdown', 'application/pdf', 
            'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        ]:
            return "assistants.file_search"
        elif mime_type.startswith('image/'):
            return "vision"
    return "assistants.file_search"