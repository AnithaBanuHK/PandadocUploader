import requests
import json
 
url = "https://api.pandadoc.com/public/v1/documents"
 
headers = {
    "Authorization": "API-Key 67146d9c47d3b282e63b2abd0f3611183a0e7752"
}
 
payload = {
    "name": "receipt",
    "recipients": [
        {
            "email": "anithabanu2021@gmail.com",
            "first_name": "Anitha",
            "last_name": "Banu",
            "role": "Signer"
        }
    ]
}
 
file_path = "Narayan NDA.pdf"
 
files = {
    "file": (
        "Narayan NDA.pdf",
        open(file_path, "rb"),
        "application/pdf"
    ),
    "data": (None, json.dumps(payload), "application/json")
}
 
 
response = requests.post(url, headers=headers, files=files)
print(response.status_code)
print(response.text)
 