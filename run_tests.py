import unittest
import os

if __name__ == '__main__':
    # Change the current working directory to 'tests'
    os.chdir('tests')

    # Create a test suite combining all test cases
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir='.', pattern='test*.py')

    # Create a test runner that will run the test suite
    runner = unittest.TextTestRunner()
    runner.run(suite)
