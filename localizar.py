from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
import mysql.connector
import random
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://medlocator-six.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def conectar_mysql():
    return mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST"),
        port=int(os.environ.get("MYSQL_PORT", 3306)),
        user=os.environ.get("MYSQL_USER"),
        password=os.environ.get("MYSQL_PASSWORD"),
        database=os.environ.get("MYSQL_DATABASE")
    )

def usuario_eh_premium(usuario_id):
    if not usuario_id:
        return False
    conn = conectar_mysql()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT premium FROM usuarios WHERE id = %s", (usuario_id,))
    row = cursor.fetchone()
    conn.close()
    return row and row.get("premium") == 1

def buscar_medicamentos(premium=False):
    conn = conectar_mysql()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT nome, tipo_medicamento, quantidade FROM medicamentos")
    todos = cursor.fetchall()

    if not premium:
        # Seleciona uma quantidade aleatória de vacinas (tipo 20)
        vacinas = [m for m in todos if m['tipo_medicamento'] == 20]
        n_vacinas = random.randint(1, len(vacinas)) if vacinas else 0
        selecionados = random.sample(vacinas, n_vacinas) if n_vacinas else []
        conn.close()
        return selecionados

    tipo_20 = [m for m in todos if m['tipo_medicamento'] == 20]
    outros = [m for m in todos if m['tipo_medicamento'] != 20]

    if not tipo_20:
        tipo_20_escolhido = []
    else:
        tipo_20_escolhido = [random.choice(tipo_20)]

    n_outros = random.randint(0, 9)
    outros_escolhidos = random.sample(outros, min(n_outros, len(outros)))

    selecionados = tipo_20_escolhido + outros_escolhidos
    random.shuffle(selecionados)

    conn.close()
    return selecionados

def buscar_postos_osm(lat, lon, premium=False, raio_m=2000):
    overpass_url = "http://overpass-api.de/api/interpreter"
    query = f"""
    [out:json];
    (
      node["amenity"="hospital"](around:{raio_m},{lat},{lon});
      way["amenity"="hospital"](around:{raio_m},{lat},{lon});
      relation["amenity"="hospital"](around:{raio_m},{lat},{lon});
      
      node["amenity"="clinic"](around:{raio_m},{lat},{lon});
      way["amenity"="clinic"](around:{raio_m},{lat},{lon});
      relation["amenity"="clinic"](around:{raio_m},{lat},{lon});

      node["healthcare"="hospital"](around:{raio_m},{lat},{lon});
      way["healthcare"="hospital"](around:{raio_m},{lat},{lon});
      relation["healthcare"="hospital"](around:{raio_m},{lat},{lon});

      node["healthcare"="clinic"](around:{raio_m},{lat},{lon});
      way["healthcare"="clinic"](around:{raio_m},{lat},{lon});
      relation["healthcare"="clinic"](around:{raio_m},{lat},{lon});
    );
    out center;
    """

    response = requests.post(overpass_url, data={"data": query})
    dados = response.json()

    postos = []

    for el in dados.get("elements", []):
        nome = el["tags"].get("name", "UBS sem nome")

        if "lat" in el and "lon" in el:
            lat_post = el["lat"]
            lon_post = el["lon"]
        elif "center" in el:
            lat_post = el["center"]["lat"]
            lon_post = el["center"]["lon"]
        else:
            continue

        medicamentos = buscar_medicamentos(premium=premium)

        postos.append({
            "nome": nome,
            "lat": lat_post,
            "lon": lon_post,
            "medicamentos": medicamentos
        })

    return postos

@app.get("/")
def root():
    return {"mensagem": "API FastAPI rodando! Veja /docs para documentação."}

@app.get("/postos_proximos")
async def postos(lat: float, lon: float, usuario_id: int = None):
    try:
        premium = usuario_eh_premium(usuario_id)
        resultados = buscar_postos_osm(lat, lon, premium=premium)
        print(f"Total encontrados: {len(resultados)}")
        for p in resultados:
            print(p)
        return JSONResponse(content=resultados)
    except Exception as e:
        print("Erro:", e)
        return JSONResponse(content={"erro": str(e)}, status_code=500)

@app.get("/geocode_cep")
def geocode_cep(cep: str):
    viacep = requests.get(f"https://viacep.com.br/ws/{cep}/json/").json()
    if "erro" in viacep:
        return {"erro": "CEP não encontrado"}
    logradouro = viacep.get("logradouro", "")

    endereco = f"{logradouro}"
    response = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": endereco, "format": "json"},
        headers={"User-Agent": "MeuApp/1.0 (meu.email@exemplo.com)"}
    )
    try:
        nominatim = response.json()
    except Exception:
        return {"erro": "Resposta inválida do servidor de geocodificação"}

    if not nominatim:
        return {"erro": "Não foi possível geocodificar o CEP"}

    lat = nominatim[0]["lat"]
    lon = nominatim[0]["lon"]
    return {"lat": lat, "lon": lon}