import base64
import tempfile


def get_b64_screenshot(wd):
    tmpfile = tempfile.NamedTemporaryFile(suffix='.jpg')
    wd.get_screenshot_as_file(tmpfile.name)

    tmpfile.seek(0)

    screenshot = tmpfile.read()
    screenshot = base64.b64encode(screenshot).decode()

    tmpfile.close()

    return screenshot