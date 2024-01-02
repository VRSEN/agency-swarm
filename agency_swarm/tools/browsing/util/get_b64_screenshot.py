import base64
import tempfile


def get_b64_screenshot(wd, element=None):
    tmpfile = tempfile.NamedTemporaryFile(suffix='.png')

    if element:
        element.screenshot(tmpfile.name)
    else:
        wd.get_screenshot_as_file(tmpfile.name)

    tmpfile.seek(0)

    screenshot = tmpfile.read()
    screenshot = base64.b64encode(screenshot).decode()

    tmpfile.close()

    return screenshot