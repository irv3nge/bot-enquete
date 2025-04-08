import os
import discord
import asyncio
import threading
from dotenv import load_dotenv
from discord.ext import commands
from discord.ui import View, Button
from pymongo import MongoClient
from datetime import datetime

# CARREGAR VARIÁVEIS DE AMBIENTE
load_dotenv()
TOKEN = os.getenv("TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# VALIDAÇÃO BÁSICA
if not TOKEN:
    raise ValueError("❌ TOKEN do bot não encontrado. Verifique seu arquivo .env.")
if not MONGO_URI:
    raise ValueError("❌ URI do MongoDB não encontrada. Verifique seu arquivo .env.")

# CONFIGURAÇÕES
PERGUNTA = "Com que frequência você faz networking com outros profissionais da sua área?"
OPCOES = [
    "Frequentemente, estou sempre ativo em eventos e plataformas",
    "Ocasionalmente, participo de algumas oportunidades",
    "Raramente, não invisto muito tempo nisso",
    "Nunca, ainda não comecei a me engajar com networking"
]
TEMPO_EXPIRACAO = 86400  # 1 dia
CANAIS_ALVO = [1333583081738604647]  # IDs dos canais onde a enquete será enviada

# SETUP DO BOT E MONGO
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

mongo = MongoClient(MONGO_URI)
db = mongo["enquetesDB"]
colecao = db["votos"]

# BOTÕES E VIEW DA ENQUETE
class EnqueteButton(Button):
    def __init__(self, label, enquete_id):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.enquete_id = enquete_id

    async def callback(self, interaction: discord.Interaction):
        usuario = str(interaction.user)
        cargo = interaction.user.top_role.name
        resposta = self.label

        if colecao.find_one({"usuario": usuario, "enquete_id": self.enquete_id}):
            await interaction.response.send_message(
                "⚠️ Você já votou nessa enquete!", ephemeral=True
            )
            return

        colecao.insert_one({
            "usuario": usuario,
            "cargo": cargo,
            "resposta": resposta,
            "data_hora": datetime.utcnow(),
            "enquete_id": self.enquete_id
        })

        await interaction.response.send_message(
            f"✅ Voto registrado: {resposta}", ephemeral=True
        )

class EnqueteView(View):
    def __init__(self, enquete_id):
        super().__init__(timeout=TEMPO_EXPIRACAO)
        self.enquete_id = enquete_id
        self.message = None

        for opcao in OPCOES:
            self.add_item(EnqueteButton(opcao, enquete_id=enquete_id))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(view=self)

# COMANDOS DO BOT
@bot.command(name="iniciar_enquete")
async def iniciar_enquete(ctx):
    view = EnqueteView(enquete_id=ctx.message.id)
    mensagem = await ctx.send(content=f"**{PERGUNTA}**", view=view)
    view.message = mensagem

@bot.command(name="encerrar_enquete")
async def encerrar_enquete(ctx):
    async for mensagem in ctx.channel.history(limit=50):
        if mensagem.author == bot.user and mensagem.components:
            nova_view = View()
            for row in mensagem.components:
                for item in row.children:
                    item.disabled = True
                    nova_view.add_item(item)
            await mensagem.edit(view=nova_view)
            await ctx.send("✅ Enquete encerrada manualmente.")
            return
    await ctx.send("❌ Nenhuma enquete ativa encontrada.")

@bot.command(name="resultados")
async def mostrar_resultados(ctx):
    enquete_id = None
    async for mensagem in ctx.channel.history(limit=50):
        if mensagem.author == bot.user and mensagem.components:
            enquete_id = mensagem.id
            break

    if not enquete_id:
        await ctx.send("❌ Nenhuma enquete encontrada.")
        return

    votos = list(colecao.find({"enquete_id": enquete_id}))
    if not votos:
        await ctx.send("📭 Ninguém votou ainda.")
        return

    resultado = "**📊 Resultados da Enquete:**\n\n"
    for voto in votos:
        resultado += (
            f"👤 **{voto['usuario']}** ({voto['cargo']}) → {voto['resposta']} "
            f"({voto['data_hora'].strftime('%d/%m %H:%M')})\n"
        )

    await ctx.send(resultado)

@bot.command(name="disparar_em_todos")
async def disparar_em_todos(ctx):
    for canal_id in CANAIS_ALVO:
        canal = bot.get_channel(canal_id)
        if canal:
            view = EnqueteView(enquete_id=canal_id)
            mensagem = await canal.send(content=f"**{PERGUNTA}**", view=view)
            view.message = mensagem

# FUNÇÃO OPCIONAL: Tecla "Z" dispara enquete automaticamente
def monitorar_tecla():
    try:
        import keyboard  # pip install keyboard
        while True:
            if keyboard.is_pressed("z"):
                for canal_id in CANAIS_ALVO:
                    canal = bot.get_channel(canal_id)
                    if canal:
                        view = EnqueteView(enquete_id=canal_id)
                        asyncio.run_coroutine_threadsafe(
                            canal.send(content=f"**{PERGUNTA}**", view=view), bot.loop
                        )
                break
    except:
        print("⚠️ 'keyboard' não disponível — funcionalidade de tecla desativada.")

threading.Thread(target=monitorar_tecla, daemon=True).start()

# INICIAR O BOT
bot.run(TOKEN)
