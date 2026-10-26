import threading
import webbrowser

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = 5000
    url = f"http://127.0.0.1:{port}"
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    app.run(debug=False, port=port)