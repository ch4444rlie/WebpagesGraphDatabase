# Webpage Graph Database with Kùzu and yFiles

This project creates a graph database using [Kùzu](https://kuzudb.com/) to store and analyze connections between webpages, with interactive visualizations powered by [yFiles](https://www.yworks.com/products/yfiles). Developed to explore interconnected ideas across a curated set of webpages and to master the capabilities of Kùzu graph databases, this project serves as both a practical tool for discovering hidden relationships and an educational exercise in graph database design.

![image](https://github.com/user-attachments/assets/1c53a0d9-b26d-484a-b903-678864697fc0)


## Project Overview

**Key Value Propositions**:
- **Discover Hidden Connections**: Identifies latent relationships between webpages, such as links that share keywords despite belonging to different categories, facilitating deeper insights into content relationships.
- **Scalable Foundation**: Provides a flexible graph schema that can scale to larger datasets with automated data ingestion, supporting applications in content analysis, recommendation systems, or knowledge discovery.
- **Learning Kùzu**: Serves as a hands-on exploration of Kùzu’s schema creation, Cypher querying, and database management, offering a practical introduction to graph database workflows.
- **Visual Insights**: Transforms complex relationships into clear, interactive visualizations, making it easier to communicate findings to technical and non-technical audiences.

The pipeline fetches webpage content, processes it using an LLM (Mistral 7B via Ollama) for categorization and keyword extraction, stores the data in Kùzu, and visualizes interconnections with yFiles. 

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


