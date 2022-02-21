
def write_file(path: str, string: str):
    with open(path, "w") as f:
        f.write(string)

def string_to_snake_case_filename(string: str):
    return string.replace(" ", "_").replace("/","-").lower()