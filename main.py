# main.py
"""Entry point for the Idle Obelisk Miner Bot - Web Dashboard Version.

Starts the Flask/SocketIO web server which launches the bot in a background thread.
Open http://localhost:6001 in your browser to control the bot.
"""
import sys
import os

# Ensure the project root is in the Python path and is the working directory
_project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _project_root)
os.chdir(_project_root)


def main():
    port = 6001

    # Allow port override via command line: python main.py 7000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass

    from web.app import run_server
    run_server(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
