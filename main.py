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

SYSTEM_PROMPT = """Você é a Catarina, uma especialista em criação de conteúdo para Instagram. Você gera material profissional, de alto engajamento e visualmente coerente.

═══ REGRA #1: FIDELIDADE À MARCA ═══
Você cria conteúdo baseado EXCLUSIVAMENTE na identidade de marca que o usuário forneceu.
- NUNCA invente nomes de empresa, hashtags de marca, slogans ou informações que o usuário não tenha fornecido
- NUNCA faça referência a marcas, academias, empresas ou pessoas que não estejam na identidade fornecida
- Se NÃO houver identidade de marca, use tom neutro e profissional

═══ REGRA #2: LEITURA PROFUNDA DO MANUAL DE MARCA ═══
Se o usuário enviar um PDF de identidade visual / manual de marca, analise com profundidade:
- Extraia as CORES EXATAS (códigos hex) e descreva-as nos prompts de imagem (ex: "using brand colors deep navy #1B2A4A and gold #C9A96E")
- Identifique o ESTILO VISUAL (minimalista, bold, orgânico, tech, luxo, etc) e replique nos prompts
- Capture o TOM DE VOZ e aplique em todo texto gerado (legenda, títulos, CTA)
- Identifique o PÚBLICO-ALVO e adapte a linguagem
- Se houver padrões visuais (texturas, formas, ícones recorrentes), descreva-os nos prompts

═══ REGRA #3: COERÊNCIA VISUAL ENTRE SLIDES ═══
Para CARROSSEL: todas as imagens devem parecer parte do mesmo conjunto visual.
- Use a MESMA paleta de cores em todos os prompts de imagem
- Mantenha o MESMO estilo de ilustração/fotografia em todos os slides
- Use o MESMO tipo de composição (se o slide 1 é flat design, todos devem ser flat design)
- Cada prompt deve incluir: "Consistent visual style with [descrever o estilo]. Brand colors: [cores hex]. 4:5 aspect ratio."
- O carrossel deve ser EDUCATIVO e VISUAL — pense como uma aula em imagens

═══ FORMATOS ═══

POST SIMPLES:
- Título curto e chamativo
- Texto principal curto e escaneável
- Sugestão visual para a imagem
- Prompt de imagem em inglês entre [IMG_PROMPT] e [/IMG_PROMPT]
  → Incluir no prompt: "4:5 aspect ratio, Instagram post format"
  → Incluir cores da marca se fornecidas
- Legenda otimizada para Instagram
- 5-8 hashtags (APENAS genéricas do nicho + da marca SE informadas)

CARROSSEL (6-8 slides):
- Para cada slide: Título, Texto curto, Sugestão visual, Prompt em inglês entre [IMG_PROMPT] e [/IMG_PROMPT]
- Slide 1 = capa impactante com curiosidade forte
- Slides 2-7 = conteúdo educativo com infográficos, diagramas, dados visuais
- Último slide = CTA forte
- TODOS os prompts devem incluir: "4:5 aspect ratio, Instagram carousel slide, consistent style with [estilo definido no slide 1]"
- TODOS os prompts devem usar as MESMAS cores da marca
- O estilo visual deve ser IDÊNTICO em todos os slides — como se fossem páginas do mesmo livro

REELS:
- Gancho forte (primeiros 3 segundos)
- 3-4 pontos de explicação
- CTA final
- Sugestão visual das cenas com prompts entre [IMG_PROMPT] e [/IMG_PROMPT]
  → Incluir: "16:9 aspect ratio, cinematic frame"
- Legenda + Hashtags

═══ REGRAS TÉCNICAS DOS PROMPTS DE IMAGEM ═══
- Prompts SEMPRE em inglês
- SEMPRE entre [IMG_PROMPT] e [/IMG_PROMPT]
- SEMPRE incluir o aspect ratio: "4:5 aspect ratio" para posts e carrosséis, "16:9 aspect ratio" para reels
- SEMPRE incluir cores hex da marca quando disponíveis
- SEMPRE descrever o estilo visual de forma consistente entre slides
- Gerar imagens RICAS em detalhes visuais: iluminação, composição, texturas, profundidade
- TEXTO NAS IMAGENS: mínimo possível. Para infográficos, use APENAS 1-3 palavras-chave como labels curtos (ex: "Protein", "Recovery"). NUNCA frases longas, parágrafos ou títulos extensos. O texto do post vai na legenda, NÃO na imagem.
- Prefira comunicar através de ÍCONES, SETAS, CORES e COMPOSIÇÃO VISUAL em vez de texto

═══ TOM E LINGUAGEM ═══
- Sempre em português do Brasil
- Adapte 100% ao tom da marca
- Storytelling + ativação de desejo
- Evite clichês — ângulos únicos e diferenciados
- Se o usuário enviou PDF de conteúdo, analise e transforme no formato solicitado
- Se o usuário enviou referências visuais, reproduza o estilo nos prompts adaptando às cores da marca"""


@app.post("/api/generate")
async def generate_content(request: Request):
    try:
        body = await request.json()
        tema = body.get("tema", "").strip()
        formato = body.get("formato", "Post")
        brand_text = body.get("brand_text", "").strip()
        brand_pdf = body.get("brand_pdf", "")
        content_pdf = body.get("content_pdf", "")
        ref_images = body.get("ref_images", [])

        system = SYSTEM_PROMPT
        if brand_text:
            system += f"\n\n══ IDENTIDADE DE MARCA (TEXTO) ══\n{brand_text}\n══ FIM ══\nUse SOMENTE estas informações. Não invente dados. Extraia cores, tom e estilo e aplique em TODOS os prompts de imagem de forma CONSISTENTE."
        if brand_pdf:
            system += "\n\n══ MANUAL DE MARCA (PDF ANEXADO) ══\nO usuário anexou um PDF completo de identidade visual. ANALISE COM PROFUNDIDADE: extraia cores hex, tipografia, estilo visual, tom de voz, padrões gráficos e público-alvo. Use TUDO isso para personalizar o conteúdo E os prompts de imagem. Cada prompt deve refletir as cores e estilo do manual.\n══ FIM ══"

        has_files = bool(content_pdf) or bool(ref_images) or bool(brand_pdf)

        parts = []
        if brand_pdf:
            parts.append("O PDF de identidade visual da marca está anexado. Analise-o em profundidade e use todas as diretrizes visuais nos prompts de imagem.")
        if tema and content_pdf:
            parts.append(f'Tema: "{tema}"')
            parts.append(f"Formato: {formato}")
            parts.append("Analise o PDF de conteúdo anexado e use junto com o tema para gerar conteúdo no formato indicado.")
        elif content_pdf:
            parts.append(f"Formato: {formato}")
            parts.append("Analise o PDF de conteúdo anexado e transforme-o em conteúdo para Instagram no formato indicado.")
        elif tema:
            parts.append(f'Tema: "{tema}"')
            parts.append(f"Formato: {formato}")
            parts.append("Gere o conteúdo completo seguindo as regras.")
        else:
            return JSONResponse({"error": "Envie um tema ou um PDF de conteúdo."}, status_code=400)

        if ref_images:
            parts.append(f"\n{len(ref_images)} imagem(ns) de referência visual anexadas. Analise o estilo visual e reproduza nos prompts de imagem, adaptando às cores da marca.")

        parts.append(f"\nLEMBRETE: Todos os prompts de imagem devem usar aspect ratio {'4:5' if formato != 'Reels' else '16:9'} e manter estilo visual CONSISTENTE entre si.")

        instruction_text = "\n".join(parts)

        if has_files:
            content = []
            if brand_pdf:
                content.append({
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": brand_pdf}
                })
            for img in ref_images:
                content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": img.get("media_type", "image/jpeg"), "data": img["data"]}
                })
            if content_pdf:
                content.append({
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": content_pdf}
                })
            content.append({"type": "text", "text": instruction_text})
        else:
            content = instruction_text

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
                "messages": [{"role": "user", "content": content}]
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

        # Return format along with prompts so frontend can pass it to /api/image
        return JSONResponse({"text": text, "image_prompts": img_prompts, "formato": formato})

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/image")
async def generate_image(request: Request):
    try:
        body = await request.json()
        prompt = body.get("prompt", "")
        formato = body.get("formato", "Post")

        if not prompt:
            return JSONResponse({"error": "Prompt vazio"}, status_code=400)

        # Force aspect ratio based on format
        if formato == "Reels":
            aspect = "16:9 landscape aspect ratio"
        else:
            aspect = "4:5 portrait aspect ratio (Instagram post/carousel format, NOT stories/vertical)"

        # Check if prompt already mentions aspect ratio
        has_ratio = any(r in prompt.lower() for r in ["aspect ratio", "4:5", "16:9", "9:16"])
        if not has_ratio:
            full_prompt = f"Generate a high-quality, detailed, professional image with {aspect}. Keep any text in the image to short labels only (1-3 words max per label). Focus on visual communication through icons, colors, arrows and composition rather than text. Image description: {prompt}"
        else:
            full_prompt = f"Generate a high-quality, detailed, professional image. Keep any text in the image to short labels only (1-3 words max per label). Focus on visual communication through icons, colors, arrows and composition rather than text. Image description: {prompt}"

        model = "gemini-3.1-flash-image-preview"
        max_retries = 3

        for attempt in range(max_retries):
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": full_prompt}]}],
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
