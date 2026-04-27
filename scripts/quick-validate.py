import yaml
import sys

try:
    with open("/vercel/share/v0-project/scraper-api-spec.yaml") as f:
        spec = yaml.safe_load(f)
    print("Valid YAML")
    print(f"Title: {spec['info']['title']}")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
