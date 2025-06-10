# Webpage Graph Database with Kùzu and yFiles

This project creates a graph database using [Kùzu](https://kuzudb.com/) to store and analyze connections between webpages, with visualization powered by [yFiles](https://www.yworks.com/products/yfiles). It was developed to explore interconnected ideas and concepts across a curated set of webpages and to learn the capabilities of Kùzu graph databases.

## Project Overview

The goal is to:
- **Discover Connections**: Identify shared keywords and categories across webpages to uncover related concepts and ideas.
- **Learn Kùzu**: Experiment with Kùzu's graph database features, including schema creation, data ingestion, and querying.
- **Visualize Relationships**: Use yFiles to create interactive graph visualizations of links, categories, and keywords.

The pipeline fetches webpage content, cleans and categorizes it using an LLM (Mistral 7B via Ollama), stores the data in a Kùzu graph database, and visualizes interconnections.

## Features

- **Data Collection**: Fetches titles and content from a predefined list of URLs.
- **Content Processing**: Uses BeautifulSoup for scraping and an LLM for cleaning and extracting metadata (categories, keywords).
- **Graph Database**: Stores links, categories, and keywords as nodes in Kùzu, with relationships (`BELONGS_TO`, `HAS_KEYWORD`).
- **Interconnection Analysis**: Queries Kùzu to find links sharing keywords across different categories.
- **Visualization**: Renders the graph with yFiles, using distinct colors and shapes for links, categories, and keywords.

## Improvements in Version 2

Version 2 builds on the initial project with the following enhancements:
- **LLM-Based Content Cleaning**: Replaced basic text processing with an LLM (Mistral 7B via Ollama) to clean BeautifulSoup-extracted content, categorizing it into `garbage_text`, `cleaned_content`, and `unsure_content` for more accurate and meaningful data extraction.
- **Increased Keywords**: Expanded keyword extraction from one to up to three keywords per webpage, capturing a broader range of concepts and improving interconnection analysis.
- **Prevented `db.lock` Errors**: Modified the database initialization and connection logic to ensure proper handling of the Kùzu database (`../db/graph_db`) across cells, preventing `db.lock` conflicts.

These improvements enhance data quality, enrich the graph structure, and improve the reliability of the database operations.

## Dependencies
See pyproject.toml (https://github.com/ch4444rlie/WebpagesGraphDatabase/blob/master/pyproject.toml)


