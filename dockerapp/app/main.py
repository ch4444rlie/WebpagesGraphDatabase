from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
import kuzu
import os
import requests
from bs4 import BeautifulSoup
import urllib.parse
from ollama import Client
import re
import io
import csv

app = Flask(__name__, template_folder='templates')
app.secret_key = 'your_secret_key'  # Replace with a secure random string in production

# Initialize Kùzu database
db_path = "/app/db/kuzu.db"
try:
    db = kuzu.Database(db_path)
    conn = kuzu.Connection(db)
    conn.execute("CREATE NODE TABLE IF NOT EXISTS Link (url STRING, title STRING, raw_category STRING, suggested_category STRING, raw_content STRING, cleaned_content STRING, keywords STRING, category_explanation STRING, keyword_explanation STRING, PRIMARY KEY (url))")
    conn.execute("CREATE NODE TABLE IF NOT EXISTS Category (name STRING, PRIMARY KEY (name))")
    conn.execute("CREATE NODE TABLE IF NOT EXISTS Keyword (name STRING, PRIMARY KEY (name))")
    conn.execute("CREATE REL TABLE IF NOT EXISTS BELONGS_TO (FROM Link TO Category)")
    conn.execute("CREATE REL TABLE IF NOT EXISTS HAS_KEYWORD (FROM Link TO Keyword)")
    result = conn.execute("MATCH (l:Link) RETURN COUNT(l) AS cnt")
    count = result.get_next()[0]
    if count == 0:
        conn.execute("MERGE (:Link {url: 'https://kuzudb.com', title: 'Kùzu Database', raw_category: 'Database', suggested_category: 'Database', raw_content: 'Graph database platform', cleaned_content: 'Graph database platform', keywords: 'graph database', category_explanation: 'None', keyword_explanation: 'None'})")
        conn.execute("MERGE (:Link {url: 'https://example.com', title: 'Example Site', raw_category: 'Example', suggested_category: 'Example', raw_content: 'Example content', cleaned_content: 'Example content', keywords: 'example', category_explanation: 'None', keyword_explanation: 'None'})")
        conn.execute("MERGE (:Category {name: 'Database'})")
        conn.execute("MERGE (:Keyword {name: 'graph database'})")
        conn.execute("MATCH (l:Link {url: 'https://kuzudb.com'}), (c:Category {name: 'Database'}) MERGE (l)-[:BELONGS_TO]->(c)")
        conn.execute("MATCH (l:Link {url: 'https://example.com'}), (c:Category {name: 'Database'}) MERGE (l)-[:BELONGS_TO]->(c)")
        conn.execute("MATCH (l:Link {url: 'https://kuzudb.com'}), (k:Keyword {name: 'graph database'}) MERGE (l)-[:HAS_KEYWORD]->(k)")
        print("Kùzu database initialized with sample data")
except Exception as e:
    print(f"Error initializing Kùzu: {e}")
    raise

# Combine root and index routes to avoid endpoint conflict
@app.route("/", methods=["GET"])
@app.route("/index", methods=["GET"])
def index():
    try:
        result = conn.execute("MATCH (l:Link)-[:BELONGS_TO]->(c:Category) RETURN l.url, l.title, c.name, l.raw_category, l.suggested_category, l.raw_content, l.cleaned_content, l.keywords, l.category_explanation, l.keyword_explanation")
        links = [{
            "url": row[0],
            "title": row[1],
            "category": row[2],
            "raw_category": row[3],
            "suggested_category": row[4] if row[4] else 'None',
            "raw_content": row[5] if row[5] else 'Failed to fetch content',
            "cleaned_content": row[6] if row[6] else 'Failed to clean content',
            "keywords": row[7] if row[7] else 'none',
            "category_explanation": row[8] if row[8] else 'None',
            "keyword_explanation": row[9] if row[9] else 'None'
        } for row in result]
        print("Fetched links for index route")
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

# Other routes (unchanged from previous response)
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
        return content[:500]

def parse_category_and_keywords(response):
    categories = [
        'general tools', 'graph technologies', 'healthcare data', 'ai and legal systems',
        'federated search', 'organized crime analysis', 'beneficial ownership',
        'financial crime technology', 'corporate governance', 'power and utilities',
        'Social Media', 'Community Platform', 'Database', 'News', 'Blog', 'E-commerce',
        'International Economics/Policy', 'Data Analysis', 'Machine Learning / AI'
    ]
    category = 'Uncategorized'
    suggested_category = 'Uncategorized'
    keywords = ['none']
    if not response:
        return category, suggested_category, keywords
    match = re.search(r'Category:\s*([A-Za-z\s/]+)(?:\s*Keywords:|$)', response)
    if match:
        suggested_category = match.group(1).strip()
    for cat in categories:
        if cat.lower() == suggested_category.lower() or cat.lower() in response.lower():
            category = cat
            break
    match = re.search(r'Keywords:\s*([^.]+)', response)
    if match:
        keyword_str = match.group(1).strip()
        keywords = [k.strip() for k in keyword_str.split(',') if k.strip()][:3]
    if not keywords or keywords == ['none']:
        keywords = re.findall(r'\b[A-Z][a-zA-Z\s-]+\b', response)
        keywords = [k.strip() for k in keywords if len(k.split()) <= 2 and k.lower() not in category.lower() and k.lower() not in suggested_category.lower()][:3]
    return category, suggested_category, keywords if keywords else ['none']

def preload_metadata_csv():
    csv_path = "/app/links_with_metadata.csv"
    if not os.path.exists(csv_path):
        print("No links_with_metadata.csv found, skipping preload")
        return 0
    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            csv_reader = csv.DictReader(file)
            required_fields = ['url', 'title', 'content', 'category', 'keyword', 'category_explanation', 'keyword_explanation']
            if not all(field in csv_reader.fieldnames for field in required_fields):
                print(f"links_with_metadata.csv missing required columns: {required_fields}, skipping preload")
                return 0
            processed = 0
            for row in csv_reader:
                url = row['url'].strip()
                if not url:
                    print(f"Skipping empty URL in preload row {csv_reader.line_num}")
                    continue
                if not url.startswith(('http://', 'https://')):
                    url = 'https://' + url
                parsed_url = urllib.parse.urlparse(url)
                normalized_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}".rstrip('/')
                url = urllib.parse.quote(normalized_url, safe=':/?=&')
                result = conn.execute("MATCH (l:Link {url: $url}) RETURN l.url", {"url": url})
                if result.has_next():
                    print(f"Skipping existing link during preload row {csv_reader.line_num}: {url}")
                    continue
                title = row['title'].strip() if row['title'] else url
                raw_content = row['content'][:5000].strip() if row['content'] else ""
                cleaned_content = raw_content[:500]
                raw_category = row['category'].strip() if row['category'] else 'Uncategorized'
                suggested_category = raw_category
                category_explanation = row['category_explanation'].strip() if row['category_explanation'] else 'None'
                keyword_explanation = row['keyword_explanation'].strip() if row['keyword_explanation'] else 'None'
                keywords = [k.strip() for k in row['keyword'].split(',') if k.strip()][:3] if row['keyword'] else ['none']
                category, _, _ = parse_category_and_keywords(f"Category: {raw_category}")
                keywords_str = ', '.join(keywords) if keywords and keywords != ['none'] else 'none'
                conn.execute(
                    "MERGE (:Link {url: $url, title: $title, raw_category: $raw_category, suggested_category: $suggested_category, "
                    "raw_content: $raw_content, cleaned_content: $cleaned_content, keywords: $keywords, "
                    "category_explanation: $category_explanation, keyword_explanation: $keyword_explanation})",
                    {
                        "url": url,
                        "title": title,
                        "raw_category": raw_category,
                        "suggested_category": suggested_category,
                        "raw_content": raw_content,
                        "cleaned_content": cleaned_content,
                        "keywords": keywords_str,
                        "category_explanation": category_explanation,
                        "keyword_explanation": keyword_explanation
                    }
                )
                conn.execute("MERGE (c:Category {name: $name})", {"name": category})
                conn.execute(
                    "MATCH (l:Link {url: $url}), (c:Category {name: $name}) MERGE (l)-[:BELONGS_TO]->(c)",
                    {"url": url, "name": category}
                )
                for keyword in keywords:
                    if keyword != 'none':
                        conn.execute("MERGE (k:Keyword {name: $name})", {"name": keyword})
                        conn.execute(
                            "MATCH (l:Link {url: $url}), (k:Keyword {name: $name}) MERGE (l)-[:HAS_KEYWORD]->(k)",
                            {"url": url, "name": keyword}
                        )
                print(f"Preloaded link in row {csv_reader.line_num}: {url}, Title: {title}, Category: {category}, "
                      f"Suggested Category: {suggested_category}, Keywords: {keywords}")
                processed += 1
            print(f"Preloaded {processed} links from links_with_metadata.csv")
            return processed
    except Exception as e:
        print(f"Error preloading links_with_metadata.csv: {e}")
        flash(f"Error preloading CSV: {str(e)}")
        return 0

@app.route("/upload_csv", methods=["POST"])
def upload_csv():
    try:
        result = conn.execute("MATCH (l:Link) RETURN COUNT(l) AS cnt")
        print(f"Total links before CSV upload: {result.get_next()[0]}")
        if 'file' not in request.files:
            flash("No file uploaded")
            return redirect(url_for("index"))
        file = request.files['file']
        if not file.filename.endswith('.csv'):
            flash("File must be a CSV")
            return redirect(url_for("index"))
        batch_size = int(request.form.get('batch_size', 5))
        try:
            stream = io.StringIO(file.stream.read().decode("UTF-8"), newline=None)
        except UnicodeDecodeError as e:
            flash(f"Invalid CSV encoding, please use UTF-8: {str(e)}")
            return redirect(url_for("index"))
        csv_reader = csv.DictReader(stream)
        required_fields = ['url']
        metadata_fields = ['url', 'title', 'content', 'category', 'keyword', 'category_explanation', 'keyword_explanation']
        is_metadata_csv = all(field in csv_reader.fieldnames for field in metadata_fields)
        if not all(field in csv_reader.fieldnames for field in required_fields):
            flash("CSV must contain a 'url' column")
            return redirect(url_for("index"))
        processed = 0
        skipped = 0
        for row in csv_reader:
            if processed >= batch_size:
                break
            url = row['url'].strip()
            if not url:
                print(f"Skipping empty URL in row {csv_reader.line_num}")
                skipped += 1
                continue
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            parsed_url = urllib.parse.urlparse(url)
            normalized_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}".rstrip('/')
            url = urllib.parse.quote(normalized_url, safe=':/?=&')
            result = conn.execute("MATCH (l:Link {url: $url}) RETURN l.url", {"url": url})
            if result.has_next():
                print(f"Skipping duplicate link in row {csv_reader.line_num}: {url}")
                skipped += 1
                continue
            try:
                if is_metadata_csv:
                    title = row['title'].strip() if row['title'] else url
                    raw_content = row['content'][:5000].strip() if row['content'] else ""
                    cleaned_content = raw_content[:500]
                    raw_category = row['category'].strip() if row['category'] else 'Uncategorized'
                    suggested_category = raw_category
                    category_explanation = row['category_explanation'].strip() if row['category_explanation'] else 'None'
                    keyword_explanation = row['keyword_explanation'].strip() if row['keyword_explanation'] else 'None'
                    keywords = [k.strip() for k in row['keyword'].split(',') if k.strip()][:3] if row['keyword'] else ['none']
                    category, _, _ = parse_category_and_keywords(f"Category: {raw_category}")
                    keywords_str = ', '.join(keywords) if keywords and keywords != ['none'] else 'none'
                else:
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                    try:
                        response = requests.get(url, headers=headers, timeout=10)
                        response.raise_for_status()
                        soup = BeautifulSoup(response.text, 'html.parser')
                        title = soup.title.string.strip() if soup.title else url
                        text_elements = soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                        raw_content = ' '.join(element.get_text(strip=True) for element in text_elements)[:5000]
                    except requests.RequestException as e:
                        print(f"Failed to fetch title/content for {url} in row {csv_reader.line_num}: {e}")
                        title = url
                        raw_content = "Failed to fetch content"
                    ollama_host = os.getenv('OLLAMA_HOST', 'http://host.docker.internal:11434')
                    cleaned_content = clean_content_with_ollama(raw_content, ollama_host)
                    try:
                        client = Client(host=ollama_host, timeout=20)
                        content_for_prompt = cleaned_content if cleaned_content else raw_content[:1000]
                        prompt = (
                            f"Given the webpage title '{title}' and the following content excerpt: '{content_for_prompt[:1000]}', "
                            f"suggest a single category (e.g., Social Media, Database, News) and up to three keywords (1-2 words each)."
                        )
                        response = client.chat(model='mistral:7b-instruct-v0.3-q4_0', messages=[{'role': 'user', 'content': prompt}])
                        raw_category = response['message']['content'].strip()
                        category, suggested_category, keywords = parse_category_and_keywords(raw_category)
                        category_explanation = 'Generated by LLM'
                        keyword_explanation = 'Generated by LLM'
                        keywords_str = ', '.join(keywords) if keywords and keywords != ['none'] else 'none'
                    except Exception as e:
                        print(f"Failed to connect to Ollama for {url} in row {csv_reader.line_num}: {e}")
                        raw_category = 'Failed to connect to Ollama'
                        category = 'Uncategorized'
                        suggested_category = 'Uncategorized'
                        keywords = ['none']
                        keywords_str = 'none'
                        category_explanation = 'Ollama failure'
                        keyword_explanation = 'Ollama failure'
                        cleaned_content = raw_content[:500]
                conn.execute(
                    "MERGE (:Link {url: $url, title: $title, raw_category: $raw_category, suggested_category: $suggested_category, "
                    "raw_content: $raw_content, cleaned_content: $cleaned_content, keywords: $keywords, "
                    "category_explanation: $category_explanation, keyword_explanation: $keyword_explanation})",
                    {
                        "url": url,
                        "title": title,
                        "raw_category": raw_category,
                        "suggested_category": suggested_category,
                        "raw_content": raw_content,
                        "cleaned_content": cleaned_content,
                        "keywords": keywords_str,
                        "category_explanation": category_explanation,
                        "keyword_explanation": keyword_explanation
                    }
                )
                conn.execute("MERGE (c:Category {name: $name})", {"name": category})
                conn.execute(
                    "MATCH (l:Link {url: $url}), (c:Category {name: $name}) MERGE (l)-[:BELONGS_TO]->(c)",
                    {"url": url, "name": category}
                )
                for keyword in keywords:
                    if keyword != 'none':
                        conn.execute("MERGE (k:Keyword {name: $name})", {"name": keyword})
                        conn.execute(
                            "MATCH (l:Link {url: $url}), (k:Keyword {name: $name}) MERGE (l)-[:HAS_KEYWORD]->(k)",
                            {"url": url, "name": keyword}
                        )
                print(f"Added link in row {csv_reader.line_num}: {url}, Title: {title}, Category: {category}, "
                      f"Suggested Category: {suggested_category}, Keywords: {keywords}")
                processed += 1
            except Exception as e:
                print(f"Error processing row {csv_reader.line_num} for URL {url}: {e}")
                flash(f"Error processing row {csv_reader.line_num} for URL {url}: {str(e)}")
                skipped += 1
                continue
        result = conn.execute("MATCH (l:Link) RETURN COUNT(l) AS cnt")
        print(f"Total links after CSV upload: {result.get_next()[0]}")
        flash(f"Successfully processed {processed} links, skipped {skipped} duplicates or invalid entries")
        return redirect(url_for("index"))
    except Exception as e:
        print(f"Error processing CSV: {e}")
        flash(f"Error processing CSV: {str(e)}")
        return redirect(url_for("index"))

@app.route("/add_link", methods=["POST"])
def add_link():
    try:
        url = request.form["url"]
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        parsed_url = urllib.parse.urlparse(url)
        normalized_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}".rstrip('/')
        url = urllib.parse.quote(normalized_url, safe=':/?=&')
        result = conn.execute("MATCH (l:Link {url: $url}) RETURN l.url", {"url": url})
        if result.has_next():
            print(f"Skipping duplicate link: {url}")
            flash(f"Link already exists: {url}")
            return redirect(url_for("index"))
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
            content_for_prompt = cleaned_content if cleaned_content else content[:1000]
            prompt = (
                f"Given the webpage title '{title}' and the following content excerpt: '{content_for_prompt[:1000]}', "
                f"suggest a single category (e.g., Social Media, Database, News) and up to three keywords (1-2 words each)."
            )
            response = client.chat(model='mistral:7b-instruct-v0.3-q4_0', messages=[{'role': 'user', 'content': prompt}])
            raw_category = response['message']['content'].strip()
            category, suggested_category, keywords = parse_category_and_keywords(raw_category)
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
            suggested_category = 'Uncategorized'
            keywords = ['none']
            keywords_str = 'none'
            conn.execute("MERGE (c:Category {name: 'Uncategorized'})")
        conn.execute(
            "MERGE (:Link {url: $url, title: $title, raw_category: $raw_category, suggested_category: $suggested_category, "
            "raw_content: $raw_content, cleaned_content: $cleaned_content, keywords: $keywords})",
            {
                "url": url,
                "title": title,
                "raw_category": raw_category,
                "suggested_category": suggested_category,
                "raw_content": content,
                "cleaned_content": cleaned_content,
                "keywords": keywords_str
            }
        )
        conn.execute("MATCH (l:Link {url: $url}), (c:Category {name: $name}) MERGE (l)-[:BELONGS_TO]->(c)", {"url": url, "name": category})
        print(f"Added link: {url}, Title: {title}, Category: {category}, Suggested Category: {suggested_category}, Keywords: {keywords}")
        flash(f"Successfully added link: {url}")
        return redirect(url_for("index"))
    except Exception as e:
        print(f"Error adding link: {e}")
        flash(f"Error adding link: {str(e)}")
        return redirect(url_for("index"))

@app.route("/graph_data", methods=["GET"])
def graph_data():
    try:
        nodes = []
        result = conn.execute("MATCH (l:Link) WHERE l.title IS NOT NULL RETURN l.url, l.title")
        link_count = 0
        for row in result:
            nodes.append({"id": f"Link:{row[0]}", "label": row[1], "group": "Link"})
            link_count += 1
        print(f"Fetched {link_count} links for graph")
        
        result = conn.execute("MATCH (c:Category) WHERE c.name IS NOT NULL RETURN c.name")
        category_count = 0
        for row in result:
            nodes.append({"id": f"Category:{row[0]}", "label": row[0], "group": "Category"})
            category_count += 1
        print(f"Fetched {category_count} categories for graph")
        
        result = conn.execute("MATCH (k:Keyword) WHERE k.name IS NOT NULL RETURN k.name")
        keyword_count = 0
        for row in result:
            nodes.append({"id": f"Keyword:{row[0]}", "label": row[0], "group": "Keyword"})
            keyword_count += 1
        print(f"Fetched {keyword_count} keywords for graph")
        
        edges = []
        result = conn.execute("MATCH (l:Link)-[:BELONGS_TO]->(c:Category) WHERE l.url IS NOT NULL AND c.name IS NOT NULL RETURN l.url, c.name")
        belongs_to_count = 0
        for row in result:
            edges.append({"from": f"Link:{row[0]}", "to": f"Category:{row[1]}"})
            belongs_to_count += 1
        print(f"Fetched {belongs_to_count} BELONGS_TO edges for graph")
        
        result = conn.execute("MATCH (l:Link)-[:HAS_KEYWORD]->(k:Keyword) WHERE l.url IS NOT NULL AND k.name IS NOT NULL RETURN l.url, k.name")
        has_keyword_count = 0
        for row in result:
            edges.append({"from": f"Link:{row[0]}", "to": f"Keyword:{row[1]}"})
            has_keyword_count += 1
        print(f"Fetched {has_keyword_count} HAS_KEYWORD edges for graph")
        
        # Log all nodes to check for duplicates
        node_ids = [node['id'] for node in nodes]
        print(f"Node IDs: {node_ids}")
        if len(node_ids) != len(set(node_ids)):
            print(f"Warning: Duplicate node IDs detected: {set([x for x in node_ids if node_ids.count(x) > 1])}")
        
        print(f"Graph data: {len(nodes)} nodes, {len(edges)} edges")
        return jsonify({"nodes": nodes, "edges": edges})
    except Exception as e:
        print(f"Error fetching graph data: {e}")
        return jsonify({"nodes": [], "edges": [], "error": str(e)}), 200



@app.route("/delete_link", methods=["POST"])
def delete_link():
    try:
        url = request.form["url"]
        conn.execute("MATCH (l:Link {url: $url}) DETACH DELETE l", {"url": url})
        print(f"Deleted link: {url}")
        flash(f"Successfully deleted link: {url}")
        return redirect(url_for("index"))
    except Exception as e:
        print(f"Error deleting link: {e}")
        flash(f"Error deleting link: {str(e)}")
        return redirect(url_for("index"))

if __name__ == "__main__":
    print("Starting Flask server")
    preload_metadata_csv()
    app.run(host="0.0.0.0", port=5000, debug=False)