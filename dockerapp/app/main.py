from flask import Flask, render_template, request, redirect, url_for
import kuzu
import os
import requests
from bs4 import BeautifulSoup
import urllib.parse

app = Flask(__name__, template_folder='templates')

# Initialize Kùzu database
db_path = "/app/db/kuzu.db"
try:
    db = kuzu.Database(db_path)
    conn = kuzu.Connection(db)
    conn.execute("CREATE NODE TABLE Link (url STRING, title STRING, PRIMARY KEY (url))")
    conn.execute("CREATE NODE TABLE Category (name STRING, PRIMARY KEY (name))")
    conn.execute("CREATE REL TABLE BELONGS_TO (FROM Link TO Category)")
    result = conn.execute("MATCH (l:Link) RETURN COUNT(l) AS cnt")
    count = result.get_next()[0]
    if count == 0:
        conn.execute("CREATE (:Link {url: 'https://kuzudb.com', title: 'Kùzu Database'})")
        conn.execute("CREATE (:Link {url: 'https://example.com', title: 'Example Site'})")
        conn.execute("CREATE (:Category {name: 'Database'})")
        conn.execute(
            """
            MATCH (l:Link {url: 'https://kuzudb.com'}), (c:Category {name: 'Database'})
            CREATE (l)-[:BELONGS_TO]->(c)
            """
        )
        conn.execute(
            """
            MATCH (l:Link {url: 'https://example.com'}), (c:Category {name: 'Database'})
            CREATE (l)-[:BELONGS_TO]->(c)
            """
        )
        print("Kùzu database initialized with sample data")
except Exception as e:
    print(f"Error initializing Kùzu: {e}")

@app.route("/", methods=["GET"])
def index():
    try:
        result = conn.execute("MATCH (l:Link)-[:BELONGS_TO]->(c:Category) RETURN l.url, l.title, c.name")
        links = [{"url": row[0], "title": row[1], "category": row[2]} for row in result]
        return render_template("index.html", links=links)
    except Exception as e:
        print(f"Error fetching links: {e}")
        return f"Error: {str(e)}", 500

@app.route("/add_link", methods=["POST"])
def add_link():
    try:
        url = request.form["url"]
        # Basic URL sanitization
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        url = urllib.parse.quote(url, safe=':/?=&')
        # Fetch webpage title
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            title = soup.title.string.strip() if soup.title else url
        except requests.RequestException as e:
            print(f"Failed to fetch title for {url}: {e}")
            title = url  # Fallback to URL if fetching fails
        # Insert link and connect to default category
        # Use parameter binding to prevent SQL injection
        conn.execute("CREATE (:Link {url: $url, title: $title})", {"url": url, "title": title})
        conn.execute(
            """
            MATCH (l:Link {url: $url}), (c:Category {name: 'Database'})
            CREATE (l)-[:BELONGS_TO]->(c)
            """,
            {"url": url}
        )
        print(f"Added link: {url}, Title: {title}")
        return redirect(url_for("index"))
    except Exception as e:
        print(f"Error adding link: {e}")
        return f"Error: {str(e)}", 500

if __name__ == "__main__":
    print("Starting Flask server")
    app.run(host="0.0.0.0", port=5000)