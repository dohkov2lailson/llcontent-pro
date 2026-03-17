import os
import re
import time
import json
import base64
import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

app = FastAPI()

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SYSTEM_PROMPT = """Você é a Catarina, uma especialista em criação de conteúdo para Instagram. Você gera material profissional e de alto engajamento, personalizado para qualquer marca ou profissional.

REGRA FUNDAMENTAL: Você cria conteúdo baseado EXCLUSIVAMENTE na identidade de marca que o usuário forneceu. NUNCA invente nomes de empresa, hashtags de marca, slogans ou informações que o usuário não tenha fornecido.

Regras por formato:

POST SIMPLES:
- Título curto e chamativo
- Texto principal curto e escaneável
- Sugestão visual para a imagem do post
- Prompt detalhado para gerar a imagem em IA (em inglês, formato vertical 4:5, sem texto na imagem). Coloque o prompt entre as tags [IMG_PROMPT] e [/IMG_PROMPT]
- Legenda otimizada para Instagram
- Entre 5 e 8 hashtags relevantes (APENAS hashtags genéricas do nicho. Inclua hashtags da marca SOMENTE se o usuário as informou explicitamente)

CARROSSEL (6 a 8 slides):
- Para cada slide: Título, Texto curto, Sugestão visual, Prompt para imagem (em inglês entre [IMG_PROMPT] e [/IMG_PROMPT])
- Slide 1 = capa com forte curiosidade
- Demais slides: infográficos, ícones, diagramas, elementos educativos

REELS:
- Gancho inicial forte (primeiros 3 segundos)
- Explicação em 3 ou 4 pontos
- Fechamento com call to action
- Sugestão visual das cenas (com prompt entre [IMG_PROMPT] e [/IMG_PROMPT])
- Legenda
- Hashtags

REGRAS DE OURO:
- Sempre responda em português do Brasil
- Adapte tom de voz, linguagem e estilo 100% ao que o usuário definiu na identidade de marca
- Se o usuário NÃO forneceu identidade de marca, use tom neutro e profissional
- NUNCA invente hashtags com nomes de marcas, empresas ou pessoas que o usuário não mencionou
- NUNCA faça referência a marcas, academias, empresas ou pessoas específicas que não estejam na identidade de marca fornecida
- Prompts de imagem SEMPRE em inglês, SEMPRE entre [IMG_PROMPT] e [/IMG_PROMPT]
- Nunca inclua texto/tipografia dentro das imagens nos prompts
- Seja criativa, foque em storytelling e ativação de desejo
- Evite clichês — busque ângulos únicos e diferenciados"""


@app.post("/api/generate")
async def generate_content(request: Request):
    try:
        body = await request.json()
        tema = body.get("tema", "")
        formato = body.get("formato", "Post")
        brand_text = body.get("brand_text", "")

        system = SYSTEM_PROMPT
        if brand_text:
            system += f"\n\n--- IDENTIDADE DE MARCA DO USUÁRIO ---\n{brand_text}\n--- FIM DA IDENTIDADE ---\nUse SOMENTE as informações acima para personalizar o conteúdo. Não invente dados adicionais."

        user_msg = f'Tema: "{tema}"\nFormato: {formato}\n\nGere o conteúdo completo seguindo as regras.'

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

        model = "gemini-2.5-flash-image"
        max_retries = 3

        for attempt in range(max_retries):
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": f"Generate an image: {prompt}\n\nIMPORTANT: All text, words, letters, and typography that appear inside the image MUST be written in Brazilian Portuguese (pt-BR). Never use English text in the image."}]}],
                    "generationConfig": {
                        "responseModalities": ["TEXT", "IMAGE"]
                    }
                },
                timeout=120
            )

            if resp.status_code == 429:
                wait = (attempt + 1) * 15
                if attempt < max_retries - 1:
                    time.sleep(wait)
                    continue
                else:
                    return JSONResponse({"error": "Limite de requisições. Aguarde 1 minuto e tente novamente."}, status_code=429)

            if resp.status_code != 200:
                error_detail = ""
                try:
                    error_detail = resp.json().get("error", {}).get("message", "")
                except:
                    error_detail = resp.text[:200]
                return JSONResponse({"error": f"Erro ({resp.status_code}): {error_detail}"}, status_code=500)

            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return JSONResponse({"error": "Resposta vazia"}, status_code=500)

            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                if "inlineData" in part:
                    img_data = part["inlineData"]
                    return JSONResponse({
                        "image": img_data["data"],
                        "mime": img_data.get("mimeType", "image/png"),
                        "model_used": model
                    })

            return JSONResponse({"error": "Resposta sem imagem. Tente um prompt diferente."}, status_code=500)

        return JSONResponse({"error": "Falha após tentativas"}, status_code=500)

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


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
        models = [{"name": m.get("name", ""), "displayName": m.get("displayName", "")} for m in data.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
        return JSONResponse({"models": models, "total": len(models)})
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
