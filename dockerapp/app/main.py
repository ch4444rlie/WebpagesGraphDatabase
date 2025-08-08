from flask import Flask, render_template, request, redirect, url_for, jsonify
import kuzu
import os
import requests
from bs4 import BeautifulSoup
import urllib.parse
from ollama import Client
import re

app = Flask(__name__, template_folder='templates')

# Initialize Kùzu database
db_path = "/app/db/kuzu.db"
try:
    db = kuzu.Database(db_path)
    conn = kuzu.Connection(db)
    conn.execute("CREATE NODE TABLE IF NOT EXISTS Link (url STRING, title STRING, raw_category STRING, raw_content STRING, cleaned_content STRING, keywords STRING, PRIMARY KEY (url))")
    conn.execute("CREATE NODE TABLE IF NOT EXISTS Category (name STRING, PRIMARY KEY (name))")
    conn.execute("CREATE NODE TABLE IF NOT EXISTS Keyword (name STRING, PRIMARY KEY (name))")
    conn.execute("CREATE REL TABLE IF NOT EXISTS BELONGS_TO (FROM Link TO Category)")
    conn.execute("CREATE REL TABLE IF NOT EXISTS HAS_KEYWORD (FROM Link TO Keyword)")
    result = conn.execute("MATCH (l:Link) RETURN COUNT(l) AS cnt")
    count = result.get_next()[0]
    if count == 0:
        conn.execute("MERGE (:Link {url: 'https://kuzudb.com', title: 'Kùzu Database', raw_category: 'Database', raw_content: 'Graph database platform', cleaned_content: 'Graph database platform', keywords: 'graph database'})")
        conn.execute("MERGE (:Link {url: 'https://example.com', title: 'Example Site', raw_category: 'Example', raw_content: 'Example content', cleaned_content: 'Example content', keywords: 'example'})")
        conn.execute("MERGE (:Category {name: 'Database'})")
        conn.execute("MERGE (:Keyword {name: 'graph database'})")
        conn.execute("MATCH (l:Link {url: 'https://kuzudb.com'}), (c:Category {name: 'Database'}) MERGE (l)-[:BELONGS_TO]->(c)")
        conn.execute("MATCH (l:Link {url: 'https://example.com'}), (c:Category {name: 'Database'}) MERGE (l)-[:BELONGS_TO]->(c)")
        conn.execute("MATCH (l:Link {url: 'https://kuzudb.com'}), (k:Keyword {name: 'graph database'}) MERGE (l)-[:HAS_KEYWORD]->(k)")
        print("Kùzu database initialized with sample data")
except Exception as e:
    print(f"Error initializing Kùzu: {e}")
    raise

def parse_category_and_keywords(response):
    if not response:
        return 'Uncategorized', []
    categories = [
        'general tools', 'graph technologies', 'healthcare data', 'ai and legal systems',
        'federated search', 'organized crime analysis', 'beneficial ownership',
        'financial crime technology', 'corporate governance', 'power and utilities',
        'Social Media', 'Community Platform', 'Database', 'News', 'Blog', 'E-commerce',
        'International Economics/Policy', 'Data Analysis'
    ]
    category = 'Uncategorized'
    for cat in categories:
        if cat.lower() in response.lower():
            category = cat
            break
    else:
        match = re.search(r'Category:\s*([A-Za-z\s/]+)(?:\s*Keywords:|$)', response)
        if match:
            category = match.group(1).strip()
    # Extract keywords after "Keywords:" if present
    keywords = []
    match = re.search(r'Keywords:\s*([^.]+)', response)
    if match:
        keyword_str = match.group(1).strip()
        # Split by commas, handle multi-word phrases
        keywords = [k.strip() for k in keyword_str.split(',') if k.strip()][:3]
    if not keywords or keywords == ['none']:
        # Fallback: extract meaningful phrases
        keywords = re.findall(r'\b[A-Z][a-zA-Z\s-]+\b', response)
        keywords = [k.strip() for k in keywords if len(k.split()) <= 2 and k.lower() not in category.lower()][:3]
    return category, keywords if keywords else ['none']

def clean_content_with_ollama(content, ollama_host):
    if not content or len(content.strip()) < 100:
        return ""
    prompt = f"Extract the main meaningful content from the following text, up to 500 characters: {content[:2000]}"
    try:
        client = Client(host=ollama_host, timeout=20)
        response = client.chat(model='mistral:7b-instruct-v0.3-q4_0', messages=[{'role': 'user', 'content': prompt}])
        return response['message']['content'].strip()[:500]
    except Exception as e:
        print(f"Failed to clean content with Ollama: {e}")
        return ""

@app.route("/", methods=["GET"])
def index():
    try:
        result = conn.execute("MATCH (l:Link)-[:BELONGS_TO]->(c:Category) RETURN l.url, l.title, c.name, l.raw_category, l.raw_content, l.cleaned_content, l.keywords")
        links = [{
            "url": row[0],
            "title": row[1],
            "category": row[2],
            "raw_category": row[3],
            "raw_content": row[4] if row[4] else 'Failed to fetch content',
            "cleaned_content": row[5] if row[5] else 'Failed to clean content',
            "keywords": row[6] if row[6] else 'none'
        } for row in result]
        print("Fetched links for index route")
        # Fetch interconnections
        result = conn.execute("""
            MATCH (l1:Link)-[:HAS_KEYWORD]->(k:Keyword)<-[:HAS_KEYWORD]-(l2:Link), 
                  (l1)-[:BELONGS_TO]->(c1:Category), (l2)-[:BELONGS_TO]->(c2:Category)
            WHERE l1.url <> l2.url AND c1.name <> c2.name
            RETURN l1.url, l2.url, k.name, c1.name, c2.name
        """)
        interconnections = [{
            "link1": row[0],
            "link2": row[1],
            "keyword": row[2],
            "category1": row[3],
            "category2": row[4]
        } for row in result]
        return render_template("index.html", links=links, interconnections=interconnections)
    except Exception as e:
        print(f"Error fetching links: {e}")
        return f"Error: {str(e)}", 500

@app.route("/add_link", methods=["POST"])
def add_link():
    try:
        url = request.form["url"]
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        url = urllib.parse.quote(url, safe=':/?=&')
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        content = ""
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            title = soup.title.string.strip() if soup.title else url
            text_elements = soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
            content = ' '.join(element.get_text(strip=True) for element in text_elements)[:5000]
        except requests.RequestException as e:
            print(f"Failed to fetch title/content for {url}: {e}")
            title = url
            content = "Failed to fetch content"
        ollama_host = os.getenv('OLLAMA_HOST', 'http://host.docker.internal:11434')
        cleaned_content = clean_content_with_ollama(content, ollama_host)
        try:
            client = Client(host=ollama_host, timeout=20)
            prompt = f"Given the webpage title '{title}', suggest a single category (e.g., Social Media, Database, News) and up to three keywords (1-2 words each)."
            response = client.chat(model='mistral:7b-instruct-v0.3-q4_0', messages=[{'role': 'user', 'content': prompt}])
            raw_category = response['message']['content'].strip()
            category, keywords = parse_category_and_keywords(raw_category)
            print(f"Ollama raw response: {raw_category}")
            conn.execute("MERGE (c:Category {name: $name})", {"name": category})
            for keyword in keywords:
                if keyword != 'none':
                    conn.execute("MERGE (k:Keyword {name: $name})", {"name": keyword})
                    conn.execute("MATCH (l:Link {url: $url}), (k:Keyword {name: $name}) MERGE (l)-[:HAS_KEYWORD]->(k)", {"url": url, "name": keyword})
            keywords_str = ', '.join(keywords) if keywords and keywords != ['none'] else 'none'
        except Exception as e:
            print(f"Failed to connect to Ollama at {ollama_host}: {e}")
            raw_category = 'Failed to connect to Ollama'
            category = 'Uncategorized'
            keywords = ['none']
            keywords_str = 'none'
            conn.execute("MERGE (c:Category {name: 'Uncategorized'})")
        conn.execute("MERGE (:Link {url: $url, title: $title, raw_category: $raw_category, raw_content: $raw_content, cleaned_content: $cleaned_content, keywords: $keywords})", 
                    {"url": url, "title": title, "raw_category": raw_category, "raw_content": content, "cleaned_content": cleaned_content, "keywords": keywords_str})
        conn.execute("MATCH (l:Link {url: $url}), (c:Category {name: $name}) MERGE (l)-[:BELONGS_TO]->(c)", {"url": url, "name": category})
        print(f"Added link: {url}, Title: {title}, Category: {category}, Keywords: {keywords}")
        return redirect(url_for("index"))
    except Exception as e:
        print(f"Error adding link: {e}")
        return f"Error: {str(e)}", 500

@app.route("/graph_data", methods=["GET"])
def graph_data():
    try:
        nodes = []
        result = conn.execute("MATCH (l:Link) WHERE l.title IS NOT NULL RETURN l.url, l.title")
        for row in result:
            nodes.append({"id": row[0], "label": row[1], "group": "Link"})
        result = conn.execute("MATCH (c:Category) WHERE c.name IS NOT NULL RETURN c.name")
        for row in result:
            nodes.append({"id": row[0], "label": row[0], "group": "Category"})
        result = conn.execute("MATCH (k:Keyword) WHERE k.name IS NOT NULL RETURN k.name")
        for row in result:
            nodes.append({"id": row[0], "label": row[0], "group": "Keyword"})
        edges = []
        result = conn.execute("MATCH (l:Link)-[:BELONGS_TO]->(c:Category) WHERE l.url IS NOT NULL AND c.name IS NOT NULL RETURN l.url, c.name")
        for row in result:
            edges.append({"from": row[0], "to": row[1]})
        result = conn.execute("MATCH (l:Link)-[:HAS_KEYWORD]->(k:Keyword) WHERE l.url IS NOT NULL AND k.name IS NOT NULL RETURN l.url, k.name")
        for row in result:
            edges.append({"from": row[0], "to": row[1]})
        print(f"Graph data: {len(nodes)} nodes, {len(edges)} edges")
        return jsonify({"nodes": nodes, "edges": edges})
    except Exception as e:
        print(f"Error fetching graph data: {e}")
        return jsonify({"nodes": [], "edges": [], "error": str(e)}), 200

if __name__ == "__main__":
    print("Starting Flask server")
    app.run(host="0.0.0.0", port=5000, debug=False)