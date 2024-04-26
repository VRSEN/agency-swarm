import unittest
import os
import sys

if __name__ == '__main__':
    os.environ["DEBUG_MODE"] = "True"

    # Change the current working directory to 'tests'
    os.chdir('tests')

    # Create a test suite combining all test cases
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir='.', pattern='test*.py')

    # Create a test runner that will run the test suite
    runner = unittest.TextTestRunner()
    result = runner.run(suite)

    # Exit with a non-zero exit code if tests failed
    if not result.wasSuccessful():
        sys.exit(1)
