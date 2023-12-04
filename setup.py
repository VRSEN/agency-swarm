from setuptools import setup, find_packages

# Read the contents of your requirements file
with open('requirements.txt') as f:
    requirements = f.read().splitlines()

setup(
    name='agency-swarm',
    version='0.1.0',
    author='VRSEN',
    author_email='arseny9795@gmail.com',
    description='Replace your own agency with an agent swarm.',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/VRSEN/agency-swarm',
    packages=find_packages(),
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
    entry_points = {
        'console_scripts': ['agency-swarm=agency_swarm.cli:main'],
    },
    python_requires='>=3.7',  # Specify the Python version requirements
)
