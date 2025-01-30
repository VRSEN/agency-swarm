from setuptools import find_packages, setup

# Read the contents of your requirements file
with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="agency-swarm",
    version="0.1.0",
    author="VRSEN",
    author_email="me@vrsen.ai",
    description="An opensource agent orchestration framework built on top of the latest OpenAI Assistants API.",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/VRSEN/agency-swarm",
    packages=find_packages(),
    install_requires=[
        "pydantic>=2.0.0",
        "python-dotenv>=1.0.0",
        "yt-dlp>=2023.12.30",
        "ffmpeg-python>=0.2.0",
    ],
    classifiers=[
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: MIT License",
    ],
    entry_points={
        "console_scripts": ["agency-swarm=agency_swarm.cli:main"],
    },
    python_requires=">=3.8",
)
