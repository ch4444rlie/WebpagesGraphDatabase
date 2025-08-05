from flask import Flask, request, render_template, jsonify
import kuzu
import os
import pandas as pd
import requests
from bs4 import BeautifulSoup
from ollama import Client
from pydantic import BaseModel, Field
import json

app = Flask(__name__, template_folder='templates', static_folder='static')

# Initialize Kùzu database
db_path = os.path.join("db", "graph_db")
os.makedirs(db_path, exist_ok=True)
try:
    db = kuzu.Database(db_path)
    conn = kuzu.Connection(db)
    result = conn.execute("CALL show_tables() RETURN name")
    existing_tables = [row[0] for row in result.get_as_arrow().to_pandas()]
    if "Link" not in existing_tables:
        conn.execute("CREATE NODE TABLE Link(url STRING, category STRING, title STRING, keyword STRING, category_explanation STRING, keyword_explanation STRING, PRIMARY KEY(url))")
        conn.execute("CREATE NODE TABLE Category(name STRING, PRIMARY KEY(name))")
        conn.execute("CREATE NODE TABLE Keyword(name STRING, PRIMARY KEY(name))")
        conn.execute("CREATE REL TABLE BELONGS_TO(FROM Link TO Category)")
        conn.execute("CREATE REL TABLE HAS_KEYWORD(FROM Link TO Keyword)")
except Exception as e:
    print(f"Error initializing Kùzu database: {str(e)}")

# Pydantic model for metadata
class ArticleClassification(BaseModel):
    category: str = Field(..., description="The assigned category (2-3 words)", min_length=2, max_length=50)
    keywords: list[str] = Field(..., description="Up to three key terms (1-2 words each)", min_items=1, max_items=3)
    category_explanation: str = Field(..., description="One sentence explaining the category choice", min_length=10, max_length=200)
    keyword_explanations: list[str] = Field(..., description="One sentence per keyword explaining the choice", min_items=1, max_items=3)

# Fetch webpage content
def fetch_webpage_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        text_elements = soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        text = ' '.join(element.get_text(strip=True) for element in text_elements)
        title = soup.find('title').text if soup.find('title') else url
        return text[:5000], title[:255]
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return "", url

# Generate metadata with Ollama
def generate_metadata(content, url):
    if not content or len(content.strip()) < 100:
        return {"category": "uncategorized", "keywords": ["none"], "category_explanation": "Insufficient content", "keyword_explanations": ["No keywords extracted"], "title": url}
    suggested_categories = ["general tools", "graph technologies", "healthcare data", "ai and legal systems", "federated search", "organized crime analysis", "beneficial ownership", "financial crime technology", "corporate governance", "power and utilities"]
    template = f"""
    You are an expert at categorizing articles. Analyze the content and provide:
    - "category": A category (2-3 words, from {', '.join(suggested_categories)} or a new one)
    - "keywords": Up to three key terms (1-2 words each, e.g., 'knowledge graph')
    - "category_explanation": One sentence explaining the category choice
    - "keyword_explanations": One sentence per keyword explaining the choice
    Return JSON wrapped in ```json\n{{}}\n```.
    Content: {content[:2000]}
    """
    try:
        client = Client(host='http://host.docker.internal:11434')  # Access local Ollama
        response = client.generate(model='mistral:7b-instruct-v0.3-q4_0', prompt=template, options={"temperature": 0.4})
        raw_response = response['response'].strip()
        if raw_response.startswith('```json'):
            raw_response = raw_response[7:].rsplit('```', 1)[0].strip()
        result = json.loads(raw_response)
        metadata = ArticleClassification.model_validate(result).dict()
        metadata['title'] = fetch_webpage_content(url)[1]  # Add title
        return metadata
    except Exception as e:
        print(f"Error processing {url} with Ollama: {e}")
        return {"category": "uncategorized", "keywords": ["none"], "category_explanation": "Failed to process", "keyword_explanations": ["No keywords extracted"], "title": url}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/add_link", methods=["POST"])
def add_link():
    try:
        data = request.json
        url = data.get("url", "").replace("'", "\\'")
        if not url:
            return jsonify({"error": "URL is required"}), 400

        # Fetch content and generate metadata
        content, title = fetch_webpage_content(url)
        metadata = generate_metadata(content, url)
        title = metadata.get("title", title).replace("'", "\\'")
        category = metadata.get("category", "uncategorized").replace("'", "\\'")
        keywords = ", ".join(metadata.get("keywords", ["none"])).replace("'", "\\'")
        category_explanation = metadata.get("category_explanation", "Failed to process").replace("'", "\\'")
        keyword_explanation = "; ".join(metadata.get("keyword_explanations", ["No keywords extracted"])).replace("'", "\\'")

        # Insert Link node
        conn.execute(f"""
            MERGE (l:Link {{url: '{url}'}})
            SET l.category = '{category}',
                l.title = '{title}',
                l.keyword = '{keywords}',
                l.category_explanation = '{category_explanation}',
                l.keyword_explanation = '{keyword_explanation}'
        """)
        # Insert Category node and relationship
        if category and category != "uncategorized":
            conn.execute(f"MERGE (c:Category {{name: '{category}'}})")
            conn.execute(f"""
                MATCH (l:Link {{url: '{url}'}}), (c:Category {{name: '{category}'}})
                MERGE (l)-[:BELONGS_TO]->(c)
            """)
        # Insert Keyword nodes and relationships
        for keyword in metadata.get("keywords", []):
            keyword_escaped = keyword.replace("'", "\\'")
            if keyword_escaped:
                conn.execute(f"MERGE (k:Keyword {{name: '{keyword_escaped}'}})")
                conn.execute(f"""
                    MATCH (l:Link {{url: '{url}'}}), (k:Keyword {{name: '{keyword_escaped}'}})
                    MERGE (l)-[:HAS_KEYWORD]->(k)
                """)
        return jsonify({"status": "success", "metadata": metadata})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/get_links")
def get_links():
    try:
        result = conn.execute("MATCH (l:Link) RETURN l.url, l.title, l.category, l.keyword")
        links = [{"URL": row[0], "Title": row[1], "Category": row[2], "Keywords": row[3]} 
                 for row in result.get_as_arrow().to_pandas()]
        return jsonify(links)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/get_graph")
def get_graph():
    try:
        nodes = []
        edges = []
        result = conn.execute("MATCH (l:Link) RETURN l.url, l.category, l.title, l.keyword LIMIT 50")
        for row in result.get_as_arrow().to_pandas():
            nodes.append({"id": row[0], "properties": {"type": "Link", "label": row[2] or row[0], "category": row[1], "keywords": row[3]}})
        result = conn.execute("MATCH (c:Category) RETURN c.name")
        for row in result.get_as_arrow().to_pandas():
            nodes.append({"id": row[0], "properties": {"type": "Category", "label": row[0]}})
        result = conn.execute("MATCH (k:Keyword) RETURN k.name")
        for row in result.get_as_arrow().to_pandas():
            nodes.append({"id": row[0], "properties": {"type": "Keyword", "label": row[0]}})
        result = conn.execute("MATCH (l:Link)-[:BELONGS_TO]->(c:Category) RETURN l.url, c.name")
        for row in result.get_as_arrow().to_pandas():
            edges.append({"start": row[0], "end": row[1], "properties": {"type": "BELONGS_TO"}})
        result = conn.execute("MATCH (l:Link)-[:HAS_KEYWORD]->(k:Keyword) RETURN l.url, k.name")
        for row in result.get_as_arrow().to_pandas():
            edges.append({"start": row[0], "end": row[1], "properties": {"type": "HAS_KEYWORD"}})
        return jsonify({"nodes": nodes, "edges": edges})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)