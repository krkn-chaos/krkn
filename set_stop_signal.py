import http.client as cli

conn = cli.HTTPConnection("0.0.0.0", "<port>")

conn.request("POST", "/STOP", {})

# conn.request('POST', '/PAUSE', {})

# conn.request('POST', '/RUN', {})

response = conn.getresponse()
print(response.read().decode())
