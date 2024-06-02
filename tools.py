import json
import os
import requests
from agency_swarm.tools import BaseTool
from pydantic import Field
from bs4 import BeautifulSoup
from utils import load_config

load_config(file_path="./config.yaml")


class SearchEngine(BaseTool):
    """
    SearchEngine: A search engine tool. You can use this tool to search for a specific query on a search engine.
    The output of the search engine is a dictionary where the key is the source of the information and the value is the content.
    """
    search_engine_query: str = Field(
        ..., description="Search engine query to be executed by the tool"
    )

    def format_results(self, organic_results):

        result_strings = []
        for result in organic_results:
            title = result.get('title', 'No Title')
            link = result.get('link', '#')
            snippet = result.get('snippet', 'No snippet available.')
            result_strings.append(f"Title: {title}\nLink: {link}\nSnippet: {snippet}\n---")

        return '\n'.join(result_strings)

    def run(self):

        search_url = "https://google.serper.dev/search"
        headers = {
            'Content-Type': 'application/json',
            'X-API-KEY': os.environ['SERPER_DEV_API_KEY']  # Ensure this environment variable is set with your API key
        }
        payload = json.dumps({"q": self.search_engine_query})

        # Attempt to make the HTTP POST request
        try:
            response = requests.post(search_url, headers=headers, data=payload)
            response.raise_for_status()  # Raise an HTTPError for bad responses (4XX, 5XX)
            results = response.json()

            # Check if 'organic' results are in the response
            if 'organic' in results:
                return self.format_results(results['organic'])
            else:
                return "No organic results found."

        except requests.exceptions.HTTPError as http_err:
            return f"HTTP error occurred: {http_err}"
        except requests.exceptions.RequestException as req_err:
            return f"Request exception occurred: {req_err}"
        except KeyError as key_err:
            return f"Key error in handling response: {key_err}"


class ScrapeWebsite(BaseTool):
    """
    ScrapeWebsite: A website scraping tool. You can use this tool to scrape the content of a website.
    You must provide the URL of the website you want to scrape.
    """
    website_url: str = Field(
        ..., description="The URL of the website to scrape the content from."
    )

    def run(self):

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.google.com/',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Accept-Encoding': 'gzip, deflate, br'
        }

        try:
            # Making a GET request to the website
            response = requests.get(self.website_url, headers=headers, timeout=15)
            response.raise_for_status()  # This will raise an exception for HTTP errors

            # Parsing the page content using BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')
            text = soup.get_text(separator='\n')
            # Cleaning up the text: removing excess whitespace
            clean_text = '\n'.join([line.strip() for line in text.splitlines() if line.strip()])

            print(f"Successfully scraped content from {self.website_url}")

            return {self.website_url: clean_text}

        except requests.exceptions.RequestException as e:
            print(f"Error retrieving content from {self.website_url}: {e}")
            return {self.website_url: f"Failed to retrieve content due to an error: {e}"}