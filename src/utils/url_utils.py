import logfire

def normalize_url(url):
    """Normalize URL by removing trailing slashes and ensuring consistent formatting."""
    if not url:
        return url
    
    # Remove trailing slash if present
    url = url.rstrip('/')
    
    # Ensure consistent protocol format
    if url.startswith('http://'):
        url = url.replace('http://', 'https://')
    elif not url.startswith('https://'):
        url = f'https://{url}'
    
    return url 