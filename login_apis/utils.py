import magic

def validate_file(file):
    # Get mime type
    mime_type = magic.from_buffer(file.read(), mime=True)
    file.seek(0)  # Reset file pointer
    
    # Define allowed types
    ALLOWED_TYPES = {
        'image': ['image/jpeg', 'image/png', 'image/gif'],
        'document': ['application/pdf', 'application/msword'],
        'excel': ['application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']
    }
    
    # Check file type
    for file_type, mime_types in ALLOWED_TYPES.items():
        if mime_type in mime_types:
            return True, file_type, mime_type
            
    return False, None, mime_type

def get_file_extension(mime_type):
    MIME_TO_EXT = {
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'image/gif': '.gif',
        'application/pdf': '.pdf',
        'application/msword': '.doc',
        'application/vnd.ms-excel': '.xls',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx'
    }
    return MIME_TO_EXT.get(mime_type, '') 