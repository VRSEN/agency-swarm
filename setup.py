from setuptools import setup, find_packages

# Read the contents of your requirements file
with open('requirements.txt') as f:
    requirements = f.read().splitlines()

setup(
    name='agency-swarm',
    version='0.2.0',
    author='VRSEN',
    author_email='arseny9795@gmail.com',
    description='An opensource agent orchestration framework built on top of the latest OpenAI Assistants API.',
    long_description=open('README.md', encoding='utf-8').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/VRSEN/agency-swarm',
    packages=find_packages(exclude=['tests', 'tests.*']),
    install_requires=requirements,
    classifiers=[
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: MIT License',
    ],
    entry_points = {
        'console_scripts': ['agency-swarm=agency_swarm.cli:main'],
    },
    python_requires='>=3.7',
)
