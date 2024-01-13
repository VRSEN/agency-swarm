import unittest

from agency_swarm.tools.coding import ChangeDir


class ToolsTest(unittest.TestCase):
    def test_change_dir_example(self):
        output = ChangeDir(path="./").run()
        self.assertFalse("error" in output.lower())


if __name__ == '__main__':
    unittest.main()
