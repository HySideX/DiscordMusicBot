import discord
from discord.ext import commands
from discord import FFmpegPCMAudio, PCMVolumeTransformer
import yt_dlp
from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials
from collections import deque
import asyncio

# Initialisation
TOKEN = "Votre token de bot Discord"
SPOTIFY_CLIENT_ID = "Votre token de l'API Spotify"
SPOTIFY_CLIENT_SECRET = "Votre token SECRET de l'API Spotify"
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Configurations globales
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn"
}
disconnect_delay = 120
music_queue = deque()
volume_levels = {}

# Initialisation Spotify
spotify = Spotify(client_credentials_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))


### Utilitaires ###

def get_audio_info(query):
    """Obtenir l'URL audio et le titre avec yt-dlp."""
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
        return info['url'], info['title']

def get_spotify_tracks(query):
    """Récupérer les pistes Spotify depuis une URL."""
    if "track" in query:
        track = spotify.track(query)
        return [f"{track['name']} {track['artists'][0]['name']}"]
    elif "playlist" in query:
        return [
            f"{item['track']['name']} {item['track']['artists'][0]['name']}"
            for item in spotify.playlist(query)['tracks']['items']
        ]
    elif "album" in query:
        return [
            f"{track['name']} {track['artists'][0]['name']}"
            for track in spotify.album(query)['tracks']['items']
        ]
    else:
        raise ValueError("Lien Spotify invalide.")


async def handle_inactivity(ctx):
    """Gérer la déconnexion automatique en cas d'inactivité."""
    await asyncio.sleep(disconnect_delay)
    if ctx.voice_client and not ctx.voice_client.is_playing() and not music_queue:
        await ctx.send(f"Aucune musique ajoutée dans les 2 dernières minutes. Déconnexion.")
        await ctx.voice_client.disconnect()


### Commandes ###

@bot.event
async def on_ready():
    print(f"{bot.user.name} est prêt !")


@bot.command()
async def join(ctx):
    """Rejoindre un canal vocal."""
    if ctx.author.voice:
        await ctx.author.voice.channel.connect()
        await ctx.send("Connecté au canal vocal.")
        await handle_inactivity(ctx)
    else:
        await ctx.send("Tu dois être dans un canal vocal pour utiliser cette commande.")


@bot.command()
async def leave(ctx):
    """Quitter un canal vocal."""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Déconnecté du canal vocal.")
    else:
        await ctx.send("Je ne suis pas connecté à un canal vocal.")


@bot.command()
async def play(ctx, url):
    """Ajouter une musique à la file d'attente."""
    if not ctx.voice_client:
        await ctx.send("Je ne suis pas dans un canal vocal. Utilise `!join` pour m'ajouter.")
        return

    try:
        tracks = get_spotify_tracks(url) if "spotify.com" in url else [url]
        for track in tracks:
            music_queue.append((ctx, track))
        await ctx.send("Musique ajoutée à la file d'attente.")
        if not ctx.voice_client.is_playing():
            await play_next(ctx)
    except Exception as e:
        await ctx.send(f"Erreur : {e}")


async def play_next(ctx):
    """Jouer la prochaine musique."""
    if music_queue:
        ctx, track = music_queue.popleft()
        audio_url, title = get_audio_info(track)
        source = PCMVolumeTransformer(FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS),
                                       volume=volume_levels.get(ctx.guild.id, 0.03))
        ctx.voice_client.play(source, after=lambda e: bot.loop.create_task(play_next(ctx)))
        await ctx.send(f"Lecture en cours : **{title}**")
    else:
        await ctx.send("File d'attente vide. Déconnexion dans 2 minutes.")
        await handle_inactivity(ctx)
        

@bot.command()
async def volume(ctx, level: float):
    """Ajuster le volume entre 0 et 1 (0% à 100%)."""
    if not ctx.voice_client or not ctx.voice_client.source:
        await ctx.send("Aucune lecture audio en cours.")
        return

    if 0 <= level <= 1.0:
        ctx.voice_client.source.volume = level
        volume_levels[ctx.guild.id] = level
        await ctx.send(f"Volume ajusté à {int(level * 100)} %.")
    else:
        await ctx.send("Le volume doit être compris entre 0 (silence) et 1 (100%).")

@bot.command()
async def pause(ctx):
    """Mettre la lecture en pause."""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("Lecture mise en pause ⏸️")
    else:
        await ctx.send("Aucune musique en cours à mettre en pause.")


@bot.command()
async def resume(ctx):
    """Reprendre la lecture."""
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("Lecture reprise ▶️")
    else:
        await ctx.send("Aucune lecture n'est en pause.")


@bot.command()
async def queue(ctx):
    """Afficher la file d'attente."""
    if music_queue:
        queue_list = "\n".join([f"{i + 1}. {track}" for i, (_, track) in enumerate(music_queue)])
        await ctx.send(f"File d'attente :\n{queue_list}")
    else:
        await ctx.send("La file d'attente est vide.")


@bot.command()
async def skip(ctx):
    """Passer à la musique suivante."""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("Musique passée.")
    else:
        await ctx.send("Aucune musique à passer.")


@bot.command()
async def stop(ctx):
    """Arrêter la lecture et vider la file d'attente."""
    if ctx.voice_client:
        ctx.voice_client.stop()
        music_queue.clear()
        await ctx.send("Lecture arrêtée et file vidée.")
    else:
        await ctx.send("Aucune musique à arrêter.")


@bot.command()
async def help(ctx):
    """Afficher l'aide."""
    commands_list = """
**Commandes disponibles :**
- `!join` : Rejoindre le canal vocal.
- `!leave` : Quitter le canal vocal.
- `!play <url>` : Ajouter une musique (YouTube ou Spotify).
- `!pause` : Mettre la musique en pause.
- `!resume` : Reprendre la musique en pause.
- `!queue` : Voir la file d'attente.
- `!skip` : Passer à la musique suivante.
- `!stop` : Arrêter la musique.
- `!volume <valeur>` : Régler le volume (0 à 2).
    """
    await ctx.send(commands_list)


bot.run(TOKEN)