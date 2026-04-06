import os
import sqlite3
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1486268008266596443
WELCOME_LOG_CHANNEL_ID = 1486268009550188556
RANKING_CHANNEL_ID = 1486268011823366218

ADD_ACAO_CHANNEL_ID = 1486645052653437059
EVENTO_ACAO_CHANNEL_ID = 1486644323515895838

DB_FILE = "faction.db"

ADMIN_ROLES = [
    1486268008409206867,
    1486268008409206864,
    1486268008266596449,
    1486268008266596448
]

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
guild_obj = discord.Object(id=GUILD_ID)

def is_admin(member: discord.Member) -> bool:
    return any(role.id in ADMIN_ROLES for role in member.roles)

def get_week_key():
    now = datetime.now()
    year, week, _ = now.isocalendar()
    return f"{year}-W{week}"

def now_str():
    return datetime.now().strftime("%d/%m/%Y %H:%M")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS farms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL,
            membro TEXT NOT NULL,
            farm_tipo TEXT NOT NULL,
            qtd REAL NOT NULL,
            admin_id INTEGER NOT NULL,
            admin_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pvp_events (
            message_id INTEGER PRIMARY KEY,
            channel_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            created_by_id INTEGER NOT NULL,
            created_by_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            status TEXT NOT NULL,
            week_key TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pvp_confirmations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            user_name TEXT NOT NULL,
            status TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(message_id, user_id)
        )
    """)

    conn.commit()
    conn.close()

def add_farm(membro: str, farm_tipo: str, qtd: float, admin_id: int, admin_name: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO farms (week_key, membro, farm_tipo, qtd, admin_id, admin_name, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        get_week_key(),
        membro,
        farm_tipo,
        qtd,
        admin_id,
        admin_name,
        now_str()
    ))
    conn.commit()
    conn.close()

def get_farm_breakdown(limit=10):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT membro,
               SUM(CASE WHEN farm_tipo = 'Pedra' THEN qtd ELSE 0 END) as pedra,
               SUM(CASE WHEN farm_tipo = 'Semente' THEN qtd ELSE 0 END) as semente,
               SUM(qtd) as total
        FROM farms
        WHERE week_key = ?
        GROUP BY membro
        ORDER BY total DESC
        LIMIT ?
    """, (get_week_key(), limit))
    rows = cursor.fetchall()
    conn.close()
    return rows

def save_pvp_event(message_id: int, channel_id: int, title: str, description: str, created_by_id: int, created_by_name: str, expires_at: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO pvp_events
        (message_id, channel_id, title, description, created_by_id, created_by_name, created_at, expires_at, status, week_key)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        message_id,
        channel_id,
        title,
        description,
        created_by_id,
        created_by_name,
        now_str(),
        expires_at,
        "aberto",
        get_week_key()
    ))
    conn.commit()
    conn.close()

def get_event_data(message_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT message_id, channel_id, title, description, created_by_id, created_by_name, created_at, expires_at, status, week_key
        FROM pvp_events
        WHERE message_id = ?
    """, (message_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def set_event_status(message_id: int, status: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE pvp_events
        SET status = ?
        WHERE message_id = ?
    """, (status, message_id))
    conn.commit()
    conn.close()

def upsert_confirmation(message_id: int, user_id: int, user_name: str, status: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO pvp_confirmations (message_id, user_id, user_name, status, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(message_id, user_id)
        DO UPDATE SET
            user_name=excluded.user_name,
            status=excluded.status,
            updated_at=excluded.updated_at
    """, (
        message_id,
        user_id,
        user_name,
        status,
        now_str()
    ))
    conn.commit()
    conn.close()

def delete_confirmation(message_id: int, user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM pvp_confirmations
        WHERE message_id = ? AND user_id = ?
    """, (message_id, user_id))
    conn.commit()
    conn.close()

def remove_member_from_event(message_id: int, member_name: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM pvp_confirmations
        WHERE message_id = ? AND LOWER(user_name) = LOWER(?)
    """, (message_id, member_name))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted

def get_event_lists(message_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_name, status
        FROM pvp_confirmations
        WHERE message_id = ?
        ORDER BY user_name COLLATE NOCASE
    """, (message_id,))
    rows = cursor.fetchall()
    conn.close()

    confirmados = [name for name, status in rows if status == "confirmado"]
    recusados = [name for name, status in rows if status == "recusado"]
    return confirmados, recusados

def get_top_pvp(limit=10):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_name, COUNT(*) as total
        FROM pvp_confirmations pc
        JOIN pvp_events pe ON pe.message_id = pc.message_id
        WHERE pe.week_key = ? AND pc.status = 'confirmado'
        GROUP BY user_name
        ORDER BY total DESC
        LIMIT ?
    """, (get_week_key(), limit))
    rows = cursor.fetchall()
    conn.close()
    return rows

def is_event_open(message_id: int):
    row = get_event_data(message_id)
    if not row:
        return False
    return row[8] == "aberto"

def build_pvp_embed(message_id: int, title: str, description: str, creator_name: str, expires_at: str, status: str):
    confirmados, recusados = get_event_lists(message_id)

    color = 0xFF4444 if status == "aberto" else 0x555555
    status_text = "🟢 Aberto" if status == "aberto" else "⛔ Encerrado"

    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )

    embed.add_field(
        name=f"Status",
        value=f"{status_text}\nExpira em: {expires_at}",
        inline=False
    )

    embed.add_field(
        name=f"✅ Confirmados ({len(confirmados)})",
        value="\n".join(confirmados[:30]) if confirmados else "Ninguém confirmou ainda.",
        inline=True
    )

    embed.add_field(
        name=f"❌ Não vão ({len(recusados)})",
        value="\n".join(recusados[:30]) if recusados else "Ninguém recusou ainda.",
        inline=True
    )

    embed.add_field(
        name="Como responder",
        value="Use os botões abaixo antes do prazo para confirmar, recusar ou remover sua resposta.",
        inline=False
    )

    embed.set_footer(text=f"Criado por {creator_name}")
    return embed

class PVPEventView(discord.ui.View):
    def __init__(self, disabled=False):
        super().__init__(timeout=None)
        for item in self.children:
            item.disabled = disabled

    @discord.ui.button(label="Participar", style=discord.ButtonStyle.success, custom_id="pvp_participar")
    async def participar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_event_open(interaction.message.id):
            await interaction.response.send_message("⛔ Esta chamada já expirou.", ephemeral=True)
            return

        row = get_event_data(interaction.message.id)
        upsert_confirmation(
            message_id=interaction.message.id,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
            status="confirmado"
        )

        embed = build_pvp_embed(
            interaction.message.id,
            row[2],
            row[3],
            row[5],
            row[7],
            row[8]
        )
        await interaction.response.edit_message(embed=embed, view=PVPEventView(disabled=False))

    @discord.ui.button(label="Não participar", style=discord.ButtonStyle.danger, custom_id="pvp_recusar")
    async def recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_event_open(interaction.message.id):
            await interaction.response.send_message("⛔ Esta chamada já expirou.", ephemeral=True)
            return

        row = get_event_data(interaction.message.id)
        upsert_confirmation(
            message_id=interaction.message.id,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
            status="recusado"
        )

        embed = build_pvp_embed(
            interaction.message.id,
            row[2],
            row[3],
            row[5],
            row[7],
            row[8]
        )
        await interaction.response.edit_message(embed=embed, view=PVPEventView(disabled=False))

    @discord.ui.button(label="Remover minha resposta", style=discord.ButtonStyle.secondary, custom_id="pvp_remover")
    async def remover(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_event_open(interaction.message.id):
            await interaction.response.send_message("⛔ Esta chamada já expirou.", ephemeral=True)
            return

        row = get_event_data(interaction.message.id)
        delete_confirmation(
            message_id=interaction.message.id,
            user_id=interaction.user.id
        )

        embed = build_pvp_embed(
            interaction.message.id,
            row[2],
            row[3],
            row[5],
            row[7],
            row[8]
        )
        await interaction.response.edit_message(embed=embed, view=PVPEventView(disabled=False))

async def expire_event_later(message_id: int, channel_id: int, minutes: int):
    await asyncio.sleep(minutes * 60)

    row = get_event_data(message_id)
    if not row or row[8] != "aberto":
        return

    set_event_status(message_id, "encerrado")

    channel = bot.get_channel(channel_id)
    if channel is None:
        return

    try:
        msg = await channel.fetch_message(message_id)
        embed = build_pvp_embed(
            message_id,
            row[2],
            row[3],
            row[5],
            row[7],
            "encerrado"
        )
        await msg.edit(embed=embed, view=PVPEventView(disabled=True))
    except:
        pass

@bot.event
async def on_ready():
    init_db()
    bot.add_view(PVPEventView(disabled=False))

    try:
        synced = await bot.tree.sync(guild=guild_obj)
        print(f"{bot.user} online com sucesso!")
        print(f"{len(synced)} slash commands sincronizados.")
    except Exception as e:
        print(f"Erro ao sincronizar comandos: {e}")

    await bot.change_presence(
        activity=discord.Game(
            name="/farm | /previewtop | /fechamento | /pvpevent | /removerpvp | /toppvp"
        )
    )

@bot.event
async def on_member_join(member):
    try:
        embed = discord.Embed(
            title="🎉 Bem-vindo à facção!",
            description="Use `/tutorial` para aprender os comandos disponíveis.",
            color=0x00FF88
        )
        embed.add_field(name="Comandos", value="`/tutorial`", inline=False)
        embed.set_footer(text="Mensagem automática de boas-vindas")
        await member.send(embed=embed)
    except:
        pass

    channel = bot.get_channel(WELCOME_LOG_CHANNEL_ID)
    if channel:
        await channel.send(f"➕ **Entrada:** {member.mention} | `{member.id}`")

@bot.event
async def on_member_remove(member):
    channel = bot.get_channel(WELCOME_LOG_CHANNEL_ID)
    if channel:
        await channel.send(f"➖ **Saída:** {member.display_name} | `{member.id}`")

@bot.tree.command(name="farm", description="Registrar um farm para um membro", guild=guild_obj)
@app_commands.describe(
    membro="Nome do membro que recebeu o farm",
    qtd="Quantidade farmada",
    farm="Escolha o tipo de farm"
)
@app_commands.choices(farm=[
    app_commands.Choice(name="Pedra", value="Pedra"),
    app_commands.Choice(name="Semente", value="Semente"),
])
async def farm(interaction: discord.Interaction, membro: str, qtd: float, farm: app_commands.Choice[str]):
    if not isinstance(interaction.user, discord.Member) or not is_admin(interaction.user):
        await interaction.response.send_message("❌ Apenas admins podem usar esse comando.", ephemeral=True)
        return

    add_farm(membro, farm.value, qtd, interaction.user.id, interaction.user.display_name)

    embed = discord.Embed(title="✅ Farm registrado", color=0x00FF88)
    embed.add_field(name="Membro", value=membro, inline=False)
    embed.add_field(name="Farm desejado", value=farm.value, inline=True)
    embed.add_field(name="Quantidade", value=f"{qtd} un", inline=True)
    embed.add_field(name="Adicionado por", value=interaction.user.mention, inline=False)
    embed.set_footer(text=f"Registrado em {now_str()}")

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="previewtop", description="Ver ranking privado antes do fechamento", guild=guild_obj)
async def previewtop(interaction: discord.Interaction):
    if not isinstance(interaction.user, discord.Member) or not is_admin(interaction.user):
        await interaction.response.send_message("❌ Apenas admins podem usar esse comando.", ephemeral=True)
        return

    rows = get_farm_breakdown(limit=10)

    if not rows:
        await interaction.response.send_message("📭 Ainda não há farms registrados nesta semana.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🔒 Preview do ranking semanal",
        description="Visualização privada antes do fechamento oficial.",
        color=0xF1C40F
    )

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

    for i, (membro, pedra, semente, total) in enumerate(rows):
        embed.add_field(
            name=f"{medals[i]} {membro}",
            value=f"Pedra: {pedra:.0f} un\nSemente: {semente:.0f} un\nTotal: {total:.0f} un",
            inline=False
        )

    embed.set_footer(text=f"Semana atual: {get_week_key()}")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="fechamento", description="Publicar ranking semanal no canal oficial", guild=guild_obj)
async def fechamento(interaction: discord.Interaction):
    if not isinstance(interaction.user, discord.Member) or not is_admin(interaction.user):
        await interaction.response.send_message("❌ Apenas admins podem usar esse comando.", ephemeral=True)
        return

    rows = get_farm_breakdown(limit=10)

    if not rows:
        await interaction.response.send_message("📭 Não há farms registrados para publicar nesta semana.", ephemeral=True)
        return

    ranking_channel = interaction.guild.get_channel(RANKING_CHANNEL_ID)
    if ranking_channel is None:
        await interaction.response.send_message("❌ Não encontrei o canal de ranking configurado.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🏆 Fechamento semanal de farms",
        description=f"Resultado oficial da semana `{get_week_key()}`.",
        color=0xE67E22
    )

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

    for i, (membro, pedra, semente, total) in enumerate(rows):
        embed.add_field(
            name=f"{medals[i]} {membro}",
            value=f"Pedra: {pedra:.0f} un\nSemente: {semente:.0f} un\nTotal: {total:.0f} un",
            inline=False
        )

    embed.set_footer(text=f"Publicado por {interaction.user.display_name}")
    await ranking_channel.send(embed=embed)
    await interaction.response.send_message(f"✅ Fechamento publicado com sucesso em {ranking_channel.mention}.", ephemeral=True)

@bot.tree.command(name="pvpevent", description="Criar evento PVP com prazo e envio em canal separado", guild=guild_obj)
@app_commands.describe(
    titulo="Título da ação",
    mensagem="Descrição da ação PVP",
    duracao_minutos="Tempo de duração da chamada em minutos"
)
async def pvpevent(interaction: discord.Interaction, titulo: str, mensagem: str, duracao_minutos: int):
    if not isinstance(interaction.user, discord.Member) or not is_admin(interaction.user):
        await interaction.response.send_message("❌ Apenas admins podem usar esse comando.", ephemeral=True)
        return

    if interaction.channel_id != ADD_ACAO_CHANNEL_ID:
        await interaction.response.send_message(
            f"❌ Este comando só pode ser usado no canal <#{ADD_ACAO_CHANNEL_ID}>.",
            ephemeral=True
        )
        return

    if duracao_minutos <= 0:
        await interaction.response.send_message("❌ A duração deve ser maior que 0 minuto.", ephemeral=True)
        return

    event_channel = interaction.guild.get_channel(EVENTO_ACAO_CHANNEL_ID)
    if event_channel is None:
        await interaction.response.send_message(
            "❌ Não encontrei o canal de evento ação configurado.",
            ephemeral=True
        )
        return

    expires_at_dt = datetime.now() + timedelta(minutes=duracao_minutos)
    expires_at_str = expires_at_dt.strftime("%d/%m/%Y %H:%M")

    temp_embed = discord.Embed(
        title=f"⚔️ {titulo}",
        description=mensagem,
        color=0xFF4444
    )
    temp_embed.add_field(name="Status", value=f"🟢 Aberto\nExpira em: {expires_at_str}", inline=False)
    temp_embed.add_field(name="✅ Confirmados (0)", value="Ninguém confirmou ainda.", inline=True)
    temp_embed.add_field(name="❌ Não vão (0)", value="Ninguém recusou ainda.", inline=True)
    temp_embed.add_field(
        name="Como responder",
        value="Use os botões abaixo antes do prazo para confirmar, recusar ou remover sua resposta.",
        inline=False
    )
    temp_embed.set_footer(text=f"Criado por {interaction.user.display_name}")

    view = PVPEventView(disabled=False)
    msg = await event_channel.send(embed=temp_embed, view=view)

    save_pvp_event(
        message_id=msg.id,
        channel_id=msg.channel.id,
        title=f"⚔️ {titulo}",
        description=mensagem,
        created_by_id=interaction.user.id,
        created_by_name=interaction.user.display_name,
        expires_at=expires_at_str
    )

    asyncio.create_task(expire_event_later(msg.id, msg.channel.id, duracao_minutos))

    await interaction.response.send_message(
        f"✅ Ação criada com sucesso em {event_channel.mention}.\n⏳ Expiração: {duracao_minutos} minuto(s).",
        ephemeral=True
    )

@bot.tree.command(name="removerpvp", description="Remover manualmente um membro da lista de um evento PVP", guild=guild_obj)
@app_commands.describe(
    mensagem_id="ID da mensagem do evento PVP",
    membro="Nome exibido do membro para remover da lista"
)
async def removerpvp(interaction: discord.Interaction, mensagem_id: str, membro: str):
    if not isinstance(interaction.user, discord.Member) or not is_admin(interaction.user):
        await interaction.response.send_message("❌ Apenas admins podem usar esse comando.", ephemeral=True)
        return

    try:
        message_id = int(mensagem_id)
    except:
        await interaction.response.send_message("❌ O ID da mensagem é inválido.", ephemeral=True)
        return

    deleted = remove_member_from_event(message_id, membro)

    if deleted == 0:
        await interaction.response.send_message("❌ Não encontrei esse membro na lista desse evento.", ephemeral=True)
        return

    row = get_event_data(message_id)
    if row:
        channel = bot.get_channel(row[1])
        if channel:
            try:
                msg = await channel.fetch_message(message_id)
                embed = build_pvp_embed(
                    msg.id,
                    row[2],
                    row[3],
                    row[5],
                    row[7],
                    row[8]
                )
                await msg.edit(embed=embed, view=PVPEventView(disabled=(row[8] != "aberto")))
            except:
                pass

    await interaction.response.send_message("✅ Membro removido da lista do evento com sucesso.", ephemeral=True)

@bot.tree.command(name="toppvp", description="Ver ranking privado de presença em ações PVP", guild=guild_obj)
async def toppvp(interaction: discord.Interaction):
    if not isinstance(interaction.user, discord.Member) or not is_admin(interaction.user):
        await interaction.response.send_message("❌ Apenas admins podem usar esse comando.", ephemeral=True)
        return

    rows = get_top_pvp(limit=10)

    if not rows:
        await interaction.response.send_message("📭 Ainda não há confirmações PVP nesta semana.", ephemeral=True)
        return

    embed = discord.Embed(
        title="⚔️ Top PVP semanal",
        description="Ranking privado com base nas confirmações registradas nas ações.",
        color=0x8E44AD
    )

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

    for i, (membro, total) in enumerate(rows):
        embed.add_field(
            name=f"{medals[i]} {membro}",
            value=f"{int(total)} confirmações",
            inline=False
        )

    embed.set_footer(text=f"Semana atual: {get_week_key()}")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="tutorial", description="Aprender a usar o bot", guild=guild_obj)
async def tutorial(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📘 Tutorial do Bot da Facção",
        description="Guia rápido dos comandos.",
        color=0x3498DB
    )

    embed.add_field(
        name="/farm",
        value="Registra farm de Pedra ou Semente para um membro.",
        inline=False
    )
    embed.add_field(
        name="/previewtop",
        value="Mostra o ranking privado de farms para admins.",
        inline=False
    )
    embed.add_field(
        name="/fechamento",
        value="Publica o ranking oficial de farms no canal configurado.",
        inline=False
    )
    embed.add_field(
        name="/pvpevent",
        value=f"Cria uma ação apenas no canal <#{ADD_ACAO_CHANNEL_ID}> e publica o embed em <#{EVENTO_ACAO_CHANNEL_ID}> com prazo em minutos.",
        inline=False
    )
    embed.add_field(
        name="/removerpvp",
        value="Permite ao admin remover depois um membro da lista do evento.",
        inline=False
    )
    embed.add_field(
        name="/toppvp",
        value="Mostra ranking privado de confirmações PVP da semana.",
        inline=False
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)

bot.run(TOKEN)
