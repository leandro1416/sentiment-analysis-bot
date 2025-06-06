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
from playwright.sync_api import sync_playwright
import logging
import subprocess
from playwright.async_api import async_playwright

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuração da API
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def extrair_texto(link):
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            page = await browser.new_page(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            )
            
            try:
                await page.goto(link, wait_until='networkidle')
                # Try to find the main article content
                content = await page.evaluate("""() => {
                    // Try different selectors for article content
                    const selectors = [
                        'article',
                        'main',
                        '.article-content',
                        '.post-content',
                        '.entry-content',
                        '#content'
                    ];
                    
                    for (const selector of selectors) {
                        const element = document.querySelector(selector);
                        if (element) {
                            return element.innerText;
                        }
                    }
                    
                    // If no specific content area found, get the body text
                    return document.body.innerText;
                }""")
                
                await browser.close()
                return content
            except Exception as e:
                logging.error(f"Error during page navigation: {str(e)}")
                await browser.close()
                
                # Fallback to requests + BeautifulSoup
                response = requests.get(link)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                return soup.get_text()
                
    except Exception as e:
        logging.error(f"Error extracting text from {link}: {str(e)}")
        return ""

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

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a message to the user."""
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "Desculpe, ocorreu um erro ao processar sua solicitação. Por favor, tente novamente mais tarde."
        )

if __name__ == "__main__":
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    
    # Criar a aplicação
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Adicionar handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analisar))
    
    # Adicionar handler de erro
    application.add_error_handler(error_handler)
    
    # Configurar polling com timeout e clean=True
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        timeout=30,
        read_timeout=30,
        write_timeout=30,
        connect_timeout=30,
        pool_timeout=30
    )