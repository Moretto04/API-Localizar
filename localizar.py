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
    allow_origins=["*"],  #allow_origins=["https://seu-projeto.vercel.app"]
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
    

def buscar_medicamentos():
    conn = conectar_mysql()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT nome, tipo_medicamento, quantidade FROM medicamentos")
    todos = cursor.fetchall()

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



# Raio grande o suficiente para buscar vários estabelecimentos (~2 km)
def buscar_postos_osm(lat, lon, raio_m=2000):
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

        medicamentos = buscar_medicamentos()  

        postos.append({
            "nome": nome,
            "lat": lat_post,
            "lon": lon_post,
            "medicamentos": medicamentos
        })

    return postos

# @app.get("/", response_class=HTMLResponse)
# async def home(request: Request):
#     return templates.TemplateResponse("index.html", {"request": request})

@app.get("/postos_proximos")
async def postos(lat: float, lon: float):
    try:
        resultados = buscar_postos_osm(lat, lon)
        print(f"Total encontrados: {len(resultados)}")
        for p in resultados:
            print(p)
        return JSONResponse(content=resultados)
    except Exception as e:
        print("Erro:", e)
        return JSONResponse(content={"erro": str(e)}, status_code=500)

@app.get("/geocode_cep")
def geocode_cep(cep: str):
    # 1. Busca endereço pelo CEP (ViaCEP)
    viacep = requests.get(f"https://viacep.com.br/ws/{cep}/json/").json()
    if "erro" in viacep:
        return {"erro": "CEP não encontrado"}
    logradouro = viacep.get("logradouro", "")
    # bairro = viacep.get("bairro", "")
    # localidade = viacep.get("localidade", "")
    # uf = viacep.get("uf", "")

    # 2. Usa Nominatim para geocodificar o endereço com User-Agent
    endereco = f"{logradouro}" # {bairro}, {localidade}, {uf}, Brasil
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




