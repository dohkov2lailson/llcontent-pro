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
Crie conteúdo baseado EXCLUSIVAMENTE na identidade de marca fornecida.
- NUNCA invente nomes de empresa, hashtags de marca ou slogans não fornecidos
- Sem identidade de marca → tom neutro e profissional

═══ REGRA #2: LEITURA DO MANUAL DE MARCA ═══
Se o usuário enviar PDF de identidade visual, analise com profundidade:
- Identifique as cores e descreva-as POR NOME nos prompts (ex: "vibrant orange", "deep purple", "dark navy blue"). NUNCA use códigos hex (#FF6B00 etc) dentro dos prompts de imagem.
- Identifique o estilo visual e replique nos prompts
- Capture o tom de voz e aplique em legendas e textos
- Identifique o público-alvo e adapte a linguagem

═══ REGRA #3: COERÊNCIA VISUAL ENTRE SLIDES ═══
Para CARROSSEL: todas as imagens devem parecer parte do mesmo conjunto.
- MESMA paleta de cores descrita por nome em todos os prompts
- MESMO estilo de ilustração/fotografia em todos os slides
- MESMO tipo de composição — como páginas do mesmo livro

═══ FORMATOS ═══

POST SIMPLES:
- Título curto e chamativo
- Texto principal curto e escaneável
- Sugestão visual para a imagem
- Prompt de imagem em inglês entre [IMG_PROMPT] e [/IMG_PROMPT]
- Legenda otimizada para Instagram
- 5-8 hashtags (genéricas do nicho + da marca SE informadas)

CARROSSEL (5 slides) — STORYTELLING VISUAL:
O carrossel deve contar uma HISTÓRIA visual. Cada slide é um capítulo que faz o usuário querer ver o próximo. Pense como um mini-documentário em imagens.

Estrutura narrativa:
- Slide 1 (GANCHO): Capa impactante que gera curiosidade irresistível. A imagem deve provocar emoção — dor, desejo, surpresa. O título deve fazer a pessoa parar de rolar o feed.
- Slide 2 (PROBLEMA): Mostra a dor/problema do público. A imagem deve representar visualmente a frustração, o erro comum, ou a situação "antes". Crie empatia.
- Slide 3 (VIRADA): A revelação, o insight, a solução começa a aparecer. A imagem muda de tom — de sombrio/tenso para esperançoso. É o momento "ah, entendi!".
- Slide 4 (SOLUÇÃO): Mostra a transformação, o resultado, o "como fazer". Imagem aspiracional que mostra o "depois", o sucesso, a conquista.
- Slide 5 (CTA): Fechamento forte. Imagem que convida à ação — seguir, salvar, compartilhar, comentar. Deve transmitir conexão e comunidade.

Para cada slide gere: Título, Texto curto, Sugestão visual, Prompt em inglês entre [IMG_PROMPT] e [/IMG_PROMPT]

Regras visuais do carrossel:
- A paleta de cores e estilo devem ser IDÊNTICOS em todos os slides
- Mas a ATMOSFERA muda: slide 1-2 mais tensos/escuros → slide 3 transição → slide 4-5 mais vibrantes/claros
- Cada prompt deve descrever uma CENA com contexto emocional, não apenas um objeto ou diagrama
- Pense em cada imagem como uma cena de filme que conta parte da história
- Os prompts devem fazer referência ao mesmo "universo visual" — mesmos elementos, cores, iluminação base

REELS:
- Gancho forte (primeiros 3 segundos)
- 3-4 pontos de explicação
- CTA final
- Sugestão visual das cenas com prompts entre [IMG_PROMPT] e [/IMG_PROMPT]
- Legenda + Hashtags

═══ COMO ESCREVER PROMPTS DE IMAGEM ═══
Os prompts vão diretamente para um gerador de imagem por IA. O gerador renderiza TUDO que você escrever como conteúdo visual. Por isso:

FAÇA:
- Descreva a CENA visual em inglês (composição, iluminação, estilo, cores por nome)
- Ex: "Dark background infographic showing muscle anatomy with glowing orange and purple highlights, modern flat design style, circular diagram with icons representing energy, nutrition, recovery"
- Use nomes de cores: "vibrant orange", "neon purple", "deep black background"
- Descreva ícones e composição visual

NUNCA COLOQUE NO PROMPT:
- Códigos hex (#FF6B00, #A855F7, etc) — o gerador vai escrever isso NA imagem
- Nomes de fontes (Montserrat, Arial, etc) — aparece como texto na imagem
- Instruções técnicas (aspect ratio, format, etc) — vira texto visual
- Frases como "consistent style with..." — aparece na imagem
- Meta-instruções como "clean design", "1-3 words max" — aparece na imagem
- A palavra "aspect ratio" ou dimensões — isso é controlado separadamente

O prompt deve ser PURAMENTE DESCRITIVO da cena visual. Pense como se estivesse descrevendo uma pintura para alguém pintar.

═══ TOM E LINGUAGEM ═══
- Sempre em português do Brasil (exceto prompts de imagem que são em inglês)
- Adapte 100% ao tom da marca
- Storytelling + ativação de desejo
- Evite clichês — ângulos únicos e diferenciados"""


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
            system += f"\n\n══ IDENTIDADE DE MARCA (TEXTO) ══\n{brand_text}\n══ FIM ══\nUse SOMENTE estas informações. Descreva as cores POR NOME nos prompts de imagem, nunca por código hex."
        if brand_pdf:
            system += "\n\n══ MANUAL DE MARCA (PDF ANEXADO) ══\nAnalise o PDF de identidade visual com profundidade. Extraia cores, estilo visual, tom de voz e público-alvo. Nos prompts de imagem, descreva as cores POR NOME (ex: 'vibrant orange', 'deep purple'), NUNCA use códigos hex.\n══ FIM ══"

        has_files = bool(content_pdf) or bool(ref_images) or bool(brand_pdf)

        parts = []
        if brand_pdf:
            parts.append("O PDF de identidade visual da marca está anexado. Analise e use as diretrizes visuais nos prompts de imagem, descrevendo cores por nome.")
        if tema and content_pdf:
            parts.append(f'Tema: "{tema}"')
            parts.append(f"Formato: {formato}")
            parts.append("Analise o PDF de conteúdo e use junto com o tema para gerar conteúdo.")
        elif content_pdf:
            parts.append(f"Formato: {formato}")
            parts.append("Analise o PDF de conteúdo e transforme em conteúdo para Instagram.")
        elif tema:
            parts.append(f'Tema: "{tema}"')
            parts.append(f"Formato: {formato}")
            parts.append("Gere o conteúdo completo.")
        else:
            return JSONResponse({"error": "Envie um tema ou um PDF de conteúdo."}, status_code=400)

        if ref_images:
            parts.append(f"\n{len(ref_images)} imagem(ns) de referência visual anexadas. Reproduza o estilo visual nos prompts, adaptando às cores da marca.")

        instruction_text = "\n".join(parts)

        if has_files:
            content = []
            if brand_pdf:
                content.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": brand_pdf}})
            for img in ref_images:
                content.append({"type": "image", "source": {"type": "base64", "media_type": img.get("media_type", "image/jpeg"), "data": img["data"]}})
            if content_pdf:
                content.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": content_pdf}})
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
        img_prompts = [clean_prompt(m.strip()) for m in img_prompts]

        return JSONResponse({"text": text, "image_prompts": img_prompts, "formato": formato})

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


def clean_prompt(prompt):
    """Remove hex codes, font names, and meta-instructions that Gemini renders as text"""
    # Remove hex color codes
    prompt = re.sub(r'#[0-9A-Fa-f]{6}\b', '', prompt)
    prompt = re.sub(r'#[0-9A-Fa-f]{3}\b', '', prompt)
    # Remove common font name mentions
    prompt = re.sub(r'\b(Montserrat|Arial|Helvetica|Roboto|Inter|Poppins|Outfit|DM Sans)\s*(font|typeface|typography)?\b', '', prompt, flags=re.IGNORECASE)
    # Remove aspect ratio mentions
    prompt = re.sub(r'\b\d+:\d+\s*(aspect\s*ratio|format|portrait|landscape)?\b', '', prompt, flags=re.IGNORECASE)
    prompt = re.sub(r'\b(aspect\s*ratio)\b', '', prompt, flags=re.IGNORECASE)
    # Remove meta-instructions
    prompt = re.sub(r'\b(consistent\s*style\s*with|Instagram\s*(post|carousel|story|stories|reel)\s*(format|slide)?)\b', '', prompt, flags=re.IGNORECASE)
    prompt = re.sub(r'\b(\d+[-–]\d+\s*words?\s*max\s*(per\s*label)?)\b', '', prompt, flags=re.IGNORECASE)
    # Clean up extra spaces and commas
    prompt = re.sub(r'\s*,\s*,', ',', prompt)
    prompt = re.sub(r'\s{2,}', ' ', prompt)
    prompt = prompt.strip().strip(',').strip()
    return prompt


@app.post("/api/image")
async def generate_image(request: Request):
    try:
        body = await request.json()
        prompt = body.get("prompt", "")
        formato = body.get("formato", "Post")

        if not prompt:
            return JSONResponse({"error": "Prompt vazio"}, status_code=400)

        # Clean the prompt one more time (in case user edited it)
        prompt = clean_prompt(prompt)

        # Set aspect ratio as a SEPARATE instruction, not mixed with content
        if formato == "Reels":
            size_instruction = "Generate in 16:9 landscape format."
        else:
            size_instruction = "Generate in 4:5 portrait format suitable for Instagram."

        # Build a clean prompt: size first as system-level, then pure visual description
        full_prompt = f"{size_instruction}\n\n{prompt}"

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
