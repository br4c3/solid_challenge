from backend.app import create_app
from backend.config import load_config

app = create_app()

if __name__ == "__main__":
    server = load_config().server
    app.run(host=server.host, port=server.port, debug=server.debug)
