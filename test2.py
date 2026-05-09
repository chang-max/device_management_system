x = {"1":{"DT":"2023-01-01","EleInfo":"123","tEc":"456"}}
y = x.get("1")
z = y.get("a")
m = z.get("DT")
print(m)
print(z)
