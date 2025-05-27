import base64

def convert_file_to_base64(file_path):
    """
    Convert a file to a base64 string
    """
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
