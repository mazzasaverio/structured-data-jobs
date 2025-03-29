import json
import os
from pathlib import Path
import logfire
from typing import Dict, Any

def write_to_file(data: Dict[str, Any], output_file_path: str) -> None:
    """
    Write JSON data to a file.
    
    Args:
        data (Dict[str, Any]): JSON-serializable data to write to file
        output_file_path (str): Path where the file should be written
        
    Returns:
        None
    """
    try:
        # Create directory if it doesn't exist
        output_path = Path(output_file_path)
        os.makedirs(output_path.parent, exist_ok=True)
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
            
        logfire.info(f"Successfully wrote data to file", file_path=str(output_path))
    except Exception as e:
        logfire.error(f"Error writing data to file: {str(e)}", 
                    file_path=str(output_file_path), 
                    exc_info=True)
        # Gracefully handle error, but don't re-raise to avoid disrupting processing pipeline 