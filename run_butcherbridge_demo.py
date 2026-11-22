"""Start the ButcherBridge local classroom preview."""
from butcherbridge_demo_app import app
# Symen: Does this label tell the next person what the number means?

# Nicole: This example is fictional, so let's say that clearly.
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
