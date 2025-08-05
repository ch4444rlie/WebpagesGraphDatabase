# Brad's Webpage Graph Database

## Setup
1. Install Docker: https://docs.docker.com/get-docker/
2. Install Ollama: https://ollama.com/
3. Run Ollama locally:
   ```bash
   ollama pull mistral:7b-instruct-v0.3-q4_0
   ollama run mistral:7b-instruct-v0.3-q4_0



   
### How It Works
1. **User Runs Docker Container**:
   - Commands:
     ```bash
     docker build -t kuzu-webapp .
     docker run -p 5000:5000 -v $(pwd)/db:/app/db kuzu-webapp
     ```
   - The Flask server starts, and the app is accessible at `http://localhost:5000`.

2. **User Interaction**:
   - **Access**: Open `http://localhost:5000` in a browser.
   - **Interface**: See a form with a single URL input, a table of existing links, and a graph visualization.
   - **Add Link**:
     - Enter a URL (e.g., `https://example.com`) and submit.
     - The backend (`/add_link`):
       - Fetches webpage content using `requests` and `BeautifulSoup`.
       - Calls Ollama (`http://host.docker.internal:11434`) to generate metadata.
       - Stores the URL, title, category, keywords, and explanations in the Kùzu database.
       - Creates `Link`, `Category`, and `Keyword` nodes and `BELONGS_TO`/`HAS_KEYWORD` relationships.
     - The browser shows a success message with the generated metadata and refreshes.
   - **View Results**:
     - The table updates with the new link’s details (URL, title, category, keywords).
     - The graph updates to show the new `Link` node connected to its `Category` and `Keyword` nodes.

3. **File Interactions**:
   - **Dockerfile**: Builds the image with all dependencies and runs `main.py`.
   - **main.py**: Initializes Kùzu, serves the frontend, and handles API requests. The `/add_link` endpoint now includes metadata generation.
   - **index.html**: Provides a simple form for URL input, displays the table (`/get_links`), and renders the graph (`/get_graph`) using `vis.js`.
   - **style.css**: Styles the frontend.
   - **db/**: Stores the persistent Kùzu database.

### User Experience
- **Setup**:
  - Install Docker and Ollama.
  - Pull and run the Ollama model (`mistral:7b-instruct-v0.3-q4_0`).
  - Build and run the Docker container.
- **Usage**:
  - Open `http://localhost:5000`.
  - Enter a URL (e.g., `https://kuzudb.com`).
  - Submit, and the app:
    - Fetches the webpage content.
    - Generates metadata (e.g., category: “graph technologies”, keywords: “graph database, knowledge graph”).
    - Adds it to the Kùzu database.
    - Updates the table and graph.
- **Visualization**:
  - The graph shows `Link` nodes (blue rectangles), `Category` nodes (green ellipses), and `Keyword` nodes (orange triangles) connected by `BELONGS_TO` (yellow) and `HAS_KEYWORD` (purple) edges.
  - Users can drag, zoom, and pan the graph (with `vis.js`).

### Addressing the `pypdfium2` Warning
The warning about `pypdfium2==4.30.1` being yanked was addressed by pinning `pypdfium2>=4.30.2` in `requirements.txt`. This ensures a non-yanked version is used. Since your app doesn’t process PDFs, `pypdfium2` is likely an indirect dependency (e.g., via `pandas` or another library). If issues arise:
- Run `pip show pypdfium2` to check which package depends on it.
- Test the app to confirm no PDF-related functionality is affected.
- If unnecessary, you can try excluding `pypdfium2` by locking dependencies with Poetry (`poetry lock --no-update`) or specifying exact versions in `requirements.txt`.

### Notes on yFiles
- The code uses `vis.js` for simplicity (no licensing, easy web integration via CDN). To use yFiles:
  - Obtain a yFiles license and include the yFiles web library in `index.html`.
  - Modify the `/get_graph` endpoint to format data for yFiles (consult yFiles documentation).
  - Update the JavaScript in `index.html` to render the graph with yFiles instead of `vis.js`.
- Example yFiles snippet (requires setup):
  ```html
  <script src="path/to/yfiles.js"></script>
  <script>
    fetch('/get_graph').then(response => response.json()).then(data => {
      // yFiles rendering code here
    });
  </script>