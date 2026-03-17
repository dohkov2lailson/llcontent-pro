import os
import re
import json
import base64
import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

app = FastAPI()

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CATARINA_SYSTEM = """Você é a Catarina, gerente de marketing do LL Squad — equipe de personal trainers liderada pelo Lailson Lima, dono da academia Inove Fit em Campos dos Goytacazes/RJ.

Você é especialista em criação de conteúdo para Instagram. Também cria conteúdo para outras marcas quando recebe a identidade visual.

Regras por formato:

POST SIMPLES:
- Título curto e chamativo
- Texto principal curto e escaneável
- Sugestão visual para a imagem do post
- Prompt detalhado para gerar a imagem em IA (em inglês, formato vertical 4:5, sem texto na imagem). IMPORTANTE: coloque o prompt entre as tags [IMG_PROMPT] e [/IMG_PROMPT] para facilitar a extração.
- Legenda otimizada para Instagram
- Entre 5 e 8 hashtags relevantes

CARROSSEL (6 a 8 slides):
- Para cada slide: Título, Texto curto, Sugestão visual, Prompt para imagem (em inglês)
- Coloque cada prompt de imagem entre [IMG_PROMPT] e [/IMG_PROMPT]
- Slide 1 = capa com forte curiosidade
- Demais slides: infográficos, ícones, diagramas, elementos educativos

REELS:
- Gancho inicial forte (primeiros 3 segundos)
- Explicação em 3 ou 4 pontos
- Fechamento com call to action
- Sugestão visual das cenas (com prompt entre [IMG_PROMPT] e [/IMG_PROMPT])
- Legenda
- Hashtags

Regras gerais:
- Sempre responda em português do Brasil
- Seja criativa, linguagem conectada ao público-alvo da marca
- Tom: profissional mas descontraído, motivacional sem ser clichê
- Foque em storytelling e ativação de desejo através de dores
- Prompts de imagem SEMPRE em inglês, SEMPRE entre [IMG_PROMPT] e [/IMG_PROMPT]
- Nunca inclua texto/tipografia dentro das imagens nos prompts"""

# Models to try in order (Gemini image generation)
GEMINI_IMAGE_MODELS = [
    "gemini-2.0-flash-preview-image-generation",
    "gemini-2.0-flash-exp-image-generation",
    "gemini-2.5-flash-preview-04-17",
]


@app.post("/api/generate")
async def generate_content(request: Request):
    try:
        body = await request.json()
        tema = body.get("tema", "")
        formato = body.get("formato", "Post")
        brand_text = body.get("brand_text", "")

        system = CATARINA_SYSTEM
        if brand_text:
            system += f"\n\nIDENTIDADE DA MARCA:\n{brand_text}"

        user_msg = f'Tema: "{tema}"\nFormato: {formato}\n\nGere o conteúdo completo.'

        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 4000,
                "system": system,
                "messages": [{"role": "user", "content": user_msg}]
            },
            timeout=120
        )

        if resp.status_code != 200:
            err = resp.json().get("error", {}).get("message", resp.text[:300])
            return JSONResponse({"error": err}, status_code=resp.status_code)

        data = resp.json()
        text = "\n".join(b["text"] for b in data.get("content", []) if b.get("type") == "text")

        img_prompts = re.findall(r'\[IMG_PROMPT\](.*?)\[/IMG_PROMPT\]', text, re.DOTALL)
        img_prompts = [m.strip() for m in img_prompts]

        return JSONResponse({"text": text, "image_prompts": img_prompts})

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/image")
async def generate_image(request: Request):
    try:
        body = await request.json()
        prompt = body.get("prompt", "")

        if not prompt:
            return JSONResponse({"error": "Prompt vazio"}, status_code=400)

        # Try each Gemini image model until one works
        last_error = ""
        for model in GEMINI_IMAGE_MODELS:
            try:
                resp = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}",
                    headers={"Content-Type": "application/json"},
                    json={
                        "contents": [{"parts": [{"text": f"Generate this image: {prompt}"}]}],
                        "generationConfig": {
                            "responseModalities": ["TEXT", "IMAGE"]
                        }
                    },
                    timeout=120
                )

                if resp.status_code != 200:
                    last_error = f"{model}: {resp.status_code}"
                    continue

                data = resp.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    last_error = f"{model}: sem candidatos"
                    continue

                parts = candidates[0].get("content", {}).get("parts", [])
                for part in parts:
                    if "inlineData" in part:
                        img_data = part["inlineData"]
                        return JSONResponse({
                            "image": img_data["data"],
                            "mime": img_data.get("mimeType", "image/png"),
                            "model_used": model
                        })

                last_error = f"{model}: resposta sem imagem"
                continue

            except Exception as e:
                last_error = f"{model}: {str(e)}"
                continue

        # All Gemini models failed, try Imagen as last resort
        try:
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={GEMINI_KEY}",
                headers={"Content-Type": "application/json"},
                json={
                    "instances": [{"prompt": prompt}],
                    "parameters": {
                        "sampleCount": 1,
                        "aspectRatio": "4:5",
                        "personGeneration": "allow_all"
                    }
                },
                timeout=120
            )

            if resp.status_code == 200:
                data = resp.json()
                predictions = data.get("predictions", [])
                if predictions and "bytesBase64Encoded" in predictions[0]:
                    return JSONResponse({
                        "image": predictions[0]["bytesBase64Encoded"],
                        "mime": "image/png",
                        "model_used": "imagen-3.0"
                    })
        except Exception:
            pass

        return JSONResponse({"error": f"Nenhum modelo disponível. Último erro: {last_error}"}, status_code=500)

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# Debug endpoint - list available models
@app.get("/api/models")
async def list_models():
    try:
        resp = requests.get(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_KEY}",
            timeout=30
        )
        if resp.status_code != 200:
            return JSONResponse({"error": resp.text[:300]}, status_code=resp.status_code)

        data = resp.json()
        image_models = []
        for m in data.get("models", []):
            name = m.get("name", "")
            methods = m.get("supportedGenerationMethods", [])
            if "generateContent" in methods:
                image_models.append({
                    "name": name,
                    "displayName": m.get("displayName", ""),
                    "methods": methods
                })

        return JSONResponse({"models": image_models, "total": len(image_models)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/health")
async def health():
    return {"status": "ok", "anthropic": bool(ANTHROPIC_KEY), "gemini": bool(GEMINI_KEY)}


@app.get("/")
async def index():
    html_path = os.path.join(BASE_DIR, "index.html")
    if os.path.exists(html_path):
        return FileResponse(html_path, media_type="text/html")
    return HTMLResponse("<h1>index.html not found</h1>", status_code=404)
