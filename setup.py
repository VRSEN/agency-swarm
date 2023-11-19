from setuptools import setup, find_packages

# Read the contents of your requirements file
with open('requirements.txt') as f:
    requirements = f.read().splitlines()

setup(
    name='agency',  # Replace with your package's name
    version='0.1.0',  # Initial version of your package
    author='VRSEN',  # Replace with your name
    author_email='arseny9795@gmail.com',  # Replace with your email address
    description='This project allows anyone',  # Provide a short description
    long_description=open('README.md').read(),  # Long description read from the README.md
    long_description_content_type='text/markdown',  # Content type of the long description
    url='https://github.com/yourusername/your_package_name',  # Replace with the URL of your package's repository
    packages=find_packages(),  # Automatically find all packages and subpackages
    install_requires=requirements,
    classifiers=[
        # Classifiers help users find your project by categorizing it
        'Development Status :: 3 - Alpha',  # Change as appropriate
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: MIT License',  # Choose the appropriate license
        'Programming Language :: Python :: 3',  # Specify which pyhton versions you support
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],
    python_requires='>=3.7',  # Specify the Python version requirements
)
