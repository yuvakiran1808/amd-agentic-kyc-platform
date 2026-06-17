import json
import time
import base64
import requests
from PIL import Image
import io

def encode_image_to_base64(image_path, max_size=1024):
    """Resizes and converts local images into a format the vLLM server can read."""
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        img.thumbnail((max_size, max_size))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG")
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
        
class KYCBaseAgent:
    def __init__(self, name: str, system_instructions: str, is_vision: bool = False):
        self.name = name
        self.system_instructions = system_instructions
        self.is_vision = is_vision
        self.vllm_endpoint = "http://localhost:8000/v1/chat/completions"
        self.model_id = "Qwen/Qwen2.5-VL-7B-Instruct"

    def run(self, payload: dict) -> dict:
        start_time = time.time()
        
        if self.is_vision:
            image_path = payload.get("image_path")
            base64_img = encode_image_to_base64(image_path)
            
            messages = [
                {"role": "system", "content": self.system_instructions},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract the data from this document exactly as instructed."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
                    ]
                }
            ]
        else:
            context_data = payload.get("context_data")
            messages = [
                {"role": "system", "content": self.system_instructions},
                {"role": "user", "content": f"Input Data: {json.dumps(context_data)}"}
            ]

        api_payload = {
            "model": self.model_id,
            "messages": messages,
            "max_tokens": 256,
            "temperature": 0.0,
            "repetition_penalty": 1.1, 
            "presence_penalty": 0.5,
            "stop": ["```"],
            "response_format": {
                 "type": "json_object"
           }

        }

        response = None
        try:
            response = requests.post(self.vllm_endpoint, json=api_payload)
            response.raise_for_status()
            
            response_data = response.json()
            response_text = response_data["choices"][0]["message"]["content"]
            
        except Exception as e:
            print(f"vLLM API Error: {e}")
            if response is not None:
                print(f"EXACT SERVER REASON: {response.text}")
            response_text = '{"error": "vLLM server failed."}'
            
        return {"agent_name": self.name, "latency_sec": round(time.time() - start_time, 2), "output": response_text.strip()}