import os
import re

import pandas as pd
import textstat


def process_inline_code(code):
    # Replace dot access with whitespace if detected
    if re.search(r"\w+\.\w+", code):
        code = code.replace(".", " ")
    # Replace square brackets with whitespace
    if "[" in code or "]" in code:
        code = code.replace("[", " ").replace("]", " ")
    return code


def clean_markdown(text):
    # Remove code blocks (triple backticks)
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)

    # Process inline code: Replace inline code blocks with their processed plaintext
    def inline_code_replacer(match):
        code_content = match.group(1)
        processed = process_inline_code(code_content)
        return processed  # Inline code is replaced with its processed content

    text = re.sub(r"`([^`]+)`", inline_code_replacer, text)

    # Replace markdown links with their placeholder value (the text inside the square brackets)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # Optionally, remove or simplify other markdown formatting:
    # Remove headers (leading '#' characters) and emphasis markers
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_~]", "", text)

    return text


def compute_readability(file_path):
    with open(file_path, encoding="utf-8") as f:
        content = f.read()
    # Clean markdown formatting for better readability analysis
    plain_text = clean_markdown(content)

    scores = {
        "File": file_path,
        "Flesch-Kincaid": textstat.flesch_kincaid_grade(plain_text),
        "SMOG Index": textstat.smog_index(plain_text),
        "ARI Index": textstat.automated_readability_index(plain_text),
        "Coleman-Liau": textstat.coleman_liau_index(plain_text),
    }
    return scores


def analyze_docs(root_directory):
    results = []
    for root, _, files in os.walk(root_directory):
        for file in files:
            if file.endswith(".mdx") or file.endswith(".md"):
                file_path = os.path.join(root, file)
                file_path = file_path.replace("\\", "/")
                try:
                    scores = compute_readability(file_path)
                    results.append(scores)
                except Exception as e:
                    print(f"Error processing {file_path}: {e}")
    return results


# Replace 'docs_directory' with the path to your documentation
docs_directory = r"."
readability_results = analyze_docs(docs_directory)

# Convert results to a DataFrame for a clean report
df = pd.DataFrame(readability_results)
print(df)

# Define the threshold
threshold = 15

# Filter the DataFrame where any of the readability scores is above the threshold
filtered_df = df[
    (df["Flesch-Kincaid"] > threshold)
    | (df["SMOG Index"] > threshold)
    | (df["ARI Index"] > threshold)
    | (df["Coleman-Liau"] > threshold)
]

# Extract the list of file names
pages_above_threshold = filtered_df["File"].tolist()
print("Pages with at least one readability score above", threshold, ":", pages_above_threshold)


# Optionally, save the report to CSV for further analysis
df.to_csv("readability_report.csv", index=False)

"""Explainer of results:
Each test shows how many years of education a person needs to be able to effectively read through the text.
Flesch-Kincaid and SMOG Index are popular linguistic benchmarks applicable for most texts
ARI Index and Coleman-Liau are recommended for technical texts.
Generally is it considered that the lower the number is the easier the text is to approach.
When analysing the results just look for outliers.
"""
