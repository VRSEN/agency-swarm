from setuptools import setup, find_packages

setup(
    name="agency-swarm",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        'ffmpeg-python>=0.2.0',
        'pillow>=8.0.0',
        'pydantic>=1.8.0',
        'pytest>=6.0.0',
        'python-dotenv>=0.19.0',
        'agency-swarm>=0.1.0',
    ],
    python_requires='>=3.8',
)
