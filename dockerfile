# Use the latest Ubuntu image as the base
FROM ubuntu:latest

# Update apt package list and install python3 and pip3
RUN apt-get update && \
    apt-get install -y python3 python3-pip git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Install the Python package from the cloned repository
RUN pip3 install selenium agency-swarm webdriver-manager selenium_stealth gradio

# Define environment variable for OpenAI API Key
ENV OPENAI_API_KEY YourOpenAIKeyHere

# Expose port 7860
EXPOSE 7860