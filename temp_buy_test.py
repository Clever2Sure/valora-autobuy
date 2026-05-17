import requests
import json
import time

BASE = 'http://localhost:8001'
username = 'test_link_' + str(int(time.time()))
resp = requests.post(f'{BASE}/register', json={'username': username, 'password': 'test'})
print('register', resp.status_code)
print(resp.text)

token = resp.json()['token']
resp = requests.post(
    f'{BASE}/buy',
    headers={'Authorization': f'Bearer {token}'},
    json={'query': 'laptop 500 to 600', 'budget': 600, 'search_online': True}
)
print('buy status', resp.status_code)
print(json.dumps(resp.json(), indent=2)[:4000])
print('purchase_token', resp.json().get('product', {}).get('purchase_token'))
print('url in product', resp.json().get('product', {}).get('url'))
