import json
import yaml
from pathlib import Path
from app.services.openapi_loader import load_provider_openapi

def test_openapi_json_matches_yaml():
    """
    Assert that the JSON returned by the API is byte-for-byte identical 
    to the YAML spec when both are normalized to JSON.
    """
    spec_path = Path(__file__).resolve().parents[2] / "scraper-api-spec.yaml"
    
    with spec_path.open("r", encoding="utf-8") as f:
        yaml_data = yaml.safe_load(f)
    
    json_data = load_provider_openapi()
    
    # Normalize by converting to JSON string and back
    yaml_json = json.loads(json.dumps(yaml_data, sort_keys=True))
    json_normalized = json.loads(json.dumps(json_data, sort_keys=True))
    
    assert yaml_json == json_normalized
