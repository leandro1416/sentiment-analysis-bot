from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from openai import OpenAI
from newspaper import Article
import json
import sys
import os
from urllib.parse import urlparse
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import time
import random

# Load environment variables
load_dotenv()

# Configuração da API
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def extrair_texto(link):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0'
        }
        
        # Primeira tentativa: usar requests e BeautifulSoup
        try:
            response = requests.get(link, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remover elementos indesejados
            for element in soup(['script', 'style', 'nav', 'footer', 'header', 'iframe', 'noscript']):
                element.decompose()
                
            # Tentar encontrar o conteúdo principal
            article = soup.find('article') or soup.find('div', class_=['article', 'post', 'content', 'main-content'])
            
            if article:
                texto = article.get_text(separator=' ', strip=True)
            else:
                # Tentar encontrar parágrafos
                paragraphs = soup.find_all('p')
                texto = ' '.join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])
            
            if texto and len(texto) > 100:
                return texto
        except Exception as e:
            print(f"[AVISO] Primeira tentativa falhou: {str(e)}")
            
        # Segunda tentativa: usar newspaper3k
        try:
            article = Article(link)
            article.download()
            article.parse()
            texto = article.text
            
            if texto and len(texto) > 100:
                return texto
        except Exception as e:
            print(f"[AVISO] Segunda tentativa falhou: {str(e)}")
            
        print(f"[AVISO] Não foi possível extrair texto significativo do link: {link}")
        return None
        
    except Exception as e:
        print(f"[ERRO] Falha ao extrair texto: {str(e)}")
        return None

def classificar_conteudo_via_gpt(texto):
    try:
        resposta = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você é um Analista de Reputação Digital especializado em avaliação de conteúdo. "
                        "Sua função é analisar objetivamente conteúdos da web com foco em impacto reputacional, especialmente sobre Daniel Vorcaro e/ou Banco Master. "
                        "Ao encontrar incertezas, indique claramente suas limitações ao invés de presumir informações.\n\n"
                        "Classifique o conteúdo como POSITIVO, NEGATIVO ou NEUTRO com base em:\n"
                        "- Impacto potencial na reputação\n"
                        "- Confiabilidade da fonte\n"
                        "- Conteúdo específico (incluindo críticas, elogios, fatos, linguagem usada)\n\n"
                        "Classifique automaticamente como NEGATIVO qualquer conteúdo que mencione:\n"
                        "- Compra de uma mansão de R$280 milhões em Trancoso (BA)\n"
                        "- Festa de R$15 milhões da filha de Daniel Vorcaro com DJ Alok\n"
                        "- Referência incorreta ao banco como 'Banco Máxima' ou 'Banco Maxima'\n"
                        "- Discussões sobre ativos de alto risco ou aspectos controversos do portfólio do Banco Master\n"
                        "- Citações a Maxima Realty ou Zion Capital\n"
                        "- Menções ao pai de Daniel Vorcaro ou à sua origem familiar\n"
                        "- Estilo de vida extravagante ou eventos de luxo\n\n"
                        "Para cada análise, forneça:\n"
                        "- Classificação (POSITIVE/NEGATIVE/NEUTRAL)\n"
                        "- Fatores principais que influenciaram a classificação\n"
                        "- Avaliação da credibilidade da fonte\n"
                        "- Trechos ou elementos específicos que justificam a classificação\n"
                        "- Impacto reputacional potencial\n\n"
                        "Use linguagem profissional e objetiva. Não julgue com base em opinião pessoal, apenas com base no conteúdo e impacto."
                    )
                },
                {
                    "role": "user",
                    "content": f"Analise o conteúdo abaixo:\n\n\"\"\"{texto}\"\"\""
                }
            ],
            temperature=0.3,
            max_tokens=500
        )
        return resposta.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ERRO GPT] {e}")
        return None


def salvar_em_txt(link, analise, pasta="resultados_txt"):
    try:
        os.makedirs(pasta, exist_ok=True)
        dominio = urlparse(link).netloc.replace("www.", "").replace("/", "")
        base_path = os.path.join(pasta, dominio)
        path = f"{base_path}.txt"

        # Se já existir, crie novo com número incremental
        contador = 2
        while os.path.exists(path):
            path = f"{base_path}{contador}.txt"
            contador += 1

        with open(path, "w", encoding="utf-8") as f:
            f.write(f"Link: {link}\n\n")
            f.write(analise)

        print(f"[SUCESSO] Resultado salvo em {path}")
    except Exception as e:
        print(f"[ERRO SALVAR TXT] {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Olá! Envie o link do conteúdo que você deseja que eu analise.")

async def analisar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    texto = await extrair_texto(link)
    if texto:
        analise = classificar_conteudo_via_gpt(texto)
        await update.message.reply_text(f"[ANÁLISE GPT]\n{analise}")
        salvar_em_txt(link, analise)
    else:
        await update.message.reply_text("Não consegui acessar ou extrair conteúdo do link fornecido. Verifique se ele está correto e acessível.")

if __name__ == "__main__":
    import asyncio
    import logging
    logging.basicConfig(level=logging.INFO)

    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analisar))

    print("Bot está rodando...")
    app.run_polling()