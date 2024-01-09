import base64
import os
import tempfile


def get_b64_screenshot(wd, element=None):
    # Create a temporary file name but don't open it
    _, tmpfile_name = tempfile.mkstemp(suffix='.png')

    try:
        if element:
            element.screenshot(tmpfile_name)
        else:
            wd.get_screenshot_as_file(tmpfile_name)

        with open(tmpfile_name, 'rb') as f:
            screenshot = f.read()
        screenshot_b64 = base64.b64encode(screenshot).decode()

        return screenshot_b64
    finally:
        # Clean up the temporary file
        os.remove(tmpfile_name)